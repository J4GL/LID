const STORAGE_KEY = "p2p-compact";

export function installCompactToggle({ button, list, storage }) {
  let compact = false;
  try {
    compact = storage.getItem(STORAGE_KEY) === "1";
  } catch {}
  const apply = () => {
    list.classList.toggle("compact", compact);
    button.setAttribute("aria-pressed", String(compact));
  };
  button.addEventListener("click", () => {
    compact = !compact;
    apply();
    try {
      storage.setItem(STORAGE_KEY, compact ? "1" : "0");
    } catch {}
  });
  apply();
}
