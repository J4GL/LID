import {
  classifyLink,
  fetchableHttpUrl,
  isTorrentDownload,
  trackerOrigin,
} from "./classify.js";
import { LidClient, LidError, MAX_TORRENT_BYTES } from "./lid.js";
import { messageFor } from "./messages.js";

export const DEFAULT_SERVER = "http://192.168.1.29:8000/";
export const MENU_ID = "lid-send";

function lang() {
  try {
    return chrome.i18n.getUILanguage().startsWith("fr") ? "fr" : "en";
  } catch {
    return "en";
  }
}

async function serverUrl() {
  const { serverUrl } = await chrome.storage.sync.get({
    serverUrl: DEFAULT_SERVER,
  });
  return serverUrl || DEFAULT_SERVER;
}

async function notify(id, message) {
  await chrome.notifications.create(id, {
    type: "basic",
    iconUrl: "icons/lid-48.png",
    title: chrome.i18n.getMessage("notif_title"),
    message,
  });
}

function pendingId() {
  return `p${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
}

const PICKER_WIDTH = 380;
const PICKER_HEIGHT = 300;
const CLICK_MAX_AGE_MS = 10000;

// Self-contained: runs in the page (MAIN world), where blob-hook.js records
// the last clicked element's anchor.
function readLastClick() {
  return globalThis.__lidLastClick || null;
}

function freshAnchor(anchor) {
  if (!anchor) return null;
  const { left, right, bottom, at } = anchor;
  if (![left, right, bottom, at].every(Number.isFinite)) return null;
  return Date.now() - at <= CLICK_MAX_AGE_MS ? anchor : null;
}

function clamp(value, min, max) {
  return Math.round(Math.min(Math.max(value, min), Math.max(min, max)));
}

// Under the clicked element when the page hook saw the click, otherwise
// centered on the focused browser window. Empty when no window is known.
async function pickerBounds(tab) {
  let win;
  try {
    win = await chrome.windows.getLastFocused({ populate: true });
  } catch {
    return {};
  }
  if (!win) return {};
  const tabId = tab?.id ?? win.tabs?.find((candidate) => candidate.active)?.id;
  let left = win.left + (win.width - PICKER_WIDTH) / 2;
  let top = win.top + (win.height - PICKER_HEIGHT) / 2;
  if (tabId !== undefined) {
    try {
      const [injection] = await chrome.scripting.executeScript({
        target: { tabId },
        world: "MAIN",
        func: readLastClick,
      });
      const anchor = freshAnchor(injection?.result);
      if (anchor) {
        let zoom = 1;
        try {
          zoom = (await chrome.tabs.getZoom(tabId)) || 1;
        } catch {
          // Unknown zoom: assume 100 %.
        }
        left = ((anchor.left + anchor.right) / 2) * zoom - PICKER_WIDTH / 2;
        top = anchor.bottom * zoom + 4;
      }
    } catch {
      // Site not granted or tab gone: keep the window center.
    }
  }
  return {
    left: clamp(left, win.left, win.left + win.width - PICKER_WIDTH),
    top: clamp(top, win.top, win.top + win.height - PICKER_HEIGHT),
  };
}

async function openRoutePicker(id, tab) {
  await chrome.windows.create({
    url: chrome.runtime.getURL(`route.html?id=${id}`),
    type: "popup",
    width: PICKER_WIDTH,
    height: PICKER_HEIGHT,
    ...(await pickerBounds(tab)),
  });
}

const FALLBACK_NAME = "x.torrent";

function basename(path) {
  return String(path || FALLBACK_NAME).split(/[/\\]/).pop() || FALLBACK_NAME;
}

function isBlobUrl(url) {
  return typeof url === "string" && url.startsWith("blob:");
}

function blobOrigin(item) {
  // A referrer can name a different origin or omit the source page path.
  return trackerOrigin(item.url);
}

// Self-contained: serialized into the page by executeScript (MAIN world),
// which alone can read the page's blob: URLs. Base64 because injection
// results must be JSON-serializable. Stash first: the hook-held Blob reads
// via arrayBuffer(), immune to page CSP (fetch(blob:) is often forbidden)
// and to revokeObjectURL; fetch stays as the fallback.
function readBlobAsBase64(blobUrl) {
  const stash = globalThis.__lidBlobs;
  const stashed =
    stash && typeof stash.get === "function" ? stash.get(blobUrl) : undefined;
  const pending =
    stashed && typeof stashed.arrayBuffer === "function"
      ? Promise.resolve(stashed)
      : fetch(blobUrl).then((response) => {
          if (!response.ok) throw new Error("blob fetch failed");
          return response.blob();
        });
  return pending.then(async (blob) => {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 8192) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
    }
    return btoa(binary);
  });
}

function base64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function magnetName(magnet) {
  try {
    return new URL(magnet).searchParams.get("dn") || magnet.slice(0, 48);
  } catch {
    return magnet.slice(0, 48);
  }
}

async function fetchTorrentBytes(url) {
  let response;
  try {
    response = await fetch(url, { credentials: "include" });
  } catch {
    throw new LidError("tracker_unreachable");
  }
  if (!response.ok) throw new LidError("tracker_unreachable");
  if (Number(response.headers.get("content-length") || 0) > MAX_TORRENT_BYTES) {
    throw new LidError("file_too_large");
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength === 0 || buffer.byteLength > MAX_TORRENT_BYTES) {
    throw new LidError(
      buffer.byteLength === 0 ? "invalid_torrent" : "file_too_large",
    );
  }
  return new Uint8Array(buffer);
}

// DownloadIds already routed to the picker: onCreated and
// onChanged can both report the same torrent.
const intercepted = new Set();
// DownloadIds stashed as blob pendings, for late name refreshes.
const blobDownloads = new Map();
// PendingIds with captured bytes kept until a successful upload (memory only:
// session storage quota cannot hold large torrents).
const blobBytes = new Map();
// Route choice can arrive before the early read finishes. Both callers
// must wait on the same read, including its failure.
const blobReads = new Map();

function cancelDownloadQuietly(downloadId) {
  return new Promise((resolve) => {
    try {
      chrome.downloads.cancel(downloadId, () => {
        // Consume callback errors from this best-effort cleanup operation.
        void chrome.runtime.lastError;
        resolve();
      });
    } catch {
      resolve();
    }
  });
}

async function cancelQuietly(downloadId) {
  try {
    await cancelDownloadQuietly(downloadId);
  } catch {
    // Already gone or finished: best effort only.
  }
  try {
    await chrome.downloads.erase({ id: downloadId });
  } catch {
    // Same.
  }
}

async function interceptDownload(item) {
  if (intercepted.has(item.id)) return;
  intercepted.add(item.id);
  const url = fetchableHttpUrl(item);
  if (!url) {
    if (!isBlobUrl(item.url)) {
      await notify(
        `lid-blob-${item.id}`,
        chrome.i18n.getMessage("notif_blob"),
      );
      return;
    }
    // Page-generated bytes: the page keeps them, so cancelling the browser
    // download is safe and merely avoids a stray local file.
    await cancelQuietly(item.id);
    const id = pendingId();
    blobDownloads.set(item.id, id);
    const pending = {
      kind: "blob",
      url: item.url,
      origin: blobOrigin(item),
      name: basename(item.filename),
      downloadId: item.id,
      referrer: item.referrer || "",
      created: Date.now(),
    };
    await chrome.storage.session.set({ [id]: pending });
    const reading = cacheBlobEarly(id, pending);
    await openRoutePicker(id);
    await reading;
    return;
  }
  await cancelQuietly(item.id);
  const id = pendingId();
  await chrome.storage.session.set({
    [id]: {
      kind: "file",
      url,
      origin: trackerOrigin(url),
      name: basename(item.filename),
      created: Date.now(),
    },
  });
  await openRoutePicker(id);
}

async function handleDownload(item) {
  if (intercepted.has(item.id) || !isTorrentDownload(item)) return;
  await interceptDownload(item);
}

async function refreshPendingName(item) {
  const id = blobDownloads.get(item.id);
  if (!id || !item.filename) return;
  const store = await chrome.storage.session.get(id);
  const pending = store[id];
  if (!pending || pending.name !== FALLBACK_NAME) return;
  await chrome.storage.session.set({
    [id]: { ...pending, name: basename(item.filename) },
  });
}

async function handleFilename(item) {
  // Filename and mime often arrive after onCreated (extensionless tracker
  // URLs, generic mime): merge the event item with a fresh search, since
  // search() may not reflect the determined filename yet.
  if (intercepted.has(item.id)) {
    await refreshPendingName(item);
    return;
  }
  let full = item;
  try {
    const [found] = await chrome.downloads.search({ id: item.id });
    if (found) {
      full = { ...found };
      for (const [key, value] of Object.entries(item)) {
        if (value) full[key] = value;
      }
    }
  } catch {
    // Event item only.
  }
  if (!isTorrentDownload(full)) return;
  await interceptDownload(full);
}

async function readBlobBytes(pending) {
  const origin = blobOrigin(pending);
  // The grant can be switched off between the route choice and the read
  // (chrome://extensions toggles): report that instead of a bogus
  // "revoked blob".
  try {
    const allowed = await chrome.permissions.contains({
      origins: [`${origin}/*`],
    });
    if (!allowed) throw new LidError("origin_revoked");
  } catch (error) {
    if (error instanceof LidError) throw error;
    // No permissions API (older harness): fall through to the tab query.
  }
  const tabs = (await chrome.tabs.query({ url: [`${origin}/*`] }))
    // Unreachable tabs come back redacted, without url: not candidates.
    .filter((candidate) => {
      try {
        return candidate.url && trackerOrigin(candidate.url) === origin;
      } catch {
        return false;
      }
    })
    .sort(
      (a, b) =>
        Number(b.url === pending.referrer) - Number(a.url === pending.referrer),
    );
  if (!tabs.length) throw new LidError("blob_no_tab");
  for (const tab of tabs) {
    try {
      const [injection] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: "MAIN",
        func: readBlobAsBase64,
        args: [pending.url],
      });
      if (typeof injection?.result !== "string" || !injection.result) continue;
      const bytes = base64ToBytes(injection.result);
      if (bytes.length) return bytes;
    } catch {
      // The tab may have navigated, or another page owns the retained Blob.
    }
  }
  throw new LidError("blob_unavailable");
}

function cachedBlobBytes(id, pending) {
  const cached = blobBytes.get(id);
  if (cached) return Promise.resolve(cached);
  let reading = blobReads.get(id);
  if (!reading) {
    reading = readBlobBytes(pending)
      .then((bytes) => {
        // Keep bytes even if the upload fails and the source page closes.
        blobBytes.set(id, bytes);
        return bytes;
      })
      .finally(() => blobReads.delete(id));
    blobReads.set(id, reading);
  }
  return reading;
}

// Pages may revoke their blob within milliseconds of the click: when the
// origin is already allowed, grab the bytes at interception time so the
// route choice (seconds later) still succeeds. Failures stay silent, the
// send-time read reports them.
async function cacheBlobEarly(id, pending) {
  try {
    if (!chrome.permissions?.contains) return;
    await cachedBlobBytes(id, pending);
  } catch {
    // Send-time read will surface the real error.
  }
}

const ALL_SITES = ["http://*/*", "https://*/*"];

// `origin` "*" hooks every http(s) page, so the very first download of a
// site is already retained (no per-site grant race).
function registerBlobHook(origin) {
  return hookMatches(origin === "*" ? ALL_SITES : [`${origin}/*`]);
}

// Page scripts sharing the granted sites: the blob hook (EXT-SW-006) and the
// magnet click hook (EXT-CAP-005), which needs chrome.runtime, absent from MAIN.
const PAGE_SCRIPTS = [
  { id: "lid-blob-hook", js: ["blob-hook.js"], world: "MAIN" },
  { id: "lid-magnet-hook", js: ["magnet-hook.js"], world: "ISOLATED" },
];

async function hookMatches(matches_) {
  try {
    const existing = await chrome.scripting.getRegisteredContentScripts({
      ids: PAGE_SCRIPTS.map((script) => script.id),
    });
    // One set of sites for every script: an update may find only the older
    // blob hook, whose sites the new magnet hook must inherit.
    const matches = [
      ...new Set([
        ...existing.flatMap((script) => script.matches || []),
        ...matches_,
      ]),
    ];
    const known = new Set(existing.map((script) => script.id));
    const updates = PAGE_SCRIPTS.filter((script) => known.has(script.id)).map(
      ({ id }) => ({ id, matches }),
    );
    const fresh = PAGE_SCRIPTS.filter((script) => !known.has(script.id)).map(
      (script) => ({
        ...script,
        matches,
        runAt: "document_start",
        persistAcrossSessions: true,
      }),
    );
    if (updates.length) await chrome.scripting.updateContentScripts(updates);
    if (fresh.length) await chrome.scripting.registerContentScripts(fresh);
  } catch (error) {
    console.warn("LID hook registration failed", error);
    return { ok: false };
  }
  // Hook pages that are already open so no reload is needed.
  try {
    const tabs = await chrome.tabs.query({ url: matches_ });
    for (const tab of tabs) {
      for (const { js, world } of PAGE_SCRIPTS) {
        try {
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            world,
            files: js,
          });
        } catch {
          // Closed or unreachable tab: skip it.
        }
      }
    }
  } catch {
    // Registration stands; future page loads get the hook.
  }
  return { ok: true };
}

