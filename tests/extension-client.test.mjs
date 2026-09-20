import assert from "node:assert/strict";
import test from "node:test";

import { LidClient, LidError, MAX_TORRENT_BYTES } from "../extension/lid.js";
import { messageFor } from "../extension/messages.js";
import { ensureOrigin } from "../extension/ui.js";

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

test("EXT-CLI-001 client bootstraps token retries once and posts", async () => {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/api/bootstrap")) return jsonResponse(200, { token: "t1" });
    const form = options.body;
    assert.ok(form instanceof FormData);
    assert.equal(form.get("mode"), "direct");
    assert.equal(form.get("files").name, "x.torrent");
    assert.equal(options.headers["X-P2P-Token"], "t1");
    return jsonResponse(201, {
      results: [{ name: "x.torrent", ok: true, id: "a".repeat(40) }],
    });
  };
  const client = new LidClient("http://192.168.1.29:8000/", fetchImpl);
  const result = await client.uploadTorrent(
    new Uint8Array([1, 2, 3]),
    "x.torrent",
    "direct",
  );
  assert.deepEqual(result, {
    name: "x.torrent",
    id: "a".repeat(40),
    mode: "direct",
  });
  assert.ok(calls[0].url.endsWith("/api/bootstrap"));
  assert.ok(calls[1].url.endsWith("/api/torrents/files"));

  let bootstraps = 0;
  const retryFetch = async (url, options = {}) => {
    if (url.endsWith("/api/bootstrap")) {
      bootstraps += 1;
      return jsonResponse(200, { token: `t${bootstraps}` });
    }
    if (options.headers["X-P2P-Token"] === "t1") {
      return jsonResponse(403, {
        detail: "Session expirée.",
        code: "session_expired",
      });
    }
    const body = JSON.parse(options.body);
    assert.equal(body.mode, "proxy");
    assert.match(body.magnet, /^magnet:/);
    assert.equal(options.headers["X-P2P-Token"], "t2");
    return jsonResponse(201, { id: "b".repeat(40), mode: "proxy" });
  };
  const magnet = await new LidClient(
    "http://192.168.1.29:8000",
    retryFetch,
  ).sendMagnet("magnet:?xt=urn:btih:abc", "proxy");
  assert.deepEqual(magnet, { id: "b".repeat(40), mode: "proxy" });
  assert.equal(bootstraps, 2);

  const dupe = new LidClient("http://192.168.1.29:8000", async (url) =>
    url.endsWith("/api/bootstrap")
      ? jsonResponse(200, { token: "t" })
      : jsonResponse(409, {
          detail: "Déjà présent.",
          code: "duplicate_torrent",
        }),
  );
  await assert.rejects(
    () => dupe.uploadTorrent(new Uint8Array(8), "x.torrent", "direct"),
    (error) => {
      assert.ok(error instanceof LidError);
      assert.equal(error.code, "duplicate_torrent");
      return true;
    },
  );

  let fetched = 0;
  const guarded = new LidClient("http://192.168.1.29:8000", async () => {
    fetched += 1;
    return jsonResponse(200, {});
  });
  await assert.rejects(
    () =>
      guarded.uploadTorrent(
        new Uint8Array(MAX_TORRENT_BYTES + 1),
        "big.torrent",
        "direct",
      ),
    (error) => {
      assert.ok(error instanceof LidError);
      assert.equal(error.code, "file_too_large");
      return true;
    },
  );
  assert.equal(fetched, 0);
});

test("EXT-CLI-002 error codes map to FR and EN messages", () => {
  for (const code of [
    "duplicate_torrent",
    "proxy_unavailable",
    "proxy_not_configured",
    "invalid_torrent",
    "file_too_large",
    "server_unreachable",
  ]) {
    const fr = messageFor(code, "fr");
    const en = messageFor(code, "en");
    assert.ok(fr.length > 0);
    assert.ok(en.length > 0);
    assert.notEqual(fr, en);
  }
  assert.equal(
    messageFor("nope", "fr"),
    messageFor("unexpected_response", "fr"),
  );
  assert.equal(
    messageFor("nope", "en"),
    messageFor("unexpected_response", "en"),
  );
});

test("EXT-CLI-003 origin request failure reads as denied", async () => {
  let requested = 0;
  globalThis.chrome = {
    permissions: {
      contains: async () => true,
      request: async () => {
        requested += 1;
        return true;
      },
    },
  };
  assert.equal(await ensureOrigin("https://tracker.example"), true);
  assert.equal(requested, 0);

  globalThis.chrome.permissions.contains = async () => false;
  globalThis.chrome.permissions.request = async () => false;
  assert.equal(await ensureOrigin("https://tracker.example"), false);

  globalThis.chrome.permissions.request = async () => {
    throw new Error("no gesture");
  };
  assert.equal(await ensureOrigin("https://tracker.example"), false);
  delete globalThis.chrome;
});
