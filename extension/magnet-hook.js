// ISOLATED-world, document_start: a real click on a magnet: link goes to the
// worker's route picker instead of the OS handler (EXT-CAP-005). Registered
// with blob-hook.js on the same granted sites; transparent otherwise.
(function installLidMagnetHook() {
  function routeMagnet(event) {
    try {
      // Synthetic page clicks (isTrusted false) must not open a picker.
      if (!event.isTrusted || event.defaultPrevented || event.button !== 0) return;
      const link = event.target?.closest?.("a[href]");
      const href = typeof link?.href === "string" ? link.href.trim() : "";
      if (!/^magnet:\?/i.test(href)) return;
      // Throws once the extension is reloaded: the OS keeps the magnet then.
      chrome.runtime
        .sendMessage({ type: "lid-magnet", magnet: href })
        ?.catch?.(() => {});
      event.preventDefault();
    } catch {
      // Never break the page.
    }
  }
  // A reinjection (extension reloaded, open tab) replaces the previous
  // listener, whose chrome.runtime is gone: the newest one alone handles it.
  const previous = globalThis.__lidMagnetHook;
  if (previous) globalThis.removeEventListener("click", previous, true);
  globalThis.__lidMagnetHook = routeMagnet;
  globalThis.addEventListener("click", routeMagnet, true);
})();
