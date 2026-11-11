import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";
import { expect } from "vitest";

export function renderAt(path: string, element: ReactElement) {
  window.history.pushState({}, "", path);
  return render(<MemoryRouter initialEntries={[path]}>{element}</MemoryRouter>);
}

export async function expectNoAxeViolations(container: HTMLElement) {
  const results = await axe(container);
  expect(results.violations).toEqual([]);
}

export function mockRoutes(routes: Record<string, (init?: RequestInit) => Response | Promise<Response>>) {
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    const path = new URL(url, "http://localhost").pathname;
    const handler = routes[path];
    if (!handler) {
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    }
    return handler(init);
  };
}

export function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}
