// MAIN-world, document_start: retains small page blobs so the worker can
// read them without fetch() — page CSP may forbid fetch(blob:), and pages
// may revoke the URL within milliseconds. Registered dynamically per
// granted origin (EXT-SW-006); transparent otherwise.
(function installLidBlobHook() {
  if (window.__lidBlobHookInstalled) return;
  window.__lidBlobHookInstalled = true;
  const MAX_BLOB_BYTES = 10 * 1024 * 1024;
  const MAX_BLOBS = 8;
  const stash = new Map();
  window.__lidBlobs = stash;
  const nativeCreate = URL.createObjectURL.bind(URL);
  URL.createObjectURL = function lidCreateObjectURL(object, ...rest) {
    const url = nativeCreate(object, ...rest);
    try {
      if (
        object &&
        typeof object.arrayBuffer === "function" &&
        typeof object.size === "number" &&
        object.size > 0 &&
        object.size <= MAX_BLOB_BYTES
      ) {
        stash.set(url, object);
        while (stash.size > MAX_BLOBS) stash.delete(stash.keys().next().value);
      }
    } catch {
      // Never break the page.
    }
    return url;
  };
  // Anchor of the last pointer click, in screen CSS px, so the worker can
  // open the route picker right under the clicked link (EXT-CAP-004).
  // Keyboard activations carry no screen position: keep the previous one.
  function recordClick(event) {
    try {
      if (event.screenX === 0 && event.clientX === 0) return;
      const target =
        event.target.closest("a,button,[role=button],input") || event.target;
      const rect = target.getBoundingClientRect();
      const dx = event.screenX - event.clientX;
      const dy = event.screenY - event.clientY;
      window.__lidLastClick = {
        left: dx + rect.left,
        right: dx + rect.right,
        bottom: dy + rect.bottom,
        at: Date.now(),
      };
    } catch {
      // Never break the page.
    }
  }
  if (typeof window.addEventListener === "function") {
    window.addEventListener("pointerdown", recordClick, true);
    window.addEventListener("contextmenu", recordClick, true);
  }
})();
