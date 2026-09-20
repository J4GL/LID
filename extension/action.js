import { messageFor } from "./messages.js";
import { applyI18n, lang, serverUrl, t } from "./ui.js";

applyI18n();
const status = document.getElementById("action-status");
status.textContent = t("action_checking");

document.getElementById("open").onclick = async () => {
  await chrome.tabs.create({ url: await serverUrl() });
  window.close();
};
document.getElementById("settings").onclick = () => {
  chrome.runtime.openOptionsPage();
};

const [url, info] = await Promise.all([
  serverUrl(),
  chrome.runtime.sendMessage({ type: "lid-status" }).catch(() => null),
]);
document.getElementById("server-line").textContent = url;
if (info?.ok) {
  status.textContent = t("action_ok");
  status.className = "status ok";
} else {
  status.textContent = messageFor(info?.code || "server_unreachable", lang());
  status.className = "status error";
}
