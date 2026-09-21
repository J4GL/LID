import assert from "node:assert/strict";
import test from "node:test";
import { messageFor } from "../extension/messages.js";

function makeChrome() {
  const calls = {
    cancel: [],
    erase: [],
    windows: [],
    notifications: [],
    menus: [],
    tabQueries: [],
    injections: [],
    registrations: [],
    updates: [],
  };
  const listeners = {};
  const session = new Map();
  const chrome = {
    downloads: {
      onCreated: { addListener: (fn) => (listeners.download = fn) },
      onChanged: { addListener: (fn) => (listeners.changed = fn) },
      onDeterminingFilename: {
        addListener: (fn) => (listeners.filename = fn),
      },
      search: async () => [],
      cancel: (id, callback) => {
        calls.cancel.push(id);
        callback?.();
      },
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
    tabs: {
      query: async (query) => {
        calls.tabQueries.push(query);
        return [];
      },
    },
    scripting: {
      executeScript: async (injection) => {
        calls.injections.push(injection);
        return [{ result: "" }];
      },
      getRegisteredContentScripts: async () => [],
      registerContentScripts: async (scripts) => {
        calls.registrations.push(scripts);
      },
      updateContentScripts: async (scripts) => {
        calls.updates.push(scripts);
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
    referrer: "https://tracker.example/t/1",
    state: "in_progress",
  });
  await listeners.download({
    id: 9,
    filename: "z.torrent",
    mime: "application/x-bittorrent",
    url: "data:application/x-bittorrent;base64,AA==",
    finalUrl: "",
  });
  await listeners.download({
    id: 10,
    filename: "movie.mkv",
    mime: "video/x-matroska",
    url: "https://tracker.example/movie.mkv",
    finalUrl: "",
  });
  await flush();
  assert.deepEqual(calls.cancel, [7, 8]);
  assert.equal(session.size, 2);
  assert.equal(calls.windows.length, 2);
  assert.ok(calls.notifications.some((note) => note.id === "lid-blob-9"));

  await listeners.menu({
    menuItemId: "lid-send",
    linkUrl: "magnet:?xt=urn:btih:abc&dn=Show",
  });
  await flush();
  assert.equal(session.size, 3);
  assert.equal(calls.windows.length, 3);
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

test("EXT-SW-002 worker intercepts late torrent filenames once", async () => {
  const { chrome, calls, listeners, session } = makeChrome();
  chrome.downloads.search = async ({ id }) =>
    id === 21
      ? [
          {
            id: 21,
            filename: "",
            mime: "application/octet-stream",
            url: "https://tracker.example/get?id=9",
            finalUrl: "",
          },
        ]
      : [];
  globalThis.chrome = chrome;
  globalThis.fetch = async () => {
    throw new Error("no network in capture test");
  };
  // Fresh module instance (query busts the import cache), like a worker restart.
  await import("../extension/background.js?sw2");

  await listeners.download({
    id: 21,
    filename: "",
    mime: "",
    url: "https://tracker.example/get?id=9",
    finalUrl: "",
  });
  await flush();
  assert.deepEqual(calls.cancel, []);
  assert.equal(calls.windows.length, 0);

  await listeners.changed({
    id: 21,
    filename: { previous: "", current: "late.torrent" },
    mime: { current: "application/octet-stream" },
    finalUrl: { current: "https://cdn.example/late.torrent" },
  });
  await flush();
  assert.deepEqual(calls.cancel, [21]);
  assert.deepEqual(calls.erase, [{ id: 21 }]);
  assert.equal(session.size, 1);
  const [[, pending]] = [...session.entries()];
  assert.equal(pending.url, "https://cdn.example/late.torrent");
  assert.equal(pending.name, "late.torrent");
  assert.equal(calls.windows.length, 1);

  await listeners.changed({ id: 21, filename: { current: "late.torrent" } });
  await listeners.download({
    id: 21,
    filename: "late.torrent",
    mime: "application/octet-stream",
    url: "https://tracker.example/get?id=9",
    finalUrl: "https://cdn.example/late.torrent",
  });
  await flush();
  assert.equal(calls.windows.length, 1);
  assert.equal(session.size, 1);

  await listeners.changed({ id: 22, filename: { current: "notes.txt" } });
  await flush();
  assert.deepEqual(calls.cancel, [21]);
  assert.equal(calls.windows.length, 1);
  assert.equal(calls.notifications.length, 0);

  await listeners.changed({ id: 22, state: { current: "complete" } });
  await flush();
  assert.deepEqual(calls.cancel, [21]);
  assert.equal(calls.windows.length, 1);
  assert.equal(calls.notifications.length, 0);

  chrome.downloads.search = async () => [{
    id: 23,
    filename: "download",
    mime: "application/octet-stream",
    url: "https://tracker.example/get?id=23",
  }];
  await listeners.changed({ id: 23, mime: { current: "application/x-bittorrent" } });
  await flush();
  assert.deepEqual(calls.cancel, [21, 23]);
  assert.deepEqual(calls.erase, [{ id: 21 }, { id: 23 }]);
  assert.equal(calls.windows.length, 2);
  assert.equal(session.size, 2);
  assert.equal([...session.values()][1].url, "https://tracker.example/get?id=23");
});

test("EXT-SW-003 worker reads page blobs and sends them", async () => {
  const { chrome, calls, listeners, session } = makeChrome();
  let tabs = [{ id: 77, url: "https://site.example/torrents/1" }];
  chrome.tabs.query = async (query) => {
    calls.tabQueries.push(query);
    return tabs;
  };
  chrome.scripting.executeScript = async (injection) => {
    calls.injections.push(injection);
    assert.equal(injection.world, "MAIN");
    assert.equal(injection.target.tabId, 77);
    assert.deepEqual(injection.args, ["blob:https://site.example/uuid"]);
    return [{ result: Buffer.from([1, 2, 3, 4]).toString("base64") }];
  };
  chrome.downloads.search = async ({ id }) =>
    id === 31 ? [{ id: 31, state: "complete" }] : [];
  globalThis.chrome = chrome;
  const fetched = [];
  globalThis.fetch = async (url, options = {}) => {
    fetched.push({ url, options });
    if (url.endsWith("/api/bootstrap")) {
      return { ok: true, status: 200, json: async () => ({ token: "t" }) };
    }
    return {
      ok: true,
      status: 201,
      json: async () => ({
        results: [{ name: "page.torrent", ok: true, id: "c".repeat(40) }],
      }),
    };
  };
  await import("../extension/background.js?sw3");

  await listeners.download({
    id: 31,
    filename: "",
    mime: "application/x-bittorrent",
    url: "blob:https://site.example/uuid",
    finalUrl: "",
    referrer: "https://site.example/torrents/1",
    state: "in_progress",
  });
  await flush();
  assert.deepEqual(calls.cancel, [31]);
  assert.deepEqual(calls.erase, [{ id: 31 }]);
  assert.equal(session.size, 1);
  const [[blobId, pending]] = [...session.entries()];
  assert.equal(pending.kind, "blob");
  assert.equal(pending.origin, "https://site.example");
  assert.equal(pending.downloadId, 31);
  assert.equal(calls.windows.length, 1);

  await listeners.changed({ id: 31, filename: { current: "page.torrent" } });
  await flush();
  assert.equal(session.get(blobId).name, "page.torrent");
  assert.equal(calls.windows.length, 1);

  const reply = await new Promise((resolve) => {
    listeners.message(
      { type: "lid-send", id: blobId, mode: "proxy" },
      {},
      resolve,
    );
  });
  assert.equal(reply.ok, true);
  assert.deepEqual(calls.tabQueries, [{ url: ["https://site.example/*"] }]);
  assert.equal(calls.injections.length, 1);
  assert.deepEqual(calls.cancel, [31]);
  assert.deepEqual(calls.erase, [{ id: 31 }, { id: 31 }]);
  const upload = fetched.find((call) => call.url.endsWith("/api/torrents/files"));
  assert.equal(upload.options.body.get("mode"), "proxy");
  assert.equal(session.has(blobId), false);
  const note = calls.notifications.find((entry) => entry.id === `lid-ok-${blobId}`);
  assert.match(note.message, /^notif_added_local:/);

  tabs = [];
  await listeners.download({
    id: 32,
    filename: "gone.torrent",
    mime: "application/x-bittorrent",
    url: "blob:https://site.example/uuid2",
    finalUrl: "",
    referrer: "",
    state: "in_progress",
  });
  await flush();
  const goneId = [...session.keys()].find((key) => key !== blobId);
  const cancelCount = calls.cancel.length;
  const eraseCount = calls.erase.length;
  const failed = await new Promise((resolve) => {
    listeners.message({ type: "lid-send", id: goneId, mode: "proxy" }, {}, resolve);
  });
  assert.equal(failed.ok, false);
  assert.equal(failed.code, "blob_no_tab");
  assert.equal(calls.cancel.length, cancelCount);
  assert.equal(calls.erase.length, eraseCount);
  assert.equal(session.has(goneId), true);
});

test("EXT-SW-004 worker prefetches blob bytes when permitted", async () => {
  const { chrome, calls, listeners, session } = makeChrome();
  let permitted = true;
  let tabs = [{ id: 77, url: "https://site.example/torrents/1" }];
  chrome.permissions = {
    contains: async () => permitted,
  };
  chrome.tabs.query = async (query) => {
    calls.tabQueries.push(query);
    return tabs;
  };
  chrome.scripting.executeScript = async (injection) => {
    calls.injections.push(injection);
    return [{ result: Buffer.from([5, 6, 7]).toString("base64") }];
  };
  chrome.downloads.search = async ({ id }) =>
    id === 41 ? [{ id: 41, state: "complete" }] : [];
  globalThis.chrome = chrome;
  const fetched = [];
  globalThis.fetch = async (url, options = {}) => {
    fetched.push({ url, options });
    if (url.endsWith("/api/bootstrap")) {
      return { ok: true, status: 200, json: async () => ({ token: "t" }) };
    }
    return {
      ok: true,
      status: 201,
      json: async () => ({
        results: [{ name: "early.torrent", ok: true, id: "d".repeat(40) }],
      }),
    };
  };
  await import("../extension/background.js?sw4");

  await listeners.download({
    id: 41,
    filename: "",
    mime: "application/x-bittorrent",
    url: "blob:https://site.example/uuid",
    finalUrl: "",
    referrer: "https://site.example/torrents/1",
    state: "in_progress",
  });
  await flush();
  assert.equal(calls.injections.length, 1);
  assert.equal(calls.windows.length, 1);
  const [[earlyId, earlyPending]] = [...session.entries()];
  tabs = [];

  const reply = await new Promise((resolve) => {
    listeners.message({ type: "lid-send", id: earlyId, mode: "proxy" }, {}, resolve);
  });
  assert.equal(reply.ok, true);
  assert.equal(calls.injections.length, 1);
  assert.equal(calls.tabQueries.length, 1);
  assert.deepEqual(calls.cancel, [41]);
  assert.deepEqual(calls.erase, [{ id: 41 }, { id: 41 }]);
  const upload = fetched.find((call) => call.url.endsWith("/api/torrents/files"));
  assert.equal(upload.options.body.get("mode"), "proxy");
  assert.equal(session.has(earlyId), false);
  const note = calls.notifications.find((entry) => entry.id === `lid-ok-${earlyId}`);
  assert.match(note.message, /^notif_added_local:/);

  session.set(earlyId, earlyPending);
  const stale = await new Promise((resolve) => {
    listeners.message({ type: "lid-send", id: earlyId, mode: "proxy" }, {}, resolve);
  });
  assert.equal(stale.ok, false);
  assert.equal(stale.code, "blob_no_tab");

  permitted = false;
  await listeners.download({
    id: 42,
    filename: "",
    mime: "application/x-bittorrent",
    url: "blob:https://site.example/uuid2",
    finalUrl: "",
    referrer: "",
    state: "in_progress",
  });
  await flush();
  assert.equal(calls.injections.length, 1);
  assert.equal(calls.windows.length, 2);
});

test("EXT-SW-005 worker reports revoked origin on blob send", async () => {
  const { chrome, calls, listeners, session } = makeChrome();
  let permitted = false;
  chrome.permissions = { contains: async () => permitted };
  chrome.tabs.query = async (query) => {
    calls.tabQueries.push(query);
    return [{ id: 9 }];
  };
  globalThis.chrome = chrome;
  globalThis.fetch = async () => {
    throw new Error("no network expected");
  };
  await import("../extension/background.js?sw5");

  await listeners.download({
    id: 51,
    filename: "revoked.torrent",
    mime: "application/x-bittorrent",
    url: "blob:https://site.example/uuid",
    finalUrl: "",
    referrer: "https://site.example/torrents/1",
    state: "in_progress",
  });
  await flush();
  const [revokedId] = [...session.keys()];
  assert.equal(calls.tabQueries.length, 0);
  const cancelCount = calls.cancel.length;
  const eraseCount = calls.erase.length;
  const denied = await new Promise((resolve) => {
    listeners.message(
      { type: "lid-send", id: revokedId, mode: "direct" },
      {},
      resolve,
    );
  });
  assert.equal(denied.ok, false);
  assert.equal(denied.code, "origin_revoked");
  assert.equal(calls.cancel.length, cancelCount);
  assert.equal(calls.erase.length, eraseCount);
  assert.equal(session.has(revokedId), true);

  permitted = true;
  const hidden = await new Promise((resolve) => {
    listeners.message(
      { type: "lid-send", id: revokedId, mode: "direct" },
      {},
      resolve,
    );
  });
  assert.equal(hidden.ok, false);
  assert.equal(hidden.code, "blob_no_tab");
});

test("EXT-SW-006 worker stashes page blobs past CSP and revoke", async () => {
  const { chrome, calls, listeners } = makeChrome();
  let registered = [];
  chrome.permissions = { contains: async () => true };
  chrome.tabs.query = async (query) => {
    calls.tabQueries.push(query);
    return [{ id: 77, url: "https://site.example/t" }];
  };
  chrome.scripting.getRegisteredContentScripts = async () => registered;
  chrome.scripting.registerContentScripts = async (scripts) => {
    calls.registrations.push(scripts);
    registered = scripts;
  };
  chrome.scripting.updateContentScripts = async (scripts) => {
    calls.updates.push(scripts);
    registered = [{ ...registered[0], matches: scripts[0].matches }];
  };
  globalThis.chrome = chrome;
  globalThis.fetch = async () => {
    throw new Error("no network expected");
  };
  await import("../extension/background.js?sw6");
  const ask = (message) =>
    new Promise((resolve) => listeners.message(message, {}, resolve));

  const first = await ask({
    type: "lid-register-hook",
    origin: "https://site.example",
  });
  assert.equal(first.ok, true);
  assert.equal(calls.registrations.length, 1);
  const [script] = calls.registrations[0];
  assert.equal(script.id, "lid-blob-hook");
  assert.deepEqual(script.js, ["blob-hook.js"]);
  assert.deepEqual(script.matches, ["https://site.example/*"]);
  assert.equal(script.world, "MAIN");
  assert.equal(script.runAt, "document_start");
  const hookInjection = calls.injections.find((entry) => entry.files);
  assert.deepEqual(hookInjection.files, ["blob-hook.js"]);
  assert.equal(hookInjection.world, "MAIN");
  assert.equal(hookInjection.target.tabId, 77);

  const second = await ask({
    type: "lid-register-hook",
    origin: "https://other.example",
  });
  assert.equal(second.ok, true);
  assert.equal(calls.registrations.length, 1);
  assert.equal(calls.updates.length, 1);
  assert.deepEqual(calls.updates[0][0].matches, [
    "https://site.example/*",
    "https://other.example/*",
  ]);

  assert.match(messageFor("blob_unavailable", "fr"), /Relancez/);
  assert.match(messageFor("blob_unavailable", "en"), /again/);

  await listeners.download({
    id: 61,
    filename: "",
    mime: "application/x-bittorrent",
    url: "blob:https://site.example/u",
    finalUrl: "",
    referrer: "https://site.example/t",
    state: "in_progress",
  });
  await flush();
  const read = calls.injections.find(
    (entry) => typeof entry.func === "function",
  ).func;
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("fetch must not run");
  };
  globalThis.__lidBlobs = new Map([
    ["blob:https://site.example/u", new Blob([new Uint8Array([9, 8, 7])])],
  ]);
  assert.equal(
    await read("blob:https://site.example/u"),
    Buffer.from([9, 8, 7]).toString("base64"),
  );
  delete globalThis.__lidBlobs;
  globalThis.fetch = async () => ({
    ok: true,
    blob: async () => new Blob([new Uint8Array([1, 2])]),
  });
  assert.equal(
    await read("blob:https://site.example/u"),
    Buffer.from([1, 2]).toString("base64"),
  );
  globalThis.fetch = realFetch;
});

const settle = () => new Promise((resolve) => setImmediate(resolve));

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

async function blobHarness(t, key) {
  const harness = {
    ...makeChrome(),
    permitted: false,
    tabs: [{ id: 10, url: "https://site.example/torrents/1" }],
    bytes: new Uint8Array([0, 1, 127, 128, 254, 255]),
    fetched: [],
    permissionQueries: [],
    uploadFailures: 0,
  };
  const { chrome, calls, listeners, session } = harness;
  harness.read = async () => [{ result: Buffer.from(harness.bytes).toString("base64") }];
  chrome.permissions = {
    contains: async (query) => {
      harness.permissionQueries.push(query);
      return harness.permitted;
    },
  };
  chrome.tabs.query = async (query) => {
    calls.tabQueries.push(query);
    return harness.tabs;
  };
  chrome.scripting.executeScript = async (injection) => {
    calls.injections.push(injection);
    return harness.read(injection);
  };
  const previousChrome = globalThis.chrome;
  globalThis.chrome = chrome;
  t.after(() => { globalThis.chrome = previousChrome; });
  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    harness.fetched.push({ url, options });
    if (url === "http://192.168.1.29:8000/api/bootstrap") {
      return { ok: true, status: 200, json: async () => ({ token: "t" }) };
    }
    if (url === "http://192.168.1.29:8000/api/torrents/files") {
      if (harness.uploadFailures > 0) {
        harness.uploadFailures--;
        return { ok: false, status: 503, json: async () => ({ code: "proxy_unavailable" }) };
      }
      return {
        ok: true,
        status: 201,
        json: async () => ({ results: [{ ok: true, id: "a".repeat(40), name: "page.torrent" }] }),
      };
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  await import(`../extension/background.js?blob-regression-${key}`);
  harness.capture = async (referrer = "https://site.example/torrents/1") => {
    listeners.download({
      id: 71,
      filename: "page.torrent",
      mime: "application/x-bittorrent",
      url: "blob:https://site.example/file",
      referrer,
      state: "in_progress",
    });
    await settle();
    assert.equal(session.size, 1);
    return [...session.keys()][0];
  };
  harness.send = (id) => new Promise((resolve) => {
    listeners.message({ type: "lid-send", id, mode: "proxy" }, {}, resolve);
  });
  harness.uploads = () => harness.fetched.filter(({ url }) => url.endsWith("/api/torrents/files"));
  harness.assertUploads = async (count) => {
    assert.equal(harness.uploads().length, count);
    for (const { options } of harness.uploads()) {
      assert.equal(options.body.get("mode"), "proxy");
      const file = options.body.get("files");
      assert.equal(file.name, "page.torrent");
      assert.deepEqual(new Uint8Array(await file.arrayBuffer()), harness.bytes);
    }
  };
  harness.successes = () => calls.notifications.filter(({ id }) => id.startsWith("lid-ok-"));
  return harness;
}

test("EXT-SW-007 worker finds blob bytes across tabs for proxy upload", async (t) => {
  const cases = [
    { name: "missing referrer, first tab throws", referrer: "", failure: "throw" },
    { name: "origin referrer, first tab has no result", referrer: "https://site.example/", failure: "missing" },
    { name: "stale referrer, first tab has empty bytes", referrer: "https://site.example/old", failure: "empty" },
    { name: "foreign referrer, first tab has invalid base64", referrer: "https://other.example/", failure: "invalid" },
    { name: "exact referrer prioritizes second tab", referrer: "https://site.example/torrents/2", visited: [20] },
    { name: "exact referrer fails then next tab succeeds", referrer: "https://site.example/torrents/1", failure: "throw" },
  ];
  for (const [index, scenario] of cases.entries()) {
    await t.test(scenario.name, async (t) => {
      const h = await blobHarness(t, `7-success-${index}`);
      h.tabs = [
        { id: 90 },
        { id: 91, url: "https://other.example/" },
        { id: 10, url: "https://site.example/torrents/1" },
        { id: 20, url: "https://site.example/torrents/2" },
        { id: 30, url: "https://site.example/torrents/3" },
      ];
      h.read = async ({ target }) => {
        if (target.tabId !== 20) {
          if (scenario.failure === "throw") throw new Error("Tab closed during injection");
          if (scenario.failure === "missing") return [{}];
          return [{ result: scenario.failure === "invalid" ? "%%%" : "" }];
        }
        return [{ result: Buffer.from(h.bytes).toString("base64") }];
      };
      const id = await h.capture(scenario.referrer);
      assert.equal(h.session.get(id).origin, "https://site.example");
      assert.equal(h.calls.windows.length, 1);
      assert.equal(h.calls.injections.length, 0);
      h.permitted = true;
      const reply = await h.send(id);
      assert.equal(reply.ok, true);
      assert.equal(reply.mode, "proxy");
      assert.deepEqual(h.calls.injections.map(({ target }) => target.tabId), scenario.visited || [10, 20]);
      for (const injection of h.calls.injections) {
        assert.equal(injection.world, "MAIN");
        assert.deepEqual(injection.args, ["blob:https://site.example/file"]);
      }
      assert.deepEqual(h.calls.tabQueries, [{ url: ["https://site.example/*"] }]);
      assert.ok(h.permissionQueries.every(({ origins }) => origins.length === 1 && origins[0] === "https://site.example/*"));
      await h.assertUploads(1);
      assert.equal(h.session.has(id), false);
      assert.equal(h.successes().length, 1);
    });
  }
  for (const code of ["origin_revoked", "blob_no_tab", "blob_unavailable"]) {
    await t.test(code, async (t) => {
      const h = await blobHarness(t, `7-${code}`);
      const id = await h.capture();
      h.permitted = code !== "origin_revoked";
      h.tabs = code === "blob_no_tab" ? [{ id: 90 }] : [
        { id: 10, url: "https://site.example/torrents/1" },
        { id: 20, url: "https://site.example/torrents/2" },
      ];
      h.read = async ({ target }) => {
        if (target.tabId === 10) throw new Error("Blob revoked");
        return [{ result: "" }];
      };
      const cancelled = h.calls.cancel.length;
      const erased = h.calls.erase.length;
      assert.deepEqual(await h.send(id), { ok: false, code });
      assert.equal(h.session.has(id), true);
      assert.equal(h.fetched.length, 0);
      assert.equal(h.calls.cancel.length, cancelled);
      assert.equal(h.calls.erase.length, erased);
      assert.deepEqual(h.calls.injections.map(({ target }) => target.tabId), code === "blob_unavailable" ? [10, 20] : []);
      assert.equal(h.successes().length, 0);
    });
  }
});

test("EXT-SW-008 worker shares blob reads and retains bytes for proxy retry", async (t) => {
  await t.test("proxy choice waits for early read while popup opens", async (t) => {
    const h = await blobHarness(t, "8-pending-read");
    h.permitted = true;
    h.uploadFailures = 1;
    const popup = deferred();
    const bytes = deferred();
    t.after(() => { popup.resolve(); bytes.resolve([]); });
    h.chrome.windows.create = (options) => {
      h.calls.windows.push(options);
      return popup.promise;
    };
    h.read = () => bytes.promise;
    const id = await h.capture();
    assert.equal(h.calls.windows.length, 1);
    assert.equal(h.calls.injections.length, 1, "read starts while popup opening is pending");
    assert.equal(h.fetched.length, 0);
    const pending = h.session.get(id);
    popup.resolve();
    let replied = false;
    const sending = h.send(id).then((reply) => { replied = true; return reply; });
    await settle();
    assert.equal(h.calls.injections.length, 1, "send shares the in-flight read");
    assert.equal(replied, false);
    assert.equal(h.fetched.length, 0);
    bytes.resolve([{ result: Buffer.from(h.bytes).toString("base64") }]);
    assert.deepEqual(await sending, { ok: false, code: "proxy_unavailable" });
    await h.assertUploads(1);
    assert.equal(h.session.has(id), true);
    assert.equal(h.successes().length, 0);
    h.tabs = [];
    const queries = h.calls.tabQueries.length;
    assert.equal((await h.send(id)).ok, true);
    await h.assertUploads(2);
    assert.equal(h.calls.injections.length, 1);
    assert.equal(h.calls.tabQueries.length, queries);
    assert.equal(h.session.has(id), false);
    assert.equal(h.successes().length, 1);
    h.session.set(id, pending);
    assert.deepEqual(await h.send(id), { ok: false, code: "blob_no_tab" });
    await h.assertUploads(2);
  });

  await t.test("send-time read survives failed proxy upload and closed page", async (t) => {
    const h = await blobHarness(t, "8-send-time-read");
    h.uploadFailures = 1;
    const id = await h.capture();
    assert.equal(h.calls.injections.length, 0);
    h.permitted = true;
    assert.deepEqual(await h.send(id), { ok: false, code: "proxy_unavailable" });
    await h.assertUploads(1);
    assert.equal(h.session.has(id), true);
    assert.equal(h.calls.injections.length, 1);
    h.tabs = [];
    const queries = h.calls.tabQueries.length;
    assert.equal((await h.send(id)).ok, true);
    await h.assertUploads(2);
    assert.equal(h.calls.injections.length, 1);
    assert.equal(h.calls.tabQueries.length, queries);
    assert.equal(h.session.has(id), false);
    assert.equal(h.successes().length, 1);
  });

  await t.test("failed early read can be retried when bytes become available", async (t) => {
    const h = await blobHarness(t, "8-retry-read");
    h.permitted = true;
    h.read = async () => { throw new Error("Not available yet"); };
    const id = await h.capture();
    assert.equal(h.calls.injections.length, 1);
    assert.equal(h.fetched.length, 0);
    h.read = async () => [{ result: Buffer.from(h.bytes).toString("base64") }];
    assert.equal((await h.send(id)).ok, true);
    assert.equal(h.calls.injections.length, 2);
    await h.assertUploads(1);
    assert.equal(h.session.has(id), false);
  });
});

test("EXT-SW-009 worker consumes late download cancellation errors", async (t) => {
  const { chrome, calls, listeners, session } = makeChrome();
  let lastError = null;
  let lastErrorReads = 0;
  let uncheckedErrors = 0;
  Object.defineProperty(chrome.runtime, "lastError", {
    configurable: true,
    get() {
      lastErrorReads++;
      return lastError;
    },
  });
  chrome.downloads.cancel = (id, callback) => {
    calls.cancel.push(id);
    queueMicrotask(() => {
      lastError = { message: "Synthetic cancellation failure" };
      const readsBefore = lastErrorReads;
      callback?.();
      if (lastErrorReads === readsBefore) uncheckedErrors++;
      lastError = null;
    });
  };
  chrome.permissions = { contains: async () => false };
  const previousChrome = globalThis.chrome;
  globalThis.chrome = chrome;
  t.after(() => { globalThis.chrome = previousChrome; });
  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    if (url.endsWith("/api/bootstrap")) {
      return { ok: true, status: 200, json: async () => ({ token: "t" }) };
    }
    assert.ok(url.endsWith("/api/torrents/files"));
    assert.equal(options.body.get("mode"), "proxy");
    return {
      ok: true,
      status: 201,
      json: async () => ({
        results: [{ ok: true, id: "f".repeat(40), name: "late.torrent" }],
      }),
    };
  });
  await import("../extension/background.js?sw9");

  await listeners.download({
    id: 81,
    filename: "late.torrent",
    mime: "application/x-bittorrent",
    url: "blob:https://site.example/late",
    referrer: "https://site.example/torrents/late",
    state: "in_progress",
  });
  await flush();
  assert.equal(lastErrorReads, 1);
  assert.equal(uncheckedErrors, 0);
  assert.deepEqual(calls.cancel, [81]);
  assert.deepEqual(calls.erase, [{ id: 81 }]);
  assert.equal(calls.windows.length, 1);

  const [pendingId] = [...session.keys()];
  chrome.permissions.contains = async () => true;
  chrome.tabs.query = async () => [{ id: 82, url: "https://site.example/torrents/late" }];
  chrome.scripting.executeScript = async () => [
    { result: Buffer.from([1, 2, 3]).toString("base64") },
  ];
  chrome.downloads.search = async () => [{ id: 81, state: "interrupted" }];
  const reply = await new Promise((resolve) => {
    listeners.message(
      { type: "lid-send", id: pendingId, mode: "proxy" },
      {},
      resolve,
    );
  });
  assert.equal(reply.ok, true);
  assert.deepEqual(calls.cancel, [81]);
  assert.deepEqual(calls.erase, [{ id: 81 }, { id: 81 }]);
  assert.equal(session.has(pendingId), false);
});

test("EXT-SW-010 worker observes late filenames without suggesting after cancellation", async (t) => {
  const h = await blobHarness(t, "10-filename-after-cancel");
  const { chrome, calls, listeners, session } = h;
  h.permitted = true;
  let state = "in_progress";
  chrome.downloads.cancel = (id, callback) => {
    calls.cancel.push(id);
    state = "interrupted";
    callback();
  };
  chrome.downloads.search = async () => [{ id: 101, state }];
  listeners.download({
    id: 101,
    filename: "",
    mime: "application/x-bittorrent",
    url: "blob:https://site.example/late-name",
    referrer: "https://site.example/torrents/1",
    state,
  });
  await settle();
  assert.deepEqual(calls.cancel, [101]);
  assert.deepEqual(calls.erase, [{ id: 101 }]);
  assert.equal(calls.windows.length, 1);
  assert.equal(session.size, 1);
  const [id] = session.keys();
  assert.equal(session.get(id).name, "x.torrent");
  assert.equal(h.fetched.length, 0);

  const uncheckedErrors = [];
  let suggestions = 0;
  // Chromium's downloads_custom_bindings calls suggest automatically when
  // a registered listener returns without suggesting or returning true.
  // determineFilename rejects suggestions for cancelled downloads.
  if (listeners.filename) {
    const suggest = () => {
      suggestions++;
      if (state !== "in_progress") {
        uncheckedErrors.push("Unchecked runtime.lastError: Download must be in progress");
      }
    };
    const asynchronous = listeners.filename({ id: 101, filename: "page.torrent" }, suggest);
    if (!suggestions && asynchronous !== true) suggest();
  }
  listeners.changed?.({
    id: 101,
    filename: { current: "page.torrent" },
    state: { current: "interrupted" },
  });
  await settle();
  assert.deepEqual(uncheckedErrors, []);
  assert.equal(listeners.filename, undefined);
  assert.equal(suggestions, 0);
  assert.equal(session.get(id).name, "page.torrent");
  assert.equal(calls.windows.length, 1);
  assert.deepEqual(calls.cancel, [101]);
  assert.deepEqual(calls.erase, [{ id: 101 }]);
  assert.equal(h.fetched.length, 0);

  assert.equal((await h.send(id)).ok, true);
  await h.assertUploads(1);
  assert.equal(session.has(id), false);
  assert.equal(h.successes().length, 1);
});
