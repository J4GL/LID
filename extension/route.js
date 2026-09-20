import { messageFor } from "./messages.js";
import { applyI18n, ensureOrigin, lang, t } from "./ui.js";

applyI18n();
const id = new URLSearchParams(location.search).get("id");
const status = document.getElementById("route-status");
const buttons = [...document.querySelectorAll(".route-choice")];
document.getElementById("route-cancel").onclick = () => window.close();

function setStatus(text, kind = "") {
  status.textContent = text;
  status.className = `status ${kind}`;
}

function setBusy(busy) {
  buttons.forEach((button) => {
    button.disabled = busy;
  });
}

async function send(mode) {
  setBusy(true);
  setStatus(t("route_requesting"));
  try {
    const lookup = await chrome.runtime.sendMessage({
      type: "lid-get-pending",
      id,
    });
    if (!lookup?.ok) throw new Error("unexpected_response");
    if (lookup.pending.kind === "file") {
      if (!(await ensureOrigin(lookup.pending.origin))) {
        setStatus(t("route_denied"), "error");
        setBusy(false);
        return;
      }
    }
    setStatus(t("route_sending"));
    const result = await chrome.runtime.sendMessage({
      type: "lid-send",
      id,
      mode,
    });
    if (!result?.ok) throw new Error(result?.code || "unexpected_response");
    window.close();
  } catch (error) {
    setStatus(messageFor(error.message, lang()), "error");
    setBusy(false);
  }
}

buttons.forEach((button) => {
  button.onclick = () => send(button.dataset.mode);
});

chrome.runtime
  .sendMessage({ type: "lid-get-pending", id })
  .then((lookup) => {
    document.getElementById("pending-name").textContent =
      lookup?.pending?.name || "";
  })
  .catch(() => setStatus(messageFor("unexpected_response", lang()), "error"));
