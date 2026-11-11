import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const ANSWER = {
  request_id: "e2e-1",
  answer: "Dead ends must be limited in length to thirty metres. [1]",
  refusal: null,
  redactions: [{ kind: "email", count: 1 }],
  sources: [
    {
      n: 1,
      title: "Fire safety in flats",
      heading: "Escape routes",
      edition: "2019",
      url: "https://www.gov.uk/guidance",
      cited: true,
      quotes: [{ marker: 1, text: "Dead ends must be limited in thirty metres.", start: 0, end: 40 }],
    },
  ],
};

test("asks a question, shows a verified answer and scans it", async ({ page }) => {
  await page.route("**/v1/auth/me", (route) =>
    route.fulfill({ json: { tenant_id: "t", user_id: "u", role: "owner" } }),
  );
  await page.route("**/v1/answers", (route) => route.fulfill({ json: ANSWER }));

  await page.goto("/ask");
  await page.getByLabel(/your question/i).fill("How long can a dead end be?");
  await page.getByRole("button", { name: /^ask$/i }).click();

  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible();
  await expect(page.getByRole("link", { name: /source 1: fire safety in flats/i })).toBeVisible();
  await expect(page.getByText(/we removed 1 email address/i)).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("sign-in page is keyboard reachable and clean", async ({ page }) => {
  await page.goto("/sign-in?tenant=018f0000-0000-7000-8000-000000000001");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: /skip to main content/i })).toBeFocused();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("the stylesheet actually applies in the browser", async ({ page }) => {
  // The CSP once blocked Vite's inline styles: the page rendered, but unstyled. Axe does
  // not catch that, so assert the cascade directly.
  await page.goto("/sign-in?tenant=018f0000-0000-7000-8000-000000000001");

  const applied = await page.evaluate(() => ({
    sheets: document.styleSheets.length,
    font: getComputedStyle(document.body).fontFamily,
    margin: getComputedStyle(document.body).margin,
    headingSize: getComputedStyle(document.querySelector("h1")!).fontSize,
  }));

  expect(applied.sheets).toBeGreaterThan(0);
  expect(applied.font).not.toContain("Times");
  expect(applied.margin).toBe("0px");
  expect(applied.headingSize).toBe("30px");
});

test("an enabled primary button is the accent colour, not the disabled grey", async ({ page }) => {
  await page.goto("/sign-in?tenant=018f0000-0000-7000-8000-000000000001");
  await page.getByLabel("Email address").fill("dev@firebrief.local");

  const button = page.getByRole("button", { name: /email me a sign-in link/i });
  await expect(button).toBeEnabled();
  await expect(button).toHaveCSS("background-color", "rgb(11, 92, 173)");
});
