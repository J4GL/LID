import assert from "node:assert/strict";
import test from "node:test";

import { formatAgo } from "../app/static/timeago.js";

const HOUR = 3600;
const DAY = 24 * HOUR;
const NOW = 1_700_000_000;

test("seeding timeago SEED-LASTUP-001 formats relative age in French and English", () => {
  assert.equal(formatAgo(NOW - 6 * HOUR, NOW, "en"), "6h ago");
  assert.equal(formatAgo(NOW - 2 * DAY, NOW, "en"), "2 days ago");
  assert.equal(formatAgo(NOW - 6 * HOUR, NOW, "fr"), "il y a 6 h");
  assert.equal(formatAgo(NOW - 2 * DAY, NOW, "fr"), "il y a 2 j");
  assert.equal(formatAgo(null, NOW, "en"), "Never shared");
  assert.equal(formatAgo(null, NOW, "fr"), "Jamais partagé");
  assert.equal(formatAgo(NOW - 30, NOW, "en"), "just now");
  assert.equal(formatAgo(NOW - 30, NOW, "fr"), "à l'instant");
  assert.equal(formatAgo(NOW - 5 * 60, NOW, "en"), "5m ago");
  assert.equal(formatAgo(NOW - 5 * 60, NOW, "fr"), "il y a 5 min");
  assert.equal(formatAgo(NOW - DAY, NOW, "en"), "1 day ago");
});
