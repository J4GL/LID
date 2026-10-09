import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";
const source = await readFile(
  new URL("../app/static/add-route.js", import.meta.url),
  "utf8",
);
const { createRoutePicker } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
function element(dataset = {}) {
  const classes = new Set(),
    attributes = {},
    handlers = {};
  return {
    dataset,
    classes,
    attributes,
    focused: false,
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
    },
    setAttribute: (name, value) => (attributes[name] = value),
    addEventListener: (name, fn) => (handlers[name] = fn),
    focus() {
      this.focused = true;
    },
    click: () => handlers.click?.(),
  };
}
test("ADD-ROUTE-001 asks for a route instead of staying disabled", () => {
  const picker = element(),
    direct = element({ mode: "direct" }),
    proxy = element({ mode: "proxy" }),
    missing = [],
    selected = [];
  const route = createRoutePicker({
    picker,
    choices: [direct, proxy],
    onMissing: () => missing.push(true),
    onSelect: (mode) => selected.push(mode),
  });
  route.reset();

  assert.equal(route.require(), null);
  assert.equal(missing.length, 1);
  assert.ok(picker.classes.has("needs-route"));
  assert.equal(direct.focused, true);

  proxy.click();
  assert.equal(route.mode, "proxy");
  assert.equal(proxy.attributes["aria-pressed"], "true");
  assert.equal(direct.attributes["aria-pressed"], "false");
  assert.equal(picker.classes.has("needs-route"), false);
  assert.deepEqual(selected, ["proxy"]);

  assert.equal(route.require(), "proxy");
  assert.equal(missing.length, 1);

  route.reset();
  assert.equal(route.mode, null);
  assert.equal(direct.attributes["aria-pressed"], "false");
  assert.equal(proxy.attributes["aria-pressed"], "false");
  assert.equal(picker.classes.has("needs-route"), false);
});
