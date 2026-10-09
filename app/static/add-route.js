export function createRoutePicker({ picker, choices, onMissing, onSelect }) {
  let mode = null;
  const select = (button) => {
    mode = button?.dataset.mode ?? null;
    choices.forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    picker.classList.remove("needs-route");
  };
  choices.forEach((button) =>
    button.addEventListener("click", () => {
      select(button);
      onSelect(mode);
    }),
  );
  return {
    get mode() {
      return mode;
    },
    reset: () => select(null),
    require() {
      if (mode) return mode;
      picker.classList.add("needs-route");
      choices[0].focus();
      onMissing();
      return null;
    },
  };
}
