import { describe, expect, it } from "vitest";
// @ts-expect-error -- plain ESM helper shared with the CLI
import { checks } from "../scripts/contrast-lib.mjs";

describe("design tokens", () => {
  it("meets WCAG AA contrast in both schemes", () => {
    const results = checks() as Array<{ scheme: string; name: string; ratio: number; minimum: number }>;
    const failures = results.filter((check) => check.ratio < check.minimum);
    expect(failures, JSON.stringify(failures)).toEqual([]);
  });

  it("keeps the dark border above 3:1 with margin", () => {
    const results = checks() as Array<{ scheme: string; name: string; ratio: number }>;
    const border = results.find((check) => check.scheme === "dark" && check.name === "border");
    expect(border!.ratio).toBeGreaterThan(3.4);
  });
});
