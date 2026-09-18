"""Relocate a nested completed library into a flat final folder, once, offline.

Nothing is copied: every torrent's own top-level entry is renamed inside the final
folder, which keeps the modification times fast-resume compares and lets the
torrents seed again without a full recheck. Each record is journalled before its
files move and its index entry is rewritten only once the move is verified, so an
interruption leaves one torrent to finish instead of a library to rebuild.
"""

import argparse
from contextlib import contextmanager
import fcntl
import itertools
import json
import os
from pathlib import Path
import sys

from .config import load_config
from .folders import RootRegistry, directory
from .moves import CompletionMoves, rename_entry
from .policy import parse_source
from .storage import atomic_write, write_json

JOURNAL = "flat-migration.json"
MODES = ("direct", "proxy")
BUSY = ("moving", "verifying", "recovery")


class Blocked(ValueError):
    """Something a person has to look at before anything is allowed to move."""


def debris(name):
    """Finder droppings, the one thing an emptied shell may be cleared of."""
    return name == ".DS_Store" or name.startswith("._")


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


@contextmanager
def exclusive(state):
    state.mkdir(parents=True, exist_ok=True)
    lock = (state / "app.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise Blocked(
            "LID utilise encore ce dossier de données. Arrêtez le service "
            "(systemctl --user stop lid.service) avant la migration."
        )
    try:
        yield
    finally:
        lock.close()


def torrent_files(state, mode, record):
    """The torrent's own file list, read back from the saved .torrent."""
    path = state / mode / f"{record['id']}.source"
    if not path.exists():
        return None
    raw = path.read_bytes()
    try:
        params, _, _ = parse_source(
            raw.decode() if record.get("kind") == "magnet" else raw, mode
        )
    except (ValueError, RuntimeError, UnicodeError):
        return None
    if not params.ti:
        return None
    return CompletionMoves.file_list(params.ti)


def free_name(entry, files, claimed):
    """The first `Nom (2)`, `Nom (3)`… nobody is using, extension kept last."""
    stem, suffix = entry, ""
    if len(files) == 1 and Path(files[0]["path"]).parent == Path("."):
        stem, suffix = os.path.splitext(entry)
    for number in itertools.count(2):
        candidate = f"{stem} ({number}){suffix}"
        if candidate.casefold() not in claimed and not CompletionMoves.reserved(
            candidate
        ):
            return candidate


def plan(config, final):
    """What each nested completed record would become, and what blocks it."""
    state = config.storage.state
    steps, skipped = [], []
    # Case-folded: the final folder may well sit on a case-insensitive mount.
    claimed = {item.name.casefold() for item in final.iterdir()}
    for mode in MODES:
        records = read_json(state / mode / "index.json", {})
        for key, record in sorted(records.items()):
            storage = record.get("storage")
            if not storage:
                continue
            if storage.get("journal") or storage.get("phase") in BUSY:
                raise Blocked(
                    f"{key} ({mode}) est en cours de déplacement. Terminez-le "
                    "dans LID avant de lancer la migration."
                )
            if storage.get("layout", "nested") == "flat":
                continue
            if storage.get("root") != str(final):
                continue
            files = torrent_files(state, mode, record)
            if not files:
                skipped.append(f"{key} ({mode}) : métadonnées illisibles")
                continue
            entry = CompletionMoves.entries_of(files)[0]
            if CompletionMoves.reserved(entry):
                raise Blocked(
                    f"« {entry} » ({key}) porte un nom réservé au dossier final."
                )
            nested = Path(storage["path"])
            if not (nested / entry).exists() and entry.casefold() not in claimed:
                skipped.append(f"{key} ({mode}) : « {entry} » introuvable")
                continue
            action, name = "move", entry
            if entry.casefold() in claimed:
                if CompletionMoves.same_content(final, files, [entry]):
                    action = "adopt"
                else:
                    action, name = "suffix", free_name(entry, files, claimed)
            claimed.add(name.casefold())
            steps.append(
                {
                    "mode": mode,
                    "key": key,
                    "name": record.get("name", key),
                    "entry": entry,
                    "nested": nested,
                    "source": nested / entry,
                    "target": final / name,
                    "folder": None if name == entry else name,
                    "action": action,
                    "files": files,
                }
            )
    return steps, skipped


def describe(folder, moving):
    """What a folder would still hold once `moving` has left it."""
    if not folder.is_dir():
        return None
    rest = sorted(item.name for item in folder.iterdir() if item.name not in moving)
    return (
        folder,
        [name for name in rest if debris(name)],
        [name for name in rest if not debris(name)],
    )


def shells(config, final, steps):
    """The emptied folders the old layout leaves behind, deepest first."""
    result, emptied = [], {mode: set() for mode in MODES}
    for step in steps:
        # An adopted torrent keeps its nested duplicate: nothing leaves it.
        moving = set() if step["action"] == "adopt" else {step["entry"]}
        for folder, moved in (
            (step["nested"], moving),
            (config.storage.downloads / step["mode"] / step["key"], set()),
        ):
            found = describe(folder, moved)
            if not found:
                continue
            result.append(found)
            if folder == step["nested"] and not found[2]:
                emptied[step["mode"]].add(folder.name)
    for mode in MODES:
        found = describe(final / mode, emptied[mode])
        if found:
            result.append(found)
    return result


