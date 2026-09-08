import { installDropZones } from "./drop.js";
import { installFolderSettings } from "./folders.js";
import {
  getLanguage,
  initI18n,
  localizedError,
  onLanguageChange,
  t,
} from "./i18n.js";
("use strict");
initI18n();
const $ = (id) => document.getElementById(id);
let token = "",
  chosenMode = null,
  bootstrap = {},
  busy = false,
  addError = null,
  connectionStatus = "connecting";
const rowNodes = new Map();
const state = {
  torrents: [],
  proxy: { tcp: false, udp: false },
  download_rate: 0,
  upload_rate: 0,
  global_ratio: 0,
  seeding: 0,
};
const formatBytes = (n) => {
  const units =
    getLanguage() === "fr"
      ? ["o", "Kio", "Mio", "Gio", "Tio"]
      : ["B", "KiB", "MiB", "GiB", "TiB"];
  let i = 0;
  n = Math.max(0, Number(n) || 0);
  while (n >= 1024 && i < 4) {
    n /= 1024;
    i++;
  }
  return `${n === 0 ? 0 : n.toFixed(i ? 1 : 0)} ${units[i]}`;
};
function toast(message, error = false) {
  const el = document.createElement("div");
  el.className = `toast${error ? " error" : ""}`;
  const text = document.createElement("span");
  const renderMessage =
    typeof message === "function" ? message : () => String(message);
  text.textContent = renderMessage();
  el.renderTranslation = () => {
    text.textContent = renderMessage();
    close.setAttribute("aria-label", t("toast.close"));
  };
  const close = document.createElement("button");
  close.textContent = "✕";
  close.setAttribute("aria-label", t("toast.close"));
  close.onclick = () => el.remove();
  el.append(text, close);
  $("toast-region").append(el);
  if (!error) setTimeout(() => el.remove(), 6500);
}
function toastError(error, fallback = "") {
  toast(() => localizedError(error?.code, error?.message || fallback), true);
}
function renderAddError() {
  $("add-error").hidden = !addError;
  $("add-error").textContent = addError
    ? localizedError(addError.code, addError.message)
    : "";
}
function renderConnectionStatus() {
  $("live-label").textContent = t(`footer.${connectionStatus}`);
  if (connectionStatus === "reconnecting") {
    $("connection-error").hidden = false;
    $("connection-error").textContent = t("connection.interrupted");
  }
}
async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (
    (options.method && options.method !== "GET") ||
    url.startsWith("/api/storage") ||
    url.startsWith("/api/settings")
  )
    headers["X-P2P-Token"] = token;
  const response = await fetch(url, { ...options, headers });
  let data;
  try {
    data = await response.json();
  } catch {
    const error = new Error(t("error.unexpected_response"));
    error.code = "unexpected_response";
    throw error;
  }
  if (!response.ok && !data.results) {
    const fallback =
      typeof data.detail === "string"
        ? data.detail
        : t("error.invalid_request");
    const error = new Error(localizedError(data.code, fallback));
    error.code = data.code;
    error.fields = data.fields || {};
    error.warnings = data.warnings || [];
    throw error;
  }
  return data;
}
function setMetric(id, n, suffix = "/s") {
  const parts = formatBytes(n).split(" ");
  $(id).replaceChildren(document.createTextNode(`${parts[0]} `));
  const unit = document.createElement("small");
  unit.textContent = parts[1] + suffix;
  $(id).append(unit);
}
function render(data) {
  Object.assign(state, data);
  setMetric("total-down", data.download_rate);
  setMetric("total-up", data.upload_rate);
  $("global-ratio").textContent = Number(data.global_ratio || 0).toFixed(2);
  $("total-seeding").replaceChildren(
    document.createTextNode(`${data.seeding} `),
  );
  const unit = document.createElement("small");
  unit.textContent = t(
    data.seeding === 1 ? "torrent.unit_one" : "torrent.unit_many",
  );
  $("total-seeding").append(unit);
  $("torrent-count").textContent = data.torrents.length;
  $("empty").hidden = !!data.torrents.length;
  $("table-labels").hidden = !data.torrents.length;
  const current = new Set(data.torrents.map((r) => r.id));
  for (const [id, node] of rowNodes)
    if (!current.has(id)) {
      node.remove();
      rowNodes.delete(id);
    }
  for (const row of data.torrents) {
    let node = rowNodes.get(row.id);
    if (!node) {
      node = document.createElement("article");
      node.className = "torrent-row";
      node.dataset.mode = row.mode;
      node.innerHTML =
        '<div class="torrent-info"><h3 class="torrent-name"></h3><div class="torrent-meta"><span class="badge"></span><span class="torrent-size"></span><span class="torrent-peers"></span><span class="torrent-ratio"></span><span class="torrent-volumes"></span></div></div><div class="torrent-progress"><div class="progress-label"><span class="torrent-state"></span><strong class="torrent-percent"></strong></div><progress max="1" value="0"></progress></div><div class="transfer-speeds"><span class="torrent-down"></span><span class="torrent-up"></span></div><div class="torrent-actions"><button class="icon-button pause-action"></button><button class="icon-button remove-action">✕</button></div><div class="torrent-location"><span class="torrent-path"></span><span class="move-target" hidden></span><span class="move-error" hidden></span><button class="text-button retry-move" hidden></button></div><p class="torrent-error" hidden></p>';
      rowNodes.set(row.id, node);
      $("torrent-list").append(node);
      node.querySelector(".pause-action").onclick = () => torrentAction(row.id);
      node.querySelector(".remove-action").onclick = () =>
        torrentAction(row.id, true);
    }
    const q = (s) => node.querySelector(s);
    q(".torrent-path").textContent = row.save_path || "";
    q(".move-target").hidden =
      !row.move_destination || row.move_destination === row.save_path;
    q(".move-target").textContent = row.move_destination
      ? t("torrent.destination", { path: row.move_destination })
      : "";
    q(".move-error").hidden = !row.move_error;
    q(".move-error").textContent = row.move_error
      ? localizedError(row.move_error_code, row.move_error)
      : "";
    q(".retry-move").hidden = !row.can_retry_move;
    q(".retry-move").textContent = t("torrent.retry_move");
    q(".remove-action").title = t("torrent.remove");
    q(".remove-action").setAttribute("aria-label", t("torrent.remove"));
    q(".remove-action").disabled = ["moving", "verifying"].includes(
      row.move_state,
    );
    q(".retry-move").onclick = async () => {
      try {
        await api(`/api/torrents/${row.id}/retry-move`, { method: "POST" });
        toast(() => t("toast.retry_move"));
      } catch (e) {
        toastError(e);
      }
    };
    q(".torrent-name").textContent = row.name;
    q(".badge").textContent = row.mode === "direct" ? "DIRECT" : "PROXY";
    q(".badge").className = `badge ${row.mode}`;
    q(".torrent-size").textContent = formatBytes(row.total);
    q(".torrent-peers").textContent = `${row.peers} ${t(
      row.peers === 1 ? "torrent.peer_one" : "torrent.peer_many",
    )}`;
    q(".torrent-ratio").textContent = t("torrent.ratio", {
      value: row.ratio.toFixed(2),
    });
    q(".torrent-volumes").textContent = t("torrent.volumes", {
      downloaded: formatBytes(row.downloaded),
      uploaded: formatBytes(row.uploaded),
    });
    q(".torrent-state").textContent = t(`state.${row.state_code || "waiting"}`);
    q(".torrent-percent").textContent = `${(row.progress * 100).toFixed(1)} %`;
    q("progress").value = row.progress;
    q("progress").setAttribute(
      "aria-label",
      t("torrent.progress", { name: row.name }),
    );
    q(".torrent-down").textContent = `↓  ${formatBytes(row.download_rate)}/s`;
    q(".torrent-up").textContent = `↑  ${formatBytes(row.upload_rate)}/s`;
    q(".pause-action").textContent = row.paused ? "▶" : "Ⅱ";
    const actionLabel = t(row.paused ? "torrent.resume" : "torrent.pause");
    q(".pause-action").title = actionLabel;
    q(".pause-action").setAttribute("aria-label", `${actionLabel} ${row.name}`);
    q(".torrent-error").hidden = !row.error;
    q(".torrent-error").textContent = row.error
      ? localizedError(row.error_code, row.error)
      : "";
  }
  const p = data.proxy;
  $("proxy-dot").className =
    `dot ${p.tcp ? "good" : p.checked_at ? "" : "checking"}`;
  $("proxy-short").textContent = p.tcp
    ? p.udp
      ? t("proxy.short_tcp_udp")
      : t("proxy.short_tcp")
    : p.checked_at
      ? t("proxy.short_unavailable")
      : t("proxy.short_checking");
  $("proxy-message").textContent = t(
    `proxy.message.${p.message_code || (p.tcp ? "proxy_active_tcp" : "proxy_checking")}`,
  );
  $("tcp-result").textContent = p.tcp
    ? t("proxy.functional")
    : t("proxy.unavailable");
  $("udp-result").textContent = p.udp
    ? t("proxy.udp_valid")
    : t("proxy.udp_invalid");
  $("checked-at").textContent = p.checked_at
    ? new Date(p.checked_at * 1000).toLocaleTimeString(
        getLanguage() === "fr" ? "fr-FR" : "en-US",
      )
    : t("proxy.pending");
  if (data.errors?.length) {
    $("connection-error").hidden = false;
    $("connection-error").textContent = (data.error_details || []).length
      ? data.error_details
          .map((error) => localizedError(error.code, error.message))
          .join(" ")
      : data.errors.join(" ");
  } else if ($("live-dot").classList.contains("live"))
    $("connection-error").hidden = true;
}
async function torrentAction(id, remove = false) {
  const row = state.torrents.find((r) => r.id === id);
  if (!row) return;
  try {
    await api(
      remove
        ? `/api/torrents/${id}`
        : `/api/torrents/${id}/${row.paused ? "resume" : "pause"}`,
      { method: remove ? "DELETE" : "POST" },
    );
    if (remove) toast(() => t("toast.removed"));
    render(await api("/api/torrents"));
  } catch (e) {
    toastError(e);
  }
}
function openAdd() {
  chosenMode = null;
  addError = null;
  document
    .querySelectorAll(".mode-choice")
    .forEach((b) => b.setAttribute("aria-pressed", "false"));
  $("pick-files").disabled = true;
  $("magnet-submit").disabled = true;
  renderAddError();
  $("add-dialog").showModal();
}
$("add-button").onclick = openAdd;
$("empty-add").onclick = openAdd;
document.querySelectorAll(".mode-choice").forEach(
  (button) =>
    (button.onclick = () => {
      chosenMode = button.dataset.mode;
      document
        .querySelectorAll(".mode-choice")
        .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      $("pick-files").disabled = busy;
      $("magnet-submit").disabled = busy;
      addError = null;
      renderAddError();
    }),
);
document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.querySelector(".dialog-close").onclick = () => {
    if (dialog.dataset.locked !== "true") dialog.close();
  };
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (
        event.clientX < r.left ||
        event.clientX > r.right ||
        event.clientY < r.top ||
        event.clientY > r.bottom
      )
        if (dialog.dataset.locked !== "true") dialog.close();
    }
  });
});
$("pick-files").onclick = () => $("file-input").click();
function setBusy(value) {
  busy = value;
  $("pick-files").disabled = value || !chosenMode;
  $("magnet-submit").disabled = value || !chosenMode;
}
async function addFiles(files, mode) {
  if (!mode) return;
  if (busy) {
    toast(() => t("toast.busy"), true);
    return;
  }
  setBusy(true);
  try {
    const form = new FormData();
    form.append("mode", mode);
    for (const file of files) form.append("files", file);
    const data = await api("/api/torrents/files", {
      method: "POST",
      body: form,
    });
    for (const result of data.results)
      toast(
        result.ok
          ? () => t("toast.added", { name: result.name, mode })
          : () =>
              `${result.name} : ${localizedError(result.error_code, result.error)}`,
        !result.ok,
      );
    if (data.results.some((r) => r.ok)) $("add-dialog").close();
    render(await api("/api/torrents"));
  } catch (e) {
    toastError(e);
  } finally {
    setBusy(false);
    $("file-input").value = "";
  }
}
$("file-input").onchange = (e) => {
  if (e.target.files.length) addFiles(e.target.files, chosenMode);
};
$("magnet-form").onsubmit = async (e) => {
  e.preventDefault();
  if (!chosenMode || busy) return;
  setBusy(true);
  try {
    await api("/api/torrents/magnet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: chosenMode,
        magnet: $("magnet-input").value.trim(),
      }),
    });
    $("magnet-input").value = "";
    $("add-dialog").close();
    toast(() => t("toast.magnet_added"));
  } catch (error) {
    addError = error;
    renderAddError();
  } finally {
    setBusy(false);
  }
};
$("proxy-status").onclick = () => $("proxy-dialog").showModal();
const settingsUI = installFolderSettings({
  api,
  toast,
  localizedError,
  onLanguageChange,
  t,
});
$("recheck").onclick = async () => {
  try {
    await api("/api/proxy/check", { method: "POST" });
    toast(() => t("toast.proxy_check"));
  } catch (e) {
    toastError(e);
  }
};
installDropZones({
  target: window,
  overlay: $("drop-overlay"),
  zones: Array.from(document.querySelectorAll(".drop-zone")),
  onFiles: addFiles,
  onEnter: () =>
    document
      .querySelectorAll("dialog[open]")
      .forEach((dialog) => dialog.close()),
});
async function init() {
  try {
    bootstrap = await api("/api/bootstrap");
    token = bootstrap.token;
    $("proxy-address").textContent = bootstrap.proxy_address || t("proxy.none");
    $("proxy-choice-address").textContent =
      bootstrap.proxy_address || t("proxy.not_configured");
    if (bootstrap.setup_required) {
      document.body.classList.add("setup-only");
      $("add-button").disabled = true;
      $("empty-add").disabled = true;
      $("proxy-status").disabled = true;
      connectionStatus = "setup";
      renderConnectionStatus();
      await settingsUI.configure(bootstrap);
      return;
    }
    render(await api("/api/torrents"));
    const events = new EventSource("/api/events");
    events.onmessage = (e) => {
      $("live-dot").classList.add("live");
      connectionStatus = "live";
      renderConnectionStatus();
      render(JSON.parse(e.data));
    };
    events.onerror = () => {
      $("live-dot").classList.remove("live");
      connectionStatus = "reconnecting";
      renderConnectionStatus();
    };
  } catch (e) {
    toastError(e);
    connectionStatus = "unavailable";
    renderConnectionStatus();
    setTimeout(init, 3000);
  }
}
onLanguageChange(() => {
  document
    .querySelectorAll(".toast")
    .forEach((node) => node.renderTranslation?.());
  $("proxy-address").textContent = bootstrap.proxy_address || t("proxy.none");
  $("proxy-choice-address").textContent =
    bootstrap.proxy_address || t("proxy.not_configured");
  renderAddError();
  renderConnectionStatus();
  render(state);
});
init();
