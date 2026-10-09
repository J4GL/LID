import { LidClient, LidError } from "./lid.js";
import { messageFor } from "./messages.js";
import { applyI18n, ensureOrigin, lang, serverUrl, t } from "./ui.js";

applyI18n();
const input = document.getElementById("server-url");
const status = document.getElementById("options-status");

function setStatus(text, kind = "") {
  status.textContent = text;
  status.className = `status ${kind}`;
}

function normalize(value) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!/^https?:\/\//i.test(trimmed)) throw new LidError("server_unreachable");
  return trimmed;
}

serverUrl().then((url) => {
  input.value = url;
});

document.getElementById("save").onclick = async () => {
  try {
    const url = normalize(input.value);
    if (!(await ensureOrigin(new URL(url).origin))) {
      setStatus(t("route_denied"), "error");
      return;
    }
    await chrome.storage.sync.set({ serverUrl: `${url}/` });
    setStatus(t("options_saved"), "ok");
  } catch (error) {
    setStatus(
      messageFor(
        error instanceof LidError ? error.code : "unexpected_response",
        lang(),
      ),
      "error",
    );
  }
};

document.getElementById("test").onclick = async () => {
  setStatus(t("options_testing"));
  try {
    const info = await new LidClient(normalize(input.value)).status();
    setStatus(
      t("options_ok", [info.proxyAddress || t("options_no_proxy")]),
      info.setupRequired ? "error" : "ok",
    );
  } catch (error) {
    setStatus(
      messageFor(
        error instanceof LidError ? error.code : "unexpected_response",
        lang(),
      ),
      "error",
    );
  }
};

// One grant up front: the blob hook then exists before any page runs, so
// even a site's first download is captured before the page revokes it.
document.getElementById("all-sites").onclick = async () => {
  try {
    const granted = await chrome.permissions.request({
      origins: ["http://*/*", "https://*/*"],
    });
    if (!granted) {
      setStatus(t("route_denied"), "error");
      return;
    }
    const result = await chrome.runtime.sendMessage({
      type: "lid-register-hook",
      origin: "*",
    });
    setStatus(
      t(result?.ok ? "options_all_sites_ok" : "options_all_sites_fail"),
      result?.ok ? "ok" : "error",
    );
  } catch {
    setStatus(t("options_all_sites_fail"), "error");
  }
};
