import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";
import { resolveObjectURL } from "node:buffer";
import { runInNewContext } from "node:vm";

import {
  classifyLink,
  fetchableHttpUrl,
  isTorrentDownload,
  trackerOrigin,
} from "../extension/classify.js";

test("EXT-CAP-000 manifest declares narrow MV3 permissions", async () => {
  const manifest = JSON.parse(
    await readFile(new URL("../extension/manifest.json", import.meta.url), "utf8"),
  );
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(
    [...manifest.permissions].sort(),
    ["contextMenus", "downloads", "notifications", "scripting", "storage"],
  );
  assert.deepEqual(manifest.host_permissions, [
    "http://192.168.1.29:8000/*",
  ]);
  assert.deepEqual(manifest.optional_host_permissions, [
    "http://*/*",
    "https://*/*",
  ]);
  assert.ok(!("content_scripts" in manifest));
});

test("EXT-CAP-001 recognizes torrent downloads and extractable urls", () => {
  const httpItem = {
    filename: "ubuntu.iso.torrent",
    mime: "application/octet-stream",
    url: "https://tracker.example/get?id=1",
    finalUrl: "https://cdn.example/ubuntu.iso.torrent",
  };
  const mimeItem = {
    filename: "download.bin",
    mime: "application/x-bittorrent",
    url: "https://tracker.example/dl",
    finalUrl: "",
  };
  const blobItem = {
    filename: "x.torrent",
    mime: "application/x-bittorrent",
    url: "blob:https://tracker.example/uuid",
    finalUrl: "",
  };
  const plainItem = {
    filename: "movie.mkv",
    mime: "video/x-matroska",
    url: "https://tracker.example/movie.mkv",
    finalUrl: "",
  };
  assert.equal(isTorrentDownload(httpItem), true);
  assert.equal(
    fetchableHttpUrl(httpItem),
    "https://cdn.example/ubuntu.iso.torrent",
  );
  assert.equal(isTorrentDownload(mimeItem), true);
  assert.equal(fetchableHttpUrl(mimeItem), "https://tracker.example/dl");
  assert.equal(isTorrentDownload(blobItem), true);
  assert.equal(fetchableHttpUrl(blobItem), null);
  assert.equal(isTorrentDownload(plainItem), false);
});

test("EXT-CAP-002 classifies context menu links", () => {
  assert.equal(classifyLink("magnet:?xt=urn:btih:abc123"), "magnet");
  assert.equal(
    classifyLink("https://tracker.example:8443/x.torrent?pass=1"),
    "file",
  );
  assert.equal(classifyLink("https://tracker.example/browse"), null);
  assert.equal(classifyLink(""), null);
  assert.equal(
    trackerOrigin("https://tracker.example:8443/x.torrent?pass=1"),
    "https://tracker.example:8443",
  );
  assert.equal(trackerOrigin("http://tracker.example/x.torrent"), "http://tracker.example");
});

test("EXT-CAP-003 blob hook retains bytes after object URL revocation", async () => {
  const source = await readFile(
    new URL("../extension/blob-hook.js", import.meta.url),
    "utf8",
  );
  let fetchCalls = 0;
  const page = {
    URL: {
      createObjectURL: URL.createObjectURL.bind(URL),
      revokeObjectURL: URL.revokeObjectURL.bind(URL),
    },
    fetch: () => {
      fetchCalls++;
      throw new Error("Page CSP forbids fetch");
    },
  };
  page.window = page;
  runInNewContext(source, page, { filename: "blob-hook.js" });
  const bytes = new Uint8Array([0, 1, 127, 128, 254, 255]);
  const url = page.URL.createObjectURL(new Blob([bytes]));
  try {
    assert.ok(resolveObjectURL(url));
    page.URL.revokeObjectURL(url);
    assert.equal(resolveObjectURL(url), undefined);
    const retained = page.__lidBlobs.get(url);
    assert.ok(retained instanceof Blob);
    assert.deepEqual(new Uint8Array(await retained.arrayBuffer()), bytes);
    assert.equal(fetchCalls, 0);
  } finally {
    page.URL.revokeObjectURL(url);
  }
});

