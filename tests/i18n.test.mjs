import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const storage = new Map();
globalThis.localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
};
globalThis.document = {
  documentElement: { lang: "" },
  title: "",
  querySelectorAll: () => [],
  getElementById: () => null,
};

const source = await readFile(
  new URL("../app/static/i18n.js", import.meta.url),
  "utf8",
);
const i18n = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

test("English is the default and the French choice is persisted", () => {
  i18n.initI18n();
  assert.equal(i18n.getLanguage(), "en");
  assert.equal(i18n.t("metrics.ratio"), "Global ratio");
  assert.equal(document.documentElement.lang, "en");
  assert.equal(document.title, "LID — Linux ISO Downloader");

  i18n.setLanguage("fr");
  assert.equal(i18n.t("metrics.ratio"), "Ratio global");
  assert.equal(storage.get("p2p-language"), "fr");
  assert.equal(document.documentElement.lang, "fr");
  assert.equal(
    i18n.t("torrent.last_upload", { value: "il y a 6 h" }),
    "Dernier envoi : il y a 6 h",
  );

  i18n.setLanguage("en");
  assert.equal(
    i18n.t("torrent.last_upload", { value: "6h ago" }),
    "Last upload: 6h ago",
  );
  assert.equal(storage.get("p2p-language"), "en");
  assert.equal(
    i18n.localizedError("storage_full"),
    "Not enough space on the destination disk. Files remain in their current folder.",
  );
});

test("the initial document is English and exposes translatable controls", async () => {
  const html = await readFile(
    new URL("../app/static/index.html", import.meta.url),
    "utf8",
  );
  assert.match(html, /<html lang="en">/);
  assert.match(html, /id="language-toggle"/);
  assert.match(html, /id="global-ratio"/);
  assert.match(html, /data-i18n="folders\.title"/);
  assert.match(html, /data-i18n-aria="list\.aria"/);
});
