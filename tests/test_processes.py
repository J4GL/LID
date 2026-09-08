import asyncio
import json
import time

from app.manager import Manager
from tests.support import make_torrent
from tests.test_integration import engine_config


def test_separate_processes_api_admission_and_saved_modes(tmp_path):
    async def scenario():
        config = engine_config(tmp_path, 1080)
        config.proxy.enabled = False
        manager = Manager(config)
        await manager.start()
        try:
            assert manager.workers["direct"][0].pid != manager.workers["proxy"][0].pid
            source, _ = make_torrent(tmp_path / "seed", seed=42)
            record = await manager.add("direct", source)
            try:
                await manager.add("proxy", source)
                raise AssertionError("Missing proxy should refuse addition")
            except Exception as exc:
                assert "Aucun proxy" in str(exc)
            await manager.action(record["id"], "pause")
            stored = json.loads(
                (config.storage.state / "direct" / "index.json").read_text()
            )
            assert stored[record["id"]]["paused"] is True
            assert stored[record["id"]]["mode"] == "direct"
            await manager.action(record["id"], "remove")
            await asyncio.sleep(1.2)
            assert record["id"] not in manager.known
            assert not manager.state()["torrents"]
        finally:
            await manager.close()
        assert all(not process.is_alive() for process, _ in manager.workers.values())

    asyncio.run(scenario())
