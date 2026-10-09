import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";
const source = await readFile(
  new URL("../app/static/compact.js", import.meta.url),
  "utf8",
);
const { installCompactToggle } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
function element() {
  const classes = new Set(),
    attributes = {},
    handlers = {};
  return {
    classes,
    attributes,
    classList: {
      toggle: (name, force) => {
        if (force) classes.add(name);
        else classes.delete(name);
      },
    },
    setAttribute: (name, value) => (attributes[name] = value),
    addEventListener: (name, fn) => (handlers[name] = fn),
    click: () => handlers.click?.(),
  };
}
function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}
const brokenStorage = {
  getItem() {
    throw new Error("blocked");
  },
  setItem() {
    throw new Error("blocked");
  },
};
test("DASH-COMPACT-001 toggles and remembers the compact view", async (t) => {
  await t.test("empty storage starts normal, clicks toggle and persist", () => {
    const button = element(),
      list = element(),
      storage = memoryStorage();
    installCompactToggle({ button, list, storage });
    assert.equal(button.attributes["aria-pressed"], "false");
    assert.equal(list.classes.has("compact"), false);

    button.click();
    assert.equal(list.classes.has("compact"), true);
    assert.equal(button.attributes["aria-pressed"], "true");
    assert.equal(storage.values.get("p2p-compact"), "1");

    button.click();
    assert.equal(list.classes.has("compact"), false);
    assert.equal(button.attributes["aria-pressed"], "false");
    assert.equal(storage.values.get("p2p-compact"), "0");
  });

  await t.test("a stored choice starts compact", () => {
    const button = element(),
      list = element();
    installCompactToggle({
      button,
      list,
      storage: memoryStorage({ "p2p-compact": "1" }),
    });
    assert.equal(list.classes.has("compact"), true);
    assert.equal(button.attributes["aria-pressed"], "true");
  });

  await t.test("a throwing storage starts normal and still toggles", () => {
    const button = element(),
      list = element();
    assert.doesNotThrow(() =>
      installCompactToggle({ button, list, storage: brokenStorage }),
    );
    assert.equal(list.classes.has("compact"), false);
    button.click();
    assert.equal(list.classes.has("compact"), true);
    assert.equal(button.attributes["aria-pressed"], "true");
  });
});
