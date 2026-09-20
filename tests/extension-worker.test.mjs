import assert from "node:assert/strict";
import test from "node:test";

function makeChrome() {
  const calls = {
    cancel: [],
    erase: [],
    windows: [],
    notifications: [],
    menus: [],
  };
  const listeners = {};
  const session = new Map();
  const chrome = {
    downloads: {
      onCreated: { addListener: (fn) => (listeners.download = fn) },
      cancel: async (id) => calls.cancel.push(id),
      erase: async (query) => {
        calls.erase.push(query);
        return [query.id];
      },
    },
    contextMenus: {
      create: (item) => calls.menus.push(item),
      onClicked: { addListener: (fn) => (listeners.menu = fn) },
    },
    runtime: {
      onInstalled: { addListener: (fn) => (listeners.installed = fn) },
      onMessage: { addListener: (fn) => (listeners.message = fn) },
      getURL: (path) => `chrome-extension://test/${path}`,
    },
    storage: {
      sync: {
        get: async (defaults) => ({
          ...defaults,
          serverUrl: "http://192.168.1.29:8000/",
        }),
        set: async () => {},
      },
      session: {
        get: async (key) =>
          session.has(key) ? { [key]: session.get(key) } : {},
        set: async (obj) => {
          for (const [key, value] of Object.entries(obj)) session.set(key, value);
        },
        remove: async (key) => {
          session.delete(key);
        },
      },
    },
    windows: {
      create: async (options) => {
        calls.windows.push(options);
        return options;
      },
    },
    notifications: {
      create: async (id, options) => {
        calls.notifications.push({ id, ...options });
        return id;
      },
    },
    i18n: {
      getMessage: (key, substitutions) =>
        Array.isArray(substitutions) ? `${key}:${substitutions.join(",")}` : key,
      getUILanguage: () => "fr",
    },
  };
  return { chrome, calls, listeners, session };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 20));

test("EXT-SW-001 worker intercepts stores pending and sends", async () => {
  const { chrome, calls, listeners, session } = makeChrome();
  globalThis.chrome = chrome;
  const fetched = [];
  globalThis.fetch = async (url, options = {}) => {
    fetched.push({ url, options });
    if (url.endsWith("/api/bootstrap")) {
      return { ok: true, status: 200, json: async () => ({ token: "t" }) };
    }
    if (url.endsWith("/api/torrents/files")) {
      return {
        ok: true,
        status: 201,
        json: async () => ({
          results: [{ name: "x.torrent", ok: true, id: "a".repeat(40) }],
        }),
      };
    }
    return {
      ok: true,
      status: 200,
      headers: { get: (name) => (name === "content-length" ? "4" : null) },
      arrayBuffer: async () => new Uint8Array([1, 2, 3, 4]).buffer,
    };
  };
  await import("../extension/background.js");

  listeners.installed();
  assert.deepEqual(calls.menus, [
    { id: "lid-send", title: "menu_send", contexts: ["link"] },
  ]);

  await listeners.download({
    id: 7,
    filename: "ubuntu.iso.torrent",
    mime: "application/octet-stream",
    url: "https://tracker.example/get?id=1",
    finalUrl: "https://cdn.example/ubuntu.iso.torrent",
  });
  await flush();
  assert.deepEqual(calls.cancel, [7]);
  assert.deepEqual(calls.erase, [{ id: 7 }]);
  assert.equal(session.size, 1);
  const [[pendingId, pending]] = [...session.entries()];
  assert.equal(pending.kind, "file");
  assert.equal(pending.url, "https://cdn.example/ubuntu.iso.torrent");
  assert.equal(calls.windows.length, 1);
  assert.match(calls.windows[0].url, /route\.html\?id=/);
  assert.equal(calls.windows[0].type, "popup");

  await listeners.download({
    id: 8,
    filename: "y.torrent",
    mime: "application/x-bittorrent",
    url: "blob:https://tracker.example/uuid",
    finalUrl: "",
  });
  await listeners.download({
    id: 9,
    filename: "movie.mkv",
    mime: "video/x-matroska",
    url: "https://tracker.example/movie.mkv",
    finalUrl: "",
  });
  await flush();
  assert.deepEqual(calls.cancel, [7]);
  assert.ok(calls.notifications.some((note) => note.id === "lid-blob-8"));

  await listeners.menu({
    menuItemId: "lid-send",
    linkUrl: "magnet:?xt=urn:btih:abc&dn=Show",
  });
  await flush();
  assert.equal(session.size, 2);
  assert.equal(calls.windows.length, 2);
  assert.equal(fetched.length, 0);

  const reply = await new Promise((resolve) => {
    const alive = listeners.message(
      { type: "lid-send", id: pendingId, mode: "proxy" },
      {},
      resolve,
    );
    assert.equal(alive, true);
  });
  assert.equal(reply.ok, true);
  assert.equal(fetched[0].url, "https://cdn.example/ubuntu.iso.torrent");
  assert.ok(fetched[1].url.endsWith("/api/bootstrap"));
  assert.ok(fetched[2].url.endsWith("/api/torrents/files"));
  assert.equal(fetched[2].options.body.get("mode"), "proxy");
  assert.equal(session.has(pendingId), false);
  assert.ok(
    calls.notifications.some((note) => note.id === `lid-ok-${pendingId}`),
  );

  const before = fetched.length;
  const missing = await new Promise((resolve) => {
    listeners.message({ type: "lid-send", id: "nope", mode: "direct" }, {}, resolve);
  });
  assert.equal(missing.ok, false);
  assert.equal(fetched.length, before);
});
