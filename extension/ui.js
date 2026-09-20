// Shared helpers for extension pages (route picker, options, action popup).

export function t(key, substitutions) {
  return chrome.i18n.getMessage(key, substitutions) || key;
}

export function applyI18n(root = document) {
  for (const node of root.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.dataset.i18n);
  }
}

export function lang() {
  try {
    return chrome.i18n.getUILanguage().startsWith("fr") ? "fr" : "en";
  } catch {
    return "en";
  }
}

export async function ensureOrigin(origin) {
  const origins = [`${origin}/*`];
  try {
    if (await chrome.permissions.contains({ origins })) return true;
    return (await chrome.permissions.request({ origins })) === true;
  } catch {
    return false;
  }
}

export async function serverUrl() {
  const { serverUrl } = await chrome.storage.sync.get({
    serverUrl: "http://192.168.1.29:8000/",
  });
  return String(serverUrl || "").replace(/\/+$/, "") || "http://192.168.1.29:8000";
}
