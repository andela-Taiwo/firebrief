import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));

export function luminance(hex) {
  const value = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255);
  const channel = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export function token(block, name) {
  const match = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(block);
  if (!match) throw new Error(`missing token --${name}`);
  return match[1];
}

export function checks() {
  const css = readFileSync(join(root, "..", "src/styles/tokens.css"), "utf8");
  const blocks = {
    light: css.slice(css.indexOf(":root"), css.indexOf("@media")),
    dark: css.slice(css.indexOf("@media")),
  };

  const results = [];
  for (const scheme of ["light", "dark"]) {
    const block = blocks[scheme];
    const page = scheme === "light" ? "#ffffff" : "#0e1418";
    const surface = token(block, "surface");
    const pairs = [
      ["ink", page, 4.5],
      ["ink", surface, 4.5],
      ["muted", surface, 4.5],
      ["accent", page, 4.5],
      ["on-accent", token(block, "accent"), 4.5],
      ["verified", surface, 4.5],
      ["warning", surface, 4.5],
      ["danger", surface, 4.5],
      ["border", surface, 3],
      ["border-soft", surface, 1.2],
    ];
    for (const [name, against, minimum] of pairs) {
      results.push({ scheme, name, ratio: ratio(token(block, name), against), minimum });
    }
  }
  return results;
}
