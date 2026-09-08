export function installFolderSettings({ api, toast, localizedError, onLanguageChange, t }) {
  const $ = (id) => document.getElementById(id);
  const dialog = $("folders-dialog");
  const form = $("folder-settings-form");
  let activeField, currentPath = "", nextOffset = null, requestNumber = 0;
  let saving = false, step = 1, setupRequired = false, settings = null, lastError = null;

  function renderError() {
    let message = "";
    if (typeof lastError === "function") message = lastError();
    else if (lastError instanceof Error) {
      message = localizedError(lastError.code, lastError.message);
      const fields = Object.entries(lastError.fields || {});
      if (fields.length) message += ` ${fields.map(([name, detail]) => `${name}: ${detail}`).join(" · ")}`;
    }
    else message = lastError || "";
    $("folders-error").textContent = message;
    $("folders-error").hidden = !message;
  }
  function error(message = null) { lastError = message; renderError(); }
  function number(id) { return Number($(id).value); }
  function payload() {
    return {
      server: { host: $("server-host").value, port: number("server-port") },
      storage: {
        downloads: $("downloads-folder").value.trim(),
        completed: $("move-enabled").checked && $("completed-folder").value.trim() ? $("completed-folder").value.trim() : null,
        state: $("state-folder").value.trim(),
      },
      direct: { port: number("direct-port"), upnp: $("direct-upnp").checked },
      proxy: {
        enabled: $("proxy-enabled").checked,
        host: $("proxy-host").value.trim(),
        port: number("proxy-port"),
        username: $("proxy-username").value,
        password: $("proxy-password").value,
        clear_password: $("proxy-clear-password").checked,
        udp: $("proxy-udp").value,
        timeout: number("proxy-timeout"),
        check_interval: number("proxy-check-interval"),
        dns_server: $("proxy-dns").value.trim(),
        dht_bootstrap: $("proxy-dht").value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
      },
      seeding: {
        upload_limit: number("upload-limit"), download_limit: number("download-limit"),
        connections: number("connections-limit"), file_pool_size: number("file-pool-size"),
        save_interval: number("save-interval"),
      },
    };
  }
  function fill(data) {
    const value = data.values;
    settings = data;
    $("downloads-folder").value = value.storage.downloads;
    $("completed-folder").value = value.storage.completed || "";
    $("move-enabled").checked = !!value.storage.completed;
    $("state-folder").value = value.storage.state;
    $("server-host").value = value.server.host;
    $("server-port").value = value.server.port;
    $("direct-port").value = value.direct.port;
    $("direct-upnp").checked = value.direct.upnp;
    $("proxy-enabled").checked = value.proxy.enabled;
    $("proxy-host").value = value.proxy.host;
    $("proxy-port").value = value.proxy.port;
    $("proxy-username").value = value.proxy.username;
    $("proxy-password").value = "";
    $("proxy-password").placeholder = value.proxy.password_configured ? t("settings.password_keep") : "";
    $("proxy-clear-password").checked = false;
    $("proxy-udp").value = value.proxy.udp;
    $("proxy-timeout").value = value.proxy.timeout;
    $("proxy-check-interval").value = value.proxy.check_interval;
    $("proxy-dns").value = value.proxy.dns_server;
    $("proxy-dht").value = value.proxy.dht_bootstrap.join("\n");
    $("upload-limit").value = value.seeding.upload_limit;
    $("download-limit").value = value.seeding.download_limit;
    $("connections-limit").value = value.seeding.connections;
    $("file-pool-size").value = value.seeding.file_pool_size;
    $("save-interval").value = value.seeding.save_interval;
    $("settings-load-error").hidden = !data.load_error;
    $("settings-load-error").textContent = data.load_error || "";
    syncStorage(); syncProxy();
  }
  function syncStorage() {
    const available = !!$("completed-folder").value.trim();
    $("move-enabled").disabled = !available;
    if (!available) $("move-enabled").checked = false;
  }
  function syncProxy() {
    const enabled = $("proxy-enabled").checked;
    document.querySelectorAll("[data-proxy-fields] input, [data-proxy-fields] select").forEach((field) => { field.disabled = !enabled; });
    $("settings-proxy-test").disabled = !enabled;
  }
  function renderReview() {
    const value = payload();
    $("settings-review").textContent = t("settings.review", {
      host: value.server.host, port: value.server.port, downloads: value.storage.downloads,
      completed: value.storage.completed || t("settings.no_completed"),
      proxy: value.proxy.enabled ? `${value.proxy.host}:${value.proxy.port}` : t("settings.disabled"),
    });
  }
  function showStep(value) {
    step = Math.max(1, Math.min(3, value));
    document.querySelectorAll("[data-step]").forEach((page) => { page.hidden = Number(page.dataset.step) !== step; });
    document.querySelectorAll("[data-step-button]").forEach((button) => {
      if (Number(button.dataset.stepButton) === step) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    $("settings-previous").hidden = step === 1;
    $("settings-next").hidden = step === 3;
    $("folders-save").hidden = step !== 3;
    if (step === 3) renderReview();
    error();
  }
  function stepValid() {
    const page = document.querySelector(`[data-step="${step}"]`);
    const invalid = [...page.querySelectorAll("input, select, textarea")].find((field) => !field.disabled && !field.checkValidity());
    if (!invalid) return true;
    invalid.reportValidity(); invalid.focus(); return false;
  }
  async function open(force = false) {
    setupRequired = force;
    dialog.dataset.locked = force ? "true" : "false";
    dialog.querySelector(".dialog-close").hidden = force;
    $("setup-banner").hidden = !force;
    $("settings-restarting").hidden = true;
    form.hidden = false; $("folder-browser").hidden = true;
    error(); showStep(1);
    if (!dialog.open) dialog.showModal();
    $("folders-save").disabled = true;
    try { fill(await api("/api/settings")); $("folders-save").disabled = false; }
    catch (exception) { error(exception); }
  }
  $("storage-button").onclick = () => open(false);
  $("settings-language-toggle").onclick = () => $("language-toggle").click();
  $("completed-folder").addEventListener("input", syncStorage);
  $("proxy-enabled").addEventListener("change", syncProxy);
  $("proxy-password").addEventListener("input", () => { if ($("proxy-password").value) $("proxy-clear-password").checked = false; });
  $("proxy-clear-password").addEventListener("change", () => { if ($("proxy-clear-password").checked) $("proxy-password").value = ""; });
  document.querySelectorAll("[data-step-button]").forEach((button) => {
    button.onclick = () => { const target = Number(button.dataset.stepButton); if (target <= step || stepValid()) showStep(target); };
  });
  $("settings-next").onclick = () => { if (stepValid()) showStep(step + 1); };
  $("settings-previous").onclick = () => showStep(step - 1);
  $("settings-proxy-test").onclick = async () => {
    if (!stepValid()) return;
    const button = $("settings-proxy-test"), result = $("settings-proxy-result");
    button.disabled = true; result.textContent = t("settings.testing_proxy");
    try {
      const diagnosis = await api("/api/settings/proxy-check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload()) });
      result.className = `mode-help ${diagnosis.tcp ? "success" : "warning"}`;
      result.textContent = diagnosis.tcp ? (diagnosis.udp ? t("settings.proxy_tcp_udp_ok") : t("settings.proxy_tcp_ok")) : t("settings.proxy_failed");
    } catch (exception) {
      result.className = "mode-help warning";
      result.textContent = localizedError(exception.code, exception.message);
    } finally { button.disabled = false; }
  };
  function folderButton(name, path, shortcutKey = null) {
    const button = document.createElement("button");
    button.type = "button"; button.className = "folder-entry"; button.textContent = name; button.title = path || "";
    if (shortcutKey) button.dataset.shortcutKey = shortcutKey;
    button.onclick = () => browse(path); return button;
  }
  async function browse(path, append = false) {
    const number = ++requestNumber; error();
    $("folder-choose").disabled = true; $("folder-more").disabled = true; $("folder-loading").hidden = false;
    try {
      const query = new URLSearchParams();
      if (path) query.set("path", path);
      if (append && nextOffset !== null) query.set("offset", nextOffset);
      const listing = await api(`/api/storage/directories?${query}`);
      if (number !== requestNumber) return;
      currentPath = listing.path; $("browser-path").value = currentPath;
      $("folder-parent").disabled = listing.parent === listing.path;
      $("folder-parent").onclick = () => browse(listing.parent);
      if (!append) $("folder-list").replaceChildren();
      listing.directories.forEach((item) => $("folder-list").append(folderButton(item.name, item.path)));
      $("folder-empty").hidden = !!$("folder-list").children.length;
      $("folder-shortcuts").replaceChildren(...listing.shortcuts.map((item) => folderButton(item.key ? t(`folders.shortcut.${item.key}`) : item.name, item.path, item.key)));
      nextOffset = listing.next_offset; $("folder-more").hidden = nextOffset === null; $("folder-choose").disabled = false;
    } catch (exception) { if (number === requestNumber) error(exception); }
    finally { if (number === requestNumber) { $("folder-loading").hidden = true; $("folder-more").disabled = false; } }
  }
  for (const button of dialog.querySelectorAll("[data-browse-field]")) {
    button.onclick = () => { activeField = $(button.dataset.browseField); form.hidden = true; $("folder-browser").hidden = false; browse(activeField.value.trim() || null); };
  }
  $("browser-path-form").onsubmit = (event) => { event.preventDefault(); browse($("browser-path").value.trim()); };
  $("folder-more").onclick = () => browse(currentPath, true);
  function browserBack() { ++requestNumber; $("folder-browser").hidden = true; form.hidden = false; activeField?.focus(); }
  $("folder-back").onclick = browserBack;
  $("folder-choose").onclick = () => { activeField.value = currentPath; if (activeField.id === "completed-folder") $("move-enabled").checked = true; syncStorage(); browserBack(); };
  form.onsubmit = async (event) => {
    event.preventDefault(); if (saving || !stepValid()) return;
    saving = true; error(); $("folders-save").disabled = true; $("folders-save").textContent = t("settings.saving");
    try {
      const body = payload();
      await api("/api/settings/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const result = await api("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (result.restart) {
        form.hidden = true; $("settings-restarting").hidden = false;
        $("settings-future-url").href = result.url; $("settings-future-url").textContent = result.url;
        waitForRestart(result.url, result.instance_id);
      } else { dialog.close(); toast(() => t("toast.settings_saved")); }
    } catch (exception) { error(exception); }
    finally { saving = false; $("folders-save").disabled = false; $("folders-save").textContent = t("settings.save"); }
  };
  async function waitForRestart(url, previousInstance) {
    const endpoint = new URL("/api/ready", url);
    while (true) {
      try {
        const response = await fetch(endpoint, { cache: "no-store" });
        const status = await response.json();
        if (status.ready && status.instance_id !== previousInstance) {
          window.location.assign(url);
          return;
        }
      } catch {}
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  dialog.addEventListener("cancel", (event) => { if (setupRequired) event.preventDefault(); });
  onLanguageChange(() => {
    renderError(); if (step === 3) renderReview();
    $("settings-language-toggle").querySelectorAll("span").forEach((node) => {
      node.classList.toggle("active", node.dataset.language === document.documentElement.lang);
    });
    if (settings) $("proxy-password").placeholder = settings.values.proxy.password_configured ? t("settings.password_keep") : "";
    document.querySelectorAll("[data-shortcut-key]").forEach((button) => { button.textContent = t(`folders.shortcut.${button.dataset.shortcutKey}`); });
  });
  return { open, configure: (bootstrap) => bootstrap.setup_required && open(true) };
}
