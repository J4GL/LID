import pytest

from app.config import Config
from app.main import create_app
from tests.browser import LiveServer, obscura
from tests.test_dashboard_compact import FakeManager

GIB = 1 << 30


def disk(label, used_gib, total_gib):
    total, used = total_gib * GIB, used_gib * GIB
    return {
        "label": label,
        "path": f"/{label}",
        "total": total,
        "used": used,
        "free": total - used,
    }


def page_with(disks, script):
    class Manager(FakeManager):
        def state(self):
            return {**super().state(), "disks": disks}

    with LiveServer(create_app(Config(), Manager)) as url:
        result = obscura(url, script)
    assert "error" not in result, result.get("error")
    assert result["width"] == 1280
    return result


HELPERS = r"""
  const box = (node) => {
    const r = node.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, width: r.width, height: r.height };
  };
  const shown = (node) => !!node && node.getClientRects().length > 0;
  const text = (node) => node.textContent.replace(/\s+/g, " ").trim();
"""

FOOTER = (
    r"""
(() => { try {"""
    + HELPERS
    + r"""
  const footer = document.querySelector(".footer");
  const disk = document.getElementById("temporary-disk");
  const bar = disk.querySelector(".disk-bar");
  return JSON.stringify({
    width: window.innerWidth,
    shown: shown(disk),
    inFooter: footer.contains(disk),
    live: box(document.getElementById("live-label")),
    disk: box(disk),
    settings: box(document.getElementById("storage-button")),
    label: text(disk.querySelector(".disk-label")),
    text: text(disk.querySelector(".disk-text")),
    level: ["ok", "warn", "full"].filter((c) => bar.classList.contains(c)),
    bar: box(bar),
    fill: box(disk.querySelector(".disk-fill")),
    tagline: !!document.querySelector('[data-i18n="footer.tagline"]'),
    widget: !!document.getElementById("disk-widget"),
  });
} catch (error) { return JSON.stringify({ error: String(error) }); } })()
"""
)

CARD = (
    r"""
(() => { try {"""
    + HELPERS
    + r"""
  const metrics = [...document.querySelectorAll(".metrics > .metric")];
  const card = document.getElementById("destination-disk");
  const ratio = document.getElementById("global-ratio").closest(".metric");
  const pie = card.querySelector(".disk-pie");
  return JSON.stringify({
    width: window.innerWidth,
    shown: shown(card),
    index: metrics.indexOf(card),
    afterRatio: ratio.nextElementSibling === card,
    ratio: box(ratio),
    card: box(card),
    metrics: box(document.querySelector(".metrics")),
    label: text(card.querySelector('[data-i18n="metrics.destination"]')),
    percent: text(card.querySelector("strong")),
    note: text(card.querySelector(".metric-note")),
    pieShown: shown(pie),
    pie: box(pie),
    level: ["ok", "warn", "full"].filter((c) => pie.classList.contains(c)),
    dash: card.querySelector(".disk-pie-used").getAttribute("stroke-dasharray"),
    aria: pie.getAttribute("aria-label"),
  });
} catch (error) { return JSON.stringify({ error: String(error) }); } })()
"""
)

TWO_DISKS = [disk("downloads", 256, 512), disk("completed", 768, 1024)]


def test_disk_003_temporary_disk_in_footer():
    result = page_with(TWO_DISKS, FOOTER)
    assert result["shown"] is True
    assert result["inFooter"] is True
    assert result["live"]["right"] < result["disk"]["left"]
    assert result["disk"]["right"] < result["settings"]["left"]
    assert result["label"] == "Downloads"
    assert result["text"] == "256.0 GiB / 512.0 GiB"
    assert result["level"] == ["ok"]
    assert abs(result["fill"]["width"] - result["bar"]["width"] / 2) <= 1
    assert result["tagline"] is False
    assert result["widget"] is False

    result = page_with([disk("downloads", 471, 512)], FOOTER)
    assert result["text"] == "471.0 GiB / 512.0 GiB"
    assert result["level"] == ["full"]

    assert page_with([], FOOTER)["shown"] is False


@pytest.mark.parametrize(
    "disks, expected",
    [
        (TWO_DISKS, ("75 %", "768.0 GiB / 1.0 TiB", "ok", "75.0 100")),
        ([disk("downloads", 435, 512)], ("85 %", "435.0 GiB / 512.0 GiB", "warn", "85.0 100")),
        ([], None),
    ],
    ids=["completed", "downloads-only", "no-disks"],
)
def test_disk_004_destination_disk_pie_card(disks, expected):
    result = page_with(disks, CARD)
    if expected is None:
        assert result["shown"] is False
        assert abs(result["ratio"]["right"] - result["metrics"]["right"]) <= 1
        return
    percent, note, level, dash = expected
    assert result["shown"] is True
    assert result["index"] == 4
    assert result["afterRatio"] is True
    assert abs(result["card"]["top"] - result["ratio"]["top"]) <= 1
    assert result["card"]["left"] >= result["ratio"]["right"] - 1
    assert result["label"] == "Destination disk"
    assert result["percent"] == percent
    assert result["note"] == note
    assert result["pieShown"] is True
    assert result["pie"]["width"] >= 40 and result["pie"]["height"] >= 40
    assert result["level"] == [level]
    assert result["dash"] == dash
    assert result["aria"] == f"Destination disk: {percent} used"
