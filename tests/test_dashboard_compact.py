import time

from app.config import Config
from app.main import create_app
from tests.browser import LiveServer, obscura

LONG_NAME = "debian-live-" + "x" * 180 + "-amd64.iso"
SIX_HOURS = 6 * 3600


def torrent(**overrides):
    row = {
        "id": "a" * 40,
        "mode": "direct",
        "name": "row",
        "save_path": "/downloads",
        "move_destination": None,
        "move_error": None,
        "can_retry_move": False,
        "move_state": None,
        "total": 1 << 30,
        "downloaded": 1 << 29,
        "uploaded": 1 << 28,
        "peers": 3,
        "ratio": 0.5,
        "progress": 0.42,
        "state_code": "downloading",
        "last_upload_at": None,
        "download_rate": 1 << 20,
        "upload_rate": 1 << 10,
        "paused": False,
        "error": None,
    }
    return {**row, **overrides}


class FakeManager:
    def __init__(self, config):
        self.torrents = [
            torrent(id="a" * 40, name=LONG_NAME),
            torrent(
                id="b" * 40,
                mode="proxy",
                name="seed.iso",
                progress=1,
                ratio=1.23,
                state_code="seeding",
                last_upload_at=time.time() - SIX_HOURS,
            ),
        ]

    async def start(self):
        pass

    async def close(self):
        pass

    def state(self):
        return {
            "torrents": self.torrents,
            "disks": [],
            "proxy": {"tcp": True, "udp": True, "checked_at": time.time()},
            "errors": [],
            "seeding": 1,
            "download_rate": 0,
            "upload_rate": 0,
            "global_ratio": 0,
        }


# Runs synchronously in the page once obscura has settled: click, then measure.
MEASURE = r"""
(() => { try {
  const list = document.getElementById("torrent-list");
  const button = document.getElementById("compact-toggle");
  const box = (node) => {
    const r = node.getBoundingClientRect();
    return { left: r.left, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
  };
  // obscura has no overflow scrollWidth: measure the text through a clone.
  const naturalWidth = (node) => {
    const clone = node.cloneNode(true);
    clone.style.cssText =
      "position:absolute;visibility:hidden;width:max-content;white-space:nowrap";
    document.body.append(clone);
    const width = clone.getBoundingClientRect().width;
    clone.remove();
    return width;
  };
  const shown = (node) => !!node && node.getClientRects().length > 0;
  const parts = {
    name: ".torrent-name", ratio: ".torrent-ratio", percent: ".torrent-percent",
    bar: "progress", down: ".torrent-down", up: ".torrent-up",
    activity: ".torrent-activity", actions: ".torrent-actions",
  };
  const hidden = [".badge", ".torrent-size", ".torrent-peers", ".torrent-volumes",
    ".torrent-state", ".torrent-path"];
  const snap = () => ({
    compact: list.classList.contains("compact"),
    pressed: button.getAttribute("aria-pressed"),
    icons: ["normal", "compact"].filter((icon) =>
      shown(button.querySelector(`.icon-${icon}`))),
    labelsShown: shown(document.getElementById("table-labels")),
    rows: [...list.querySelectorAll(".torrent-row")].map((row) => {
      const name = row.querySelector(".torrent-name");
      return {
        name: name.textContent,
        row: box(row),
        parts: Object.fromEntries(Object.entries(parts).map(([key, sel]) => {
          const node = row.querySelector(sel);
          return [key, { shown: shown(node), ...box(node) }];
        })),
        hiddenShown: hidden.filter((sel) => shown(row.querySelector(sel))),
        ellipsis: getComputedStyle(name).textOverflow,
        naturalWidth: naturalWidth(name),
        activity: row.querySelector(".torrent-activity").textContent,
      };
    }),
  });
  const language = document.getElementById("language-toggle");
  const result = {
    width: window.innerWidth,
    toggle: {
      inHeader: !!button.closest(".header"),
      afterLanguage: language.nextElementSibling === button,
      language: box(language),
      button: box(button),
    },
    normal: snap(),
  };
  button.click();
  result.compact = snap();
  button.click();
  result.back = snap();
  return JSON.stringify(result);
} catch (error) { return JSON.stringify({ error: String(error) }); } })()
"""


def by_name(snapshot):
    return {
        ("long" if row["name"] == LONG_NAME else "seed"): row
        for row in snapshot["rows"]
    }


def test_dash_compact_003_one_line_rows_with_half_width_bar():
    with LiveServer(create_app(Config(), FakeManager)) as url:
        result = obscura(url, MEASURE)

    assert "error" not in result, result.get("error")
    assert result["width"] == 1280
    normal, compact, back = (
        by_name(result[key]) for key in ("normal", "compact", "back")
    )
    assert set(normal) == {"long", "seed"}

    toggle = result["toggle"]
    assert toggle["inHeader"] is True
    assert toggle["afterLanguage"] is True
    assert toggle["button"]["left"] >= toggle["language"]["left"] + toggle["language"]["width"]
    middle = lambda b: b["top"] + b["height"] / 2
    assert abs(middle(toggle["button"]) - middle(toggle["language"])) <= 1
    assert result["normal"]["pressed"] == "false"
    assert result["normal"]["icons"] == ["normal"]
    for row in normal.values():
        assert row["row"]["height"] > 56

    assert result["compact"]["compact"] is True
    assert result["compact"]["pressed"] == "true"
    assert result["compact"]["icons"] == ["compact"]
    assert result["compact"]["labelsShown"] is False
    order = ["name", "ratio", "percent", "bar", "down", "up", "activity", "actions"]
    for key, row in compact.items():
        parts = row["parts"]
        assert all(parts[p]["shown"] for p in order), (key, parts)
        assert max(parts[p]["top"] for p in order) < min(
            parts[p]["bottom"] for p in order
        ), key
        lefts = [parts[p]["left"] for p in order]
        assert lefts == sorted(lefts), (key, lefts)
        assert row["row"]["height"] <= 56, key
        assert row["hiddenShown"] == [], key
        normal_bar = normal[key]["parts"]["bar"]["width"]
        assert abs(parts["bar"]["width"] - normal_bar / 2) <= 1, key
        assert parts["name"]["width"] > normal[key]["parts"]["name"]["width"], key
    long_name = compact["long"]
    assert long_name["ellipsis"] == "ellipsis"
    assert long_name["naturalWidth"] > long_name["parts"]["name"]["width"]
    assert compact["seed"]["activity"] == "6h ago"
    assert compact["long"]["activity"] == "Never shared"

    assert result["back"]["compact"] is False
    assert result["back"]["pressed"] == "false"
    assert result["back"]["icons"] == ["normal"]
    for key, row in back.items():
        assert (
            abs(row["parts"]["bar"]["width"] - normal[key]["parts"]["bar"]["width"])
            <= 1
        ), key
