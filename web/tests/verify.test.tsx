import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Verify } from "../src/screens/Verify";
import { expectNoAxeViolations, json, mockRoutes, renderAt } from "./helpers";

beforeEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/auth/verify");
});

describe("verify", () => {
  it("posts the token and clears it from the address bar", async () => {
    const fetchMock = vi.fn(
      mockRoutes({
        "/v1/auth/verify": () =>
          json({ tenant_id: "t", user_id: "u", role: "owner" }),
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    window.history.replaceState(null, "", "/auth/verify#token=abc.def");

    renderAt("/auth/verify#token=abc.def", <Verify />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ token: "abc.def" });
    expect(window.location.hash).toBe("");
  });

  it("explains a missing token", async () => {
    global.fetch = vi.fn(mockRoutes({})) as unknown as typeof fetch;
    renderAt("/auth/verify", <Verify />);

    expect(await screen.findByText(/missing its token/i)).toBeInTheDocument();
  });

  it("explains an expired or used link", async () => {
    global.fetch = vi.fn(
      mockRoutes({ "/v1/auth/verify": () => json({ detail: "link not usable" }, 400) }),
    ) as unknown as typeof fetch;
    window.history.replaceState(null, "", "/auth/verify#token=abc.def");

    const { container } = renderAt("/auth/verify#token=abc.def", <Verify />);

    expect(await screen.findByText(/cannot be used/i)).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });
});
