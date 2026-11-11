import { describe, expect, it, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { SignIn } from "../src/screens/SignIn";
import { expectNoAxeViolations, json, mockRoutes, renderAt } from "./helpers";

const TENANT = "018f0000-0000-7000-8000-000000000001";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("sign in", () => {
  it("has labelled fields and passes axe", async () => {
    global.fetch = vi.fn(mockRoutes({})) as unknown as typeof fetch;
    const { container } = renderAt("/sign-in", <SignIn />);

    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
    expect(screen.getByLabelText("Workspace ID")).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it("prefills the workspace from an invite link", async () => {
    global.fetch = vi.fn(mockRoutes({})) as unknown as typeof fetch;
    renderAt(`/sign-in?tenant=${TENANT}`, <SignIn />);

    expect(screen.queryByLabelText("Workspace ID")).not.toBeInTheDocument();
  });

  it("refuses a workspace id that is not a uuid", async () => {
    global.fetch = vi.fn(mockRoutes({})) as unknown as typeof fetch;
    renderAt("/sign-in", <SignIn />);

    await userEvent.type(screen.getByLabelText("Email address"), "a@alpha.test");
    await userEvent.type(screen.getByLabelText("Workspace ID"), "not-a-uuid");
    await userEvent.click(screen.getByRole("button", { name: /email me a sign-in link/i }));

    expect(screen.getByText(/should look like/i)).toBeInTheDocument();
  });

  it("sends the link and confirms without revealing whether the address exists", async () => {
    const fetchMock = vi.fn(mockRoutes({ "/v1/auth/magic-link": () => json({ status: "sent" }, 202) }));
    global.fetch = fetchMock as unknown as typeof fetch;
    renderAt(`/sign-in?tenant=${TENANT}`, <SignIn />);

    await userEvent.type(screen.getByLabelText("Email address"), "a@alpha.test");
    await userEvent.click(screen.getByRole("button", { name: /email me a sign-in link/i }));

    expect(await screen.findByRole("heading", { name: /check your email/i })).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ tenant_id: TENANT, email: "a@alpha.test" });
    expect(init.credentials).toBe("include");
  });

  it("shows the retry time from a 429", async () => {
    global.fetch = vi.fn(
      mockRoutes({
        "/v1/auth/magic-link": () => json({ detail: "too many" }, 429, { "retry-after": "120" }),
      }),
    ) as unknown as typeof fetch;
    renderAt(`/sign-in?tenant=${TENANT}`, <SignIn />);

    await userEvent.type(screen.getByLabelText("Email address"), "a@alpha.test");
    await userEvent.click(screen.getByRole("button", { name: /email me a sign-in link/i }));

    await waitFor(() => expect(screen.getByText(/too many attempts/i)).toBeInTheDocument());
  });
});
