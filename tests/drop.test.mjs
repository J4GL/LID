import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";
const source = await readFile(
  new URL("../app/static/drop.js", import.meta.url),
  "utf8",
);
const { installDropZones } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
function fixture() {
  const handlers = {},
    calls = [],
    overlay = { hidden: true };
  const target = {
    innerWidth: 1000,
    innerHeight: 800,
    addEventListener: (name, fn) => {
      handlers[name] = fn;
    },
  };
  const zones = ["direct", "proxy"].map((mode) => ({
    dataset: { dropMode: mode },
    classList: { remove() {}, toggle() {} },
  }));
  installDropZones({
    target,
    overlay,
    zones,
    onFiles: (files, mode) => calls.push({ files, mode }),
  });
  const event = (zone, types = ["Files"]) => ({
    preventDefault() {},
    target: { closest: () => zone },
    dataTransfer: { types, files: [{ name: "test.torrent" }] },
    clientX: 100,
    clientY: 100,
  });
  return { handlers, overlay, zones, calls, event };
}
test("left direct / right proxy, no second implicit addition", () => {
  for (const index of [0, 1]) {
    const f = fixture();
    f.handlers.dragenter(f.event(f.zones[index]));
    assert.equal(f.overlay.hidden, false);
    f.handlers.drop(f.event(f.zones[index]));
    assert.equal(f.overlay.hidden, true);
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].mode, index === 0 ? "direct" : "proxy");
    f.handlers.drop(f.event(null));
    assert.equal(f.calls.length, 1);
  }
});
test("nested drag events and Escape do not leave overlay stuck", () => {
  const f = fixture(),
    e = f.event(f.zones[0]);
  f.handlers.dragenter(e);
  f.handlers.dragenter(e);
  f.handlers.dragleave(e);
  assert.equal(f.overlay.hidden, false);
  f.handlers.keydown({ key: "Escape" });
  assert.equal(f.overlay.hidden, true);
  assert.equal(f.calls.length, 0);
});
test("text drag does not trigger file drop UI", () => {
  const f = fixture();
  f.handlers.dragenter(f.event(null, ["text/plain"]));
  assert.equal(f.overlay.hidden, true);
});
