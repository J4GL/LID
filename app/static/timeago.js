// Pure relative-age formatter for the last uploaded packet of a seed.
// Timestamps are seconds since the Unix epoch (backend `last_upload_at`);
// `now` uses the same unit so tests stay deterministic. `lang` is "fr"
// or anything else (English fallback). No DOM, no imports.

const HOUR = 3600;
const DAY = 24 * HOUR;

export function formatAgo(timestamp, now, lang) {
  const french = lang === "fr";
  if (timestamp === null || timestamp === undefined) {
    return french ? "Jamais partagé" : "Never shared";
  }
  const diff = Math.max(0, Math.floor(now - timestamp));
  if (diff < 60) return french ? "à l'instant" : "just now";
  if (diff < HOUR) {
    const minutes = Math.floor(diff / 60);
    return french ? `il y a ${minutes} min` : `${minutes}m ago`;
  }
  if (diff < DAY) {
    const hours = Math.floor(diff / HOUR);
    return french ? `il y a ${hours} h` : `${hours}h ago`;
  }
  const days = Math.floor(diff / DAY);
  if (french) return `il y a ${days} j`;
  return days === 1 ? "1 day ago" : `${days} days ago`;
}
