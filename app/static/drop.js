// Kept independent of the rest of the UI so drag/drop routing can be tested.
export function installDropZones({
  target,
  overlay,
  zones,
  onFiles,
  onEnter = () => {},
}) {
  let depth = 0;
  const hasFiles = (event) =>
    event.dataTransfer &&
    Array.from(event.dataTransfer.types).includes("Files");
  function hide() {
    depth = 0;
    overlay.hidden = true;
    zones.forEach((zone) => zone.classList.remove("hover"));
  }
  target.addEventListener("dragenter", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    if (depth === 0) onEnter();
    depth += 1;
    overlay.hidden = false;
  });
  target.addEventListener("dragover", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    overlay.hidden = false;
    const active = event.target.closest?.(".drop-zone");
    zones.forEach((zone) => zone.classList.toggle("hover", zone === active));
  });
  target.addEventListener("dragleave", (event) => {
    if (!hasFiles(event)) return;
    depth = Math.max(0, depth - 1);
    if (
      depth === 0 ||
      event.clientX <= 0 ||
      event.clientY <= 0 ||
      event.clientX >= target.innerWidth ||
      event.clientY >= target.innerHeight
    )
      hide();
  });
  target.addEventListener("drop", (event) => {
    event.preventDefault();
    const mode = event.target.closest?.(".drop-zone")?.dataset.dropMode;
    const files = Array.from(event.dataTransfer?.files || []);
    hide();
    if ((mode === "direct" || mode === "proxy") && files.length)
      onFiles(files, mode);
  });
  target.addEventListener("dragend", hide);
  target.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
  return hide;
}