// Granted page origins, without the manifest's own hosts (the LID server).
function pageOrigins(origins) {
  let own = [];
  try {
    own = chrome.runtime.getManifest?.().host_permissions || [];
  } catch {
    // No manifest (tests): keep every origin.
  }
  return (origins || []).filter((origin) => !own.includes(origin));
}

// The hook must exist before a page creates its blob: registering it only at
// send time lost the first download of every already-granted site (grant made
// before the hook existed, script dropped on extension reload/update, or
// toggled in chrome://extensions).
async function syncBlobHook() {
  try {
    const all = await chrome.permissions?.getAll?.();
    const matches = pageOrigins(all?.origins);
    if (matches.length) await hookMatches(matches);
  } catch (error) {
    console.warn("LID hook sync failed", error);
  }
}

async function sendBlob(id, pending, client, mode) {
  let bytes;
  try {
    bytes = await cachedBlobBytes(id, pending);
  } catch (error) {
    if (error instanceof LidError) throw error;
    throw new LidError("blob_unavailable");
  }
  let localFile = false;
  try {
    const [download] = await chrome.downloads.search({
      id: pending.downloadId,
    });
    localFile = download?.state === "complete";
    if (download?.state === "in_progress") {
      await cancelDownloadQuietly(pending.downloadId);
    }
  } catch {
    // Unknown state: plain success message.
  }
  try {
    await chrome.downloads.erase({ id: pending.downloadId });
  } catch {
    // Same.
  }
  const result = await client.uploadTorrent(bytes, pending.name, mode);
  blobBytes.delete(id);
  return { ...result, localFile };
}

