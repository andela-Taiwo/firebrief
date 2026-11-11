import { describe, expect, it, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";
import { Ask } from "../src/screens/Ask";
import { expectNoAxeViolations, json, mockRoutes } from "./helpers";

const ANSWER = {
  request_id: "req-1",
  answer: "Dead ends must be limited in length to thirty metres. [1]",
  refusal: null,
  redactions: [],
  sources: [
    {
      n: 1,
      title: "Fire safety in flats",
      heading: "Escape routes",
      edition: "2019",
      url: "https://www.gov.uk/guidance",
      cited: true,
      quotes: [{ marker: 1, text: "Dead ends must be limited to thirty metres.", start: 0, end: 44 }],
    },
  ],
};

const REFUSAL = {
  request_id: "req-2",
  answer: null,
  refusal: {
    reason: "unverified",
    message: "An answer was withheld.",
    details: ['claim 1, [1]: missing_span — "Dead ends must be limited to ten metres."'],
  },
  redactions: [],
  sources: [],
};

function renderAsk(path = "/ask") {
  window.history.pushState({}, "", path);
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/ask" element={<Ask />} />
        <Route path="/sign-in" element={<p>Sign in page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function askAQuestion() {
  await userEvent.type(screen.getByLabelText(/your question/i), "How long can a dead end be?");
  await userEvent.click(screen.getByRole("button", { name: /^ask$/i }));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("ask", () => {
  it("renders an empty state that passes axe", async () => {
    global.fetch = vi.fn(mockRoutes({ "/v1/auth/me": () => json({ tenant_id: "t", user_id: "u", role: "owner" }) })) as unknown as typeof fetch;
    const { container } = renderAsk();
    await screen.findByRole("heading", { name: /ask about fire safety guidance/i });
    await expectNoAxeViolations(container);
  });

  it("sends a signed-out reader to sign in", async () => {
    global.fetch = vi.fn(mockRoutes({ "/v1/auth/me": () => json({ detail: "no session" }, 401) })) as unknown as typeof fetch;
    renderAsk();

    expect(await screen.findByText("Sign in page")).toBeInTheDocument();
  });

  it("shows the answer, its markers and sources, and moves focus to the answer", async () => {
    global.fetch = vi.fn(
      mockRoutes({
        "/v1/auth/me": () => json({ tenant_id: "t", user_id: "u", role: "owner" }),
        "/v1/answers": () => json(ANSWER),
      }),
    ) as unknown as typeof fetch;
    const { container } = renderAsk();
    await screen.findByRole("heading", { name: /ask about fire safety guidance/i });

    await askAQuestion();

    const heading = await screen.findByRole("heading", { name: "Answer" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByRole("link", { name: /source 1: fire safety in flats, edition 2019/i })).toBeInTheDocument();
    expect(screen.getByText(/verified against 1 quote/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open the guidance at this passage/i })).toHaveAttribute(
      "href",
      expect.stringContaining("#:~:text="),
    );
    await expectNoAxeViolations(container);
  });

  it("explains a refusal and moves focus to it", async () => {
    global.fetch = vi.fn(
      mockRoutes({
        "/v1/auth/me": () => json({ tenant_id: "t", user_id: "u", role: "owner" }),
        "/v1/answers": () => json(REFUSAL),
      }),
    ) as unknown as typeof fetch;
    const { container } = renderAsk();
    await screen.findByRole("heading", { name: /ask about fire safety guidance/i });

    await askAQuestion();

    const heading = await screen.findByRole("heading", { name: /could not verify every quote/i });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByText(/one quote did not match/i)).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it("states the retry time on a 429", async () => {
    global.fetch = vi.fn(
      mockRoutes({
        "/v1/auth/me": () => json({ tenant_id: "t", user_id: "u", role: "owner" }),
        "/v1/answers": () => json({ detail: "too many" }, 429, { "retry-after": "60" }),
      }),
    ) as unknown as typeof fetch;
    renderAsk();
    await screen.findByRole("heading", { name: /ask about fire safety guidance/i });

    await askAQuestion();

    expect(await screen.findByRole("heading", { name: /did not work/i })).toBeInTheDocument();
    expect(screen.getByText(/too many questions\. try again at/i)).toBeInTheDocument();
  });

  it("says nothing was charged when the service is unavailable", async () => {
    global.fetch = vi.fn(
      mockRoutes({
        "/v1/auth/me": () => json({ tenant_id: "t", user_id: "u", role: "owner" }),
        "/v1/answers": () => json({ detail: "unavailable" }, 503),
      }),
    ) as unknown as typeof fetch;
    renderAsk();
    await screen.findByRole("heading", { name: /ask about fire safety guidance/i });

    await askAQuestion();

    expect(await screen.findByText(/nothing was charged/i)).toBeInTheDocument();
  });

  it("reports a network failure in plain English", async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input), "http://localhost").pathname;
      if (path === "/v1/auth/me") return json({ tenant_id: "t", user_id: "u", role: "owner" });
      throw new TypeError("offline");
    }) as unknown as typeof fetch;
    renderAsk();
    await screen.findByRole("heading", { name: /ask about fire safety guidance/i });

    await askAQuestion();

    expect(await screen.findByText(/could not reach firebrief/i)).toBeInTheDocument();
  });
});
