import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { About, Accessibility, Help, Landing, NotFound, SignedOut } from "../src/screens/pages";
import { expectNoAxeViolations, renderAt } from "./helpers";

const PAGES = [
  ["/", Landing, /answers about fire safety/i],
  ["/about", About, /how firebrief works/i],
  ["/help", Help, /^help$/i],
  ["/accessibility", Accessibility, /accessibility statement/i],
  ["/signed-out", SignedOut, /you are signed out/i],
  ["/missing", NotFound, /page not found/i],
] as const;

describe("pages", () => {
  for (const [path, Page, heading] of PAGES) {
    it(`${path} has one heading and no accessibility violations`, async () => {
      const { container } = renderAt(path, <Page />);

      expect(screen.getByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
      await expectNoAxeViolations(container);
    });
  }

  it("labels the landing example with its source and capture date", () => {
    renderAt("/", <Landing />);

    expect(screen.getByText(/edition 2019 · captured 11 November 2026/i)).toBeInTheDocument();
  });

  it("opens a quote at its passage with a text fragment", () => {
    renderAt("/", <Landing />);

    const link = screen.getByRole("link", { name: /open the guidance at this passage/i });
    expect(link.getAttribute("href")).toContain("#:~:text=");
  });
});
