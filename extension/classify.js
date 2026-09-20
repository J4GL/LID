// Pure URL/download classification for the LID extension.
// No chrome.* or network access: unit-tested in Node (EXT-CAP-001/002).

export const TORRENT_MIME = "application/x-bittorrent";
export const TORRENT_SUFFIX = ".torrent";

export function isTorrentDownload({ filename = "", mime = "" } = {}) {
  const name = String(filename || "").toLowerCase();
  const type = String(mime || "").split(";")[0].trim().toLowerCase();
  return name.endsWith(TORRENT_SUFFIX) || type === TORRENT_MIME;
}

export function fetchableHttpUrl({ url = "", finalUrl = "" } = {}) {
  for (const candidate of [finalUrl, url]) {
    if (typeof candidate === "string" && /^https?:\/\//i.test(candidate)) {
      return candidate;
    }
  }
  return null;
}

export function classifyLink(linkUrl) {
  if (typeof linkUrl !== "string") return null;
  const trimmed = linkUrl.trim();
  if (/^magnet:\?/i.test(trimmed)) return "magnet";
  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
  return parsed.pathname.toLowerCase().endsWith(TORRENT_SUFFIX)
    ? "file"
    : null;
}

export function trackerOrigin(url) {
  return new URL(url).origin;
}