async function handleMenuClick(info, tab) {
  if (info.menuItemId !== MENU_ID) return;
  const kind = classifyLink(info.linkUrl);
  if (!kind) {
    await notify(
      `lid-link-${Date.now()}`,
      chrome.i18n.getMessage("notif_not_torrent"),
    );
    return;
  }
  const link = info.linkUrl.trim();
  if (kind === "magnet") {
    await queueMagnet(link, tab);
    return;
  }
  const id = pendingId();
  await chrome.storage.session.set({
    [id]: {
      kind,
      url: link,
      origin: trackerOrigin(link),
      name: basename(new URL(link).pathname),
      created: Date.now(),
    },
  });
  await openRoutePicker(id, tab);
}

async function queueMagnet(magnet, tab) {
  const id = pendingId();
  await chrome.storage.session.set({
    [id]: { kind: "magnet", magnet, name: magnetName(magnet), created: Date.now() },
  });
  await openRoutePicker(id, tab);
}

async function handleSend(id, mode) {
  const store = await chrome.storage.session.get(id);
  const pending = store[id];
  if (!pending || (mode !== "direct" && mode !== "proxy")) {
    return { ok: false, code: "unexpected_response" };
  }
  try {
    const client = new LidClient(await serverUrl());
    const result =
      pending.kind === "magnet"
        ? await client.sendMagnet(pending.magnet, mode)
        : pending.kind === "blob"
          ? await sendBlob(id, pending, client, mode)
          : await client.uploadTorrent(
              await fetchTorrentBytes(pending.url),
              pending.name,
              mode,
            );
    await chrome.storage.session.remove(id);
    blobDownloads.forEach((value, key) => {
      if (value === id) blobDownloads.delete(key);
    });
    await notify(
      `lid-ok-${id}`,
      chrome.i18n.getMessage(
        result.localFile ? "notif_added_local" : "notif_added",
        [result.name || pending.name, mode],
      ),
    );
    return { ok: true, ...result };
  } catch (error) {
    const code =
      error instanceof LidError ? error.code : "unexpected_response";
    await notify(`lid-err-${id}`, messageFor(code, lang()));
    return { ok: false, code };
  }
}

