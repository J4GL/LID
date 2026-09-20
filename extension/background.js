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

async function openRoutePicker(id) {
  await chrome.windows.create({
    url: chrome.runtime.getURL(`route.html?id=${id}`),
    type: "popup",
    width: 380,
    height: 300,
  });
}

function basename(path) {
  return String(path || "x.torrent").split(/[/\\]/).pop() || "x.torrent";
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

async function handleDownload(item) {
  if (!isTorrentDownload(item)) return;
  const url = fetchableHttpUrl(item);
  if (!url) {
    await notify(
      `lid-blob-${item.id}`,
      chrome.i18n.getMessage("notif_blob"),
    );
    return;
  }
  await chrome.downloads.cancel(item.id);
  await chrome.downloads.erase({ id: item.id });
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

async function handleMenuClick(info) {
  if (info.menuItemId !== MENU_ID) return;
  const kind = classifyLink(info.linkUrl);
  if (!kind) {
    await notify(
      `lid-link-${Date.now()}`,
      chrome.i18n.getMessage("notif_not_torrent"),
    );
    return;
  }
  const id = pendingId();
  const link = info.linkUrl.trim();
  await chrome.storage.session.set({
    [id]:
      kind === "magnet"
        ? { kind, magnet: link, name: magnetName(link), created: Date.now() }
        : {
            kind,
            url: link,
            origin: trackerOrigin(link),
            name: basename(new URL(link).pathname),
            created: Date.now(),
          },
  });
  await openRoutePicker(id);
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
        : await client.uploadTorrent(
            await fetchTorrentBytes(pending.url),
            pending.name,
            mode,
          );
    await chrome.storage.session.remove(id);
    await notify(
      `lid-ok-${id}`,
      chrome.i18n.getMessage("notif_added", [
        result.name || pending.name,
        mode,
      ]),
    );
    return { ok: true, ...result };
  } catch (error) {
    const code =
      error instanceof LidError ? error.code : "unexpected_response";
    await notify(`lid-err-${id}`, messageFor(code, lang()));
    return { ok: false, code };
  }
}

async function handleMessage(message) {
  if (message?.type === "lid-get-pending") {
    const store = await chrome.storage.session.get(message.id);
    return store[message.id]
      ? { ok: true, pending: store[message.id] }
      : { ok: false, code: "unexpected_response" };
  }
  if (message?.type === "lid-send") {
    return handleSend(message.id, message.mode);
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

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: chrome.i18n.getMessage("menu_send"),
    contexts: ["link"],
  });
});

chrome.downloads.onCreated.addListener((item) => {
  handleDownload(item).catch(() => {});
});

chrome.contextMenus.onClicked.addListener((info) => {
  handleMenuClick(info).catch(() => {});
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message).then(sendResponse);
  return true;
});