test("EXT-CAP-004 blob hook records the last click anchor", async () => {
  const source = await readFile(
    new URL("../extension/blob-hook.js", import.meta.url),
    "utf8",
  );
  const listeners = {};
  const page = {
    URL: {
      createObjectURL: URL.createObjectURL.bind(URL),
      revokeObjectURL: URL.revokeObjectURL.bind(URL),
    },
    Date: { now: () => 1234 },
    addEventListener: (type, fn, options) => {
      listeners[type] = { fn, options };
    },
  };
  page.window = page;
  runInNewContext(source, page, { filename: "blob-hook.js" });
  const element = (rect, ancestor) => ({
    getBoundingClientRect: () => rect,
    closest: () => ancestor || element(rect, null),
  });
  const link = { getBoundingClientRect: () => ({ left: 40, right: 120, bottom: 60 }) };
  link.closest = () => link;

  assert.equal(listeners.pointerdown.options, true);
  assert.equal(listeners.contextmenu.options, true);

  listeners.pointerdown.fn({
    target: link,
    screenX: 540,
    screenY: 320,
    clientX: 50,
    clientY: 30,
  });
  assert.deepEqual(
    { ...page.__lidLastClick },
    { left: 530, right: 610, bottom: 350, at: 1234 },
  );

  const button = { getBoundingClientRect: () => ({ left: 10, right: 90, bottom: 44 }) };
  button.closest = () => button;
  listeners.contextmenu.fn({
    target: element({ left: 30, right: 40, bottom: 30 }, button),
    screenX: 300,
    screenY: 200,
    clientX: 20,
    clientY: 20,
  });
  assert.deepEqual(
    { ...page.__lidLastClick },
    { left: 290, right: 370, bottom: 224, at: 1234 },
  );

  listeners.pointerdown.fn({
    target: link,
    screenX: 0,
    screenY: 0,
    clientX: 0,
    clientY: 0,
  });
  assert.deepEqual(
    { ...page.__lidLastClick },
    { left: 290, right: 370, bottom: 224, at: 1234 },
  );
});

test("EXT-CAP-005 magnet hook hands magnet clicks to the worker", async () => {
  const source = await readFile(
    new URL("../extension/magnet-hook.js", import.meta.url),
    "utf8",
  );
  const MAGNET = "magnet:?xt=urn:btih:abc&dn=Ubuntu";
  let listeners = [];
  const sent = [];
  const page = {
    addEventListener: (type, fn, options) => listeners.push({ type, fn, options }),
    removeEventListener: (type, fn, options) => {
      listeners = listeners.filter(
        (l) => !(l.type === type && l.fn === fn && l.options === options),
      );
    },
    chrome: { runtime: { sendMessage: (message) => sent.push({ ...message }) } },
  };
  page.window = page;
  page.globalThis = page;
  runInNewContext(source, page, { filename: "magnet-hook.js" });
  const anchor = (href) => {
    const link = { href };
    const span = { closest: (selector) => (selector === "a[href]" ? link : null) };
    return span;
  };
  const click = (target, extra = {}) => {
    const event = {
      type: "click",
      target,
      isTrusted: true,
      button: 0,
      defaultPrevented: false,
      prevented: 0,
      preventDefault() {
        this.prevented++;
      },
      ...extra,
    };
    for (const entry of listeners.filter((l) => l.type === "click")) entry.fn(event);
    return event;
  };

  assert.equal(listeners.filter((l) => l.type === "click").length, 1);
  assert.equal(listeners[0].options, true);
  let event = click(anchor(MAGNET));
  assert.equal(event.prevented, 1);
  assert.deepEqual(sent, [{ type: "lid-magnet", magnet: MAGNET }]);

  for (const [label, target, extra] of [
    ["untrusted", anchor(MAGNET), { isTrusted: false }],
    ["already prevented", anchor(MAGNET), { defaultPrevented: true }],
    ["middle button", anchor(MAGNET), { button: 1 }],
    ["http link", anchor("https://site.example/x"), {}],
  ]) {
    event = click(target, extra);
    assert.equal(event.prevented, 0, label);
  }
  assert.equal(sent.length, 1);

  runInNewContext(source, page, { filename: "magnet-hook.js" });
  assert.equal(listeners.filter((l) => l.type === "click").length, 1);
  click(anchor(MAGNET));
  assert.equal(sent.length, 2);

  page.chrome.runtime.sendMessage = () => {
    throw new Error("Extension context invalidated.");
  };
  event = click(anchor(MAGNET));
  assert.equal(event.prevented, 0);
});
