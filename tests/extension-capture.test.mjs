import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

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
    ["contextMenus", "downloads", "notifications", "storage"],
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
