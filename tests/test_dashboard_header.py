from app.config import Config
from app.main import create_app
from tests.browser import LiveServer, obscura
from tests.test_dashboard_compact import FakeManager

# Runs synchronously in the page once obscura has settled: measure, then click.
MEASURE = r"""
(() => { try {
  const box = (node) => {
    const r = node.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom,
      width: r.width, height: r.height };
  };
  const header = document.querySelector(".header");
  const button = document.getElementById("add-button");
  const h1 = document.querySelector("h1");
  const result = {
    width: window.innerWidth,
    pageHeading: !!document.querySelector(".page-heading"),
    dashboardLabel: !!document.querySelector('[data-i18n="dashboard"]'),
    h1: { text: h1.textContent.trim(), ...box(h1) },
    inHeader: header.contains(button),
    shown: button.getClientRects().length > 0,
    header: box(header),
    brand: box(document.querySelector(".brand")),
    label: box(document.querySelector(".header-label")),
    language: box(document.getElementById("language-toggle")),
    button: box(button),
  };
  button.click();
  result.dialogOpen = document.getElementById("add-dialog").open;
  return JSON.stringify(result);
} catch (error) { return JSON.stringify({ error: String(error) }); } })()
"""


def center_x(b):
    return b["left"] + b["width"] / 2


def center_y(b):
    return b["top"] + b["height"] / 2


def test_dash_header_001_add_button_centered_in_header():
    with LiveServer(create_app(Config(), FakeManager)) as url:
        result = obscura(url, MEASURE)

    assert "error" not in result, result.get("error")
    assert result["width"] == 1280
    assert result["pageHeading"] is False
    assert result["dashboardLabel"] is False
    assert result["h1"]["text"] == "Transfers"
    assert result["h1"]["width"] <= 1 and result["h1"]["height"] <= 1
    assert result["inHeader"] is True
    assert result["shown"] is True
    button = result["button"]
    assert abs(center_x(button) - center_x(result["header"])) <= 1
    assert abs(center_y(button) - center_y(result["brand"])) <= 1
    assert result["label"]["right"] < button["left"]
    assert button["right"] < result["language"]["left"]
    assert result["dialogOpen"] is True
