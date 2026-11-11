/** Recompute WCAG contrast from the CSS tokens, so a palette change cannot slip past review. */
import { checks } from "./contrast-lib.mjs";

const results = checks();
console.log(
  results.map((c) => `${c.scheme} ${c.name}: ${c.ratio.toFixed(2)}:1 (needs ${c.minimum})`).join("\n"),
);
const failures = results.filter((c) => c.ratio < c.minimum);
if (failures.length > 0) {
  console.error(`\n${failures.length} contrast failure(s)`);
  process.exit(1);
}
console.log("\nall contrast checks pass");