def report(config, final, steps, skipped):
    groups = {
        "move": "À déplacer",
        "adopt": "À adopter (le contenu identique est déjà en place)",
        "suffix": "À renommer (le nom est déjà pris par un autre contenu)",
    }
    print("\nLID — migration vers un dossier final plat  [SIMULATION]\n")
    print(f"  Dossier final      : {final}")
    print(f"  Dossier temporaire : {config.storage.downloads}\n")
    for action, title in groups.items():
        chosen = [s for s in steps if s["action"] == action]
        if not chosen:
            continue
        print(f"{title} ({len(chosen)})")
        for step in chosen:
            print(f"  {step['mode']:<8}{step['key'][:10]}  {step['name']}")
            if action == "adopt":
                print(f"      déjà présent à l'identique : {step['target']}")
                print(f"      la copie imbriquée {step['source']} est conservée ;")
                print("      supprimez-la vous-même après vérification.")
            else:
                print(f"      {step['source']}")
                print(f"   →  {step['target']}")
        print()
    leftover = shells(config, final, steps)
    if leftover:
        print("Dossiers de l'ancienne disposition")
    for folder, junk, keepers in leftover:
        if keepers:
            print(f"Conservé    : {folder}")
            print(f"              contient {', '.join(keepers)}")
        elif junk:
            print(f"À supprimer : {folder}")
            print(f"              après {', '.join(junk)} (résidus Finder)")
        else:
            print(f"À supprimer : {folder}")
    if skipped:
        print("\nLaissés en place")
        for note in skipped:
            print(f"  {note}")
    if not steps:
        print("Rien à migrer : le dossier final est déjà plat.")
        return
    print(
        f"\n{len(steps)} torrent(s), aucun octet copié — renommage sur le même disque."
    )
    print("Relancez avec --apply pour exécuter.\n")


def verified(final, step):
    return CompletionMoves.complete_files(
        final, rename_entry(step["files"], step["folder"])
    )


def relocate(final, step):
    source, target = step["source"], step["target"]
    if step["action"] == "adopt" or not source.exists():
        return
    # os.rename silently replaces a file and swallows an empty directory, so the
    # destination is checked again right before the call rather than only once.
    if os.path.lexists(target):
        raise Blocked(
            f"« {target.name} » est apparu dans le dossier final : "
            f"rien n'a été déplacé pour {step['key']}."
        )
    os.rename(source, target)
    if not verified(final, step):
        os.rename(target, source)
        raise Blocked(
            f"{step['key']} : fichiers incomplets après déplacement, remis en place."
        )


def commit(config, final, mode, key, folder):
    identity = RootRegistry(config.storage.state).roots().get(str(final))
    path = config.storage.state / mode / "index.json"
    records = read_json(path, {})
    records[key]["storage"].update(
        path=str(final),
        root=str(final),
        root_id=identity,
        layout="flat",
        folder=folder,
        target=str(final),
        target_root=str(final),
        target_id=identity,
        target_layout="flat",
        phase="done",
        journal=None,
        error=None,
        manual_retry=False,
        retry_at=0,
    )
    write_json(path, records)


def recover(config, final):
    """Finish what an interrupted run left open, by looking at the disk."""
    path = config.storage.state / JOURNAL
    pending = read_json(path, {})
    for key, step in list(pending.items()):
        step = {**step, "source": Path(step["source"]), "target": Path(step["target"])}
        if verified(final, step):
            commit(config, final, step["mode"], key, step["folder"])
        elif not step["source"].exists():
            raise Blocked(
                f"{key} : fichiers absents des deux côtés du déplacement interrompu. "
                "Rassemblez-les avant de relancer."
            )
        pending.pop(key)
        write_json(path, pending)


def sweep(config, final, steps):
    for folder, junk, keepers in shells(config, final, steps):
        if keepers:
            continue
        for name in junk:
            try:
                (folder / name).unlink()
            except OSError:
                pass
        try:
            folder.rmdir()
        except OSError:
            pass


def apply_plan(config, final, steps):
    state = config.storage.state
    path = state / JOURNAL
    pending = read_json(path, {})
    for mode in MODES:
        index, backup = (
            state / mode / "index.json",
            state / mode / "index.before-flat.json",
        )
        if index.exists() and not backup.exists():
            atomic_write(backup, index.read_bytes())
    for step in steps:
        pending[step["key"]] = {
            "mode": step["mode"],
            "action": step["action"],
            "source": str(step["source"]),
            "target": str(step["target"]),
            "folder": step["folder"],
            "files": step["files"],
        }
        write_json(path, pending)
        relocate(final, step)
        commit(config, final, step["mode"], step["key"], step["folder"])
        pending.pop(step["key"])
        write_json(path, pending)
        print(f"  {step['mode']:<8}{step['key'][:10]}  →  {step['target']}")
    sweep(config, final, steps)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LID — aplatir le dossier final (simulation par défaut)"
    )
    parser.add_argument(
        "--config", default=str(Path(__file__).resolve().parent.parent / "config.yaml")
    )
    parser.add_argument(
        "--apply", action="store_true", help="Exécuter au lieu de simuler"
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if not config.storage.completed:
            raise Blocked("Aucun dossier final configuré : il n'y a rien à aplatir.")
        with exclusive(config.storage.state):
            final = directory(config.storage.completed)
            if args.apply:
                recover(config, final)
            steps, skipped = plan(config, final)
            if not args.apply:
                report(config, final, steps, skipped)
                return 0
            if not steps:
                print("\nRien à migrer : le dossier final est déjà plat.\n")
                return 0
            print("\nLID — migration vers un dossier final plat\n")
            apply_plan(config, final, steps)
            print(f"\n{len(steps)} torrent(s) migré(s). Redémarrez le service.\n")
    except Blocked as exc:
        print(f"\nBLOQUÉ : {exc}\n", file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(f"\nERREUR : {exc}\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