async function handleMessage(message, sender) {
  if (message?.type === "lid-get-pending") {
    const store = await chrome.storage.session.get(message.id);
    return store[message.id]
      ? { ok: true, pending: store[message.id] }
      : { ok: false, code: "unexpected_response" };
  }
  if (message?.type === "lid-send") {
    return handleSend(message.id, message.mode);
  }
  if (message?.type === "lid-magnet") {
    // From magnet-hook.js: a page click, placed under the link in its tab.
    const tab = sender?.tab;
    if (tab?.id === undefined || classifyLink(message.magnet) !== "magnet") {
      return { ok: false, code: "unexpected_response" };
    }
    await queueMagnet(message.magnet.trim(), tab);
    return { ok: true };
  }
  if (message?.type === "lid-register-hook") {
    if (typeof message.origin !== "string" || !message.origin) {
      return { ok: false, code: "unexpected_response" };
    }
    return registerBlobHook(message.origin);
  }
  if (message?.type === "lid-status") {
    try {
      return { ok: true, ...(await new LidClient(await serverUrl()).status()) };
    } catch (error) {
      return {
        ok: false,
        code: error instanceof LidError ? error.code : "unexpected_response",
      };
    }
  }
  return { ok: false, code: "unexpected_response" };
}

chrome.runtime.onInstalled.addListener((details) => {
  if (details?.reason === "install") chrome.runtime.openOptionsPage?.();
  chrome.contextMenus.create({
    id: MENU_ID,
    title: chrome.i18n.getMessage("menu_send"),
    contexts: ["link"],
  });
  syncBlobHook();
});

chrome.runtime.onStartup?.addListener(() => {
  syncBlobHook();
});

chrome.permissions?.onAdded?.addListener((permissions) => {
  const matches = pageOrigins(permissions?.origins);
  if (matches.length) hookMatches(matches);
});

chrome.downloads.onCreated.addListener((item) => {
  handleDownload(item).catch((error) => console.warn("LID download handler failed", error));
});

// We only observe names; onDeterminingFilename's suggest() can race with
// onCreated cancelling the torrent and report "Download must be in progress".
chrome.downloads.onChanged.addListener((delta) => {
  if (!delta.filename?.current && !delta.mime?.current) return;
  handleFilename({
    id: delta.id,
    filename: delta.filename?.current,
    mime: delta.mime?.current,
    finalUrl: delta.finalUrl?.current,
  }).catch((error) => console.warn("LID filename handler failed", error));
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  handleMenuClick(info, tab).catch((error) => console.warn("LID menu handler failed", error));
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(
    sendResponse,
    () => sendResponse({ ok: false, code: "unexpected_response" }),
  );
  return true;
});
