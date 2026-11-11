# web-ui: the Firebrief product surface

**Status:** Planning — awaiting approval
**Depends on:** `api-hardening` (all endpoints exist) · **Unblocks:** a demo someone can use

## 1. Information architecture

Two experiences in one deployment, deliberately separated:

```
Public, static, indexed           App, client-rendered, noindex
/                    landing      /sign-in     request a magic link
/about               how it works /auth/verify  consume #token, then /ask
/help                using it     /ask          ask a question, read the answer
/accessibility       statement    /signed-out   after logout
/sitemap.xml, /robots.txt
```

Why separate: the public pages must be static HTML for SEO and LCP, and they do not need
JavaScript at all. The app needs a session and state, so it is a single-page app. The two
share CSS and components, not a runtime.

## 2. Pages

| # | Route | Purpose | Render |
|---|---|---|---|
| 1 | `/` | What Firebrief does, one real verified answer shown as proof, sign-in CTA | Static |
| 2 | `/about` | Who it is for, how verification works, what it will not do | Static |
| 3 | `/help` | How to ask a good question, what each refusal means, contact | Static |
| 4 | `/accessibility` | Accessibility statement: conformance, known gaps, how to report | Static |
| 5 | `/sign-in` | Email + workspace ID → magic link sent | SPA |
| 6 | `/auth/verify` | Read `#token`, POST `/v1/auth/verify`, clear the fragment, continue | SPA |
| 7 | `/ask` | The product: question, progress, answer or refusal, sources | SPA |
| 8 | `/signed-out` | Confirmation, link back to sign in | SPA |
| 9 | `*` | Not found | SPA |

The answer is not addressable by URL: nothing is stored server-side yet, so a link to an
answer would 404 on reload. Recorded as a follow-up rather than faked with local state.

## 3. Components

**Shell**
- `SkipLink` — first focusable element, targets `#main`.
- `PageHeader` — product mark, current section, sign-out when signed in.
- `PageFooter` — licence, accessibility link, "guidance is not advice" line.
- `Layout` — landmark regions (`header`, `nav`, `main`, `footer`), skip target.

**Asking**
- `AskForm` — labelled textarea, character counter (max 2000), submit, example questions.
- `ExampleQuestion` — a button that fills the textarea, not a link.
- `AnswerProgress` — status text, elapsed timer, `aria-live="polite"`.
- `AnswerCard` — the answer prose, with inline citation markers `[1]` rendered as links to
  the matching source card.
- `SourceList` — numbered source cards: title, section heading, edition, link to the
  document, and the verified quote(s) with the passage shown in full.
- `QuoteBlock` — blockquote with `cite`, no decorative quotes.
- `RefusalPanel` — reason heading, plain-English explanation, what to try next, the
  evidence considered (collapsed).
- `VerificationBadge` — icon **and** text ("Verified against 2 quotes"), never colour alone.
- `RedactionNotice` — "We removed 1 email address before searching", shown once.

**Auth**
- `SignInForm` — email and workspace ID, both labelled, with help text.
- `MagicLinkSent` — confirmation, "check your email", resend disabled for 60s.
- `SessionGate` — resolves `/v1/auth/me`; 401 sends to `/sign-in?next=`.

**Primitives**
- `Button` (primary/secondary/quiet), `Field` (label, hint, error, `aria-describedby`),
  `Alert` (info/warning/error, live region), `Skeleton` (reserved height, no layout shift),
  `VisuallyHidden`.

## 4. Design tokens

Colours verified with the WCAG relative-luminance formula; the ratio is against the
background it is used on.

| Token | Light | On | Ratio | Use |
|---|---|---|---|---|
| `--ink` | `#101820` | white | 17.89:1 | body text |
| `--ink` | `#101820` | `--surface` | 16.51:1 | text on panels |
| `--muted` | `#4A5560` | white | 7.61:1 | secondary text, metadata |
| `--accent` | `#0B5CAD` | white | 6.67:1 | links, primary button |
| `--on-accent` | `#FFFFFF` | accent | 6.67:1 | button label |
| `--border` | `#767F88` | white | 4.07:1 | input and control borders (needs 3:1) |
| `--border-soft` | `#B9C1C9` | white | 1.82:1 | decorative dividers only, never a control |
| `--verified` | `#0F6E3D` | white | 6.33:1 | verified badge (with icon and text) |
| `--warning` | `#7A4B00` | white | 7.41:1 | warnings |
| `--danger` | `#A02020` | white | 7.71:1 | errors |
| `--surface` | `#F4F6F7` | — | — | panels, source cards |

Dark scheme (`prefers-color-scheme: dark`):

| Token | Dark | On | Ratio |
|---|---|---|---|
| `--ink` | `#E8EDF1` | `#0E1418` | 15.74:1 |
| `--muted` | `#A7B4BF` | `#0E1418` | 8.77:1 |
| `--accent` | `#8CBEF0` | `#0E1418` | 9.49:1 |
| `--border` | `#57646F` | `#0E1418` | 3.05:1 |
| `--surface` | `#16202A` | `#0E1418` | 1.13:1 (separation only, never text) |

**Type scale** (rem, line-height):

| Step | Size | Line height | Use |
|---|---|---|---|
| display | 2.375rem / 38px | 1.15 | landing headline |
| h1 | 1.875rem / 30px | 1.2 | page title |
| h2 | 1.5rem / 24px | 1.25 | section |
| h3 | 1.25rem / 20px | 1.3 | card title |
| body-lg | 1.125rem / 18px | 1.6 | answer prose |
| body | 1rem / 16px | 1.6 | default |
| small | 0.875rem / 14px | 1.5 | metadata, never below 14px |

**Spacing** (px): 4, 8, 12, 16, 24, 32, 48, 64, 96. Radius 4px controls, 8px cards.
Measure 68ch for prose. Focus ring: 3px `--accent` with 2px offset, so it is visible on
both light and dark surfaces and on accent buttons.

Motion: one 120ms opacity transition, disabled under `prefers-reduced-motion`.

## 5. States

### `/ask`

| State | What the user sees |
|---|---|
| Empty | Heading, one sentence of instruction, two example questions, disabled submit until 2+ characters |
| Loading | "Searching the guidance…" and after 3s "Still working — this takes a few seconds." Elapsed timer. Live region announces once |
| Success | Answer prose with `[1]` markers, verification badge, numbered sources with quotes |
| Refused | Reason heading, plain English, what to try next, evidence considered |
| 401 | Redirect to `/sign-in?next=/ask` with "Your session ended. Sign in to continue." |
| 429 | "Too many questions. Try again at 14:32." Time from `Retry-After` |
| 503 | "Firebrief is temporarily unavailable. Nothing was charged. Try again." |
| Network error | "We could not reach Firebrief. Check your connection and try again." with retry |

### Refusal copy

| Reason | Copy |
|---|---|
| `no_sources` | "The guidance we hold does not cover this. Try rephrasing with the building type or the regulation." |
| `insufficient_evidence` | "The sources do not answer this question. Try asking about one specific requirement." |
| `unverified` | "We could not verify every quote in the answer, so we are not showing it. Try a narrower question." |
| `truncated` | "The answer was cut off before it could be checked. Try a narrower question." |
| `budget_exhausted` | "This question would exceed your usage limit." + reset time when present |
| `duplicate_request` | "This request has already been answered. Ask again as a new question." |
| `model_unavailable` / `budget_unavailable` | "Firebrief is temporarily unavailable. Nothing was charged." |

### Other screens

| Screen | Loading | Empty | Error |
|---|---|---|---|
| `/` , `/about`, `/help`, `/accessibility` | static, no loading | n/a | n/a |
| `/sign-in` | button shows "Sending…" and is disabled | — | 429 with time, 503, network |
| `/auth/verify` | "Signing you in…", then redirect | missing token → error with link | invalid/used token → "This link cannot be used. Request a new one." |
| `/signed-out` | — | — | — |

## 6. Accessibility plan

- Landmarks: `header`, `nav`, `main`, `footer`; one `h1` per page; headings in order.
- Skip link to `#main`, visible on focus.
- Focus ring 3px accent with 2px offset; never `outline: none` without a replacement.
- Submit is a real `button`; examples are `button`s that fill the field; no click-only divs.
- Fields have `<label for>`; hints and errors linked with `aria-describedby`; errors also
  announced in a live region and focus moves to the first invalid field.
- Results and status changes in `aria-live="polite"`; the progress timer is
  `aria-hidden` so it does not announce every second.
- Quote marks and badges use text plus an icon shape, never colour alone.
- `prefers-reduced-motion` disables transitions; `prefers-color-scheme` switches tokens.
- 200% zoom: no fixed heights on text containers, no horizontal scroll at 320px width.
- Touch targets ≥ 44×44 for primary actions, ≥ 24×24 minimum for inline controls.

## 7. SEO plan (public pages)

- Public pages are rendered to **static HTML at build time** (`react-dom/server`), no
  hydration, so LCP is text and there is no client render for crawlers.
- Unique `<title>`, meta description, canonical, Open Graph and Twitter tags per page.
- One `h1`, descriptive link text ("How verification works", not "Read more").
- `sitemap.xml` and `robots.txt` generated at build; app routes carry
  `<meta name="robots" content="noindex">`.
- No images above the fold on the landing page except an inline SVG diagram with `role="img"`
  and a descriptive label, so CLS stays at 0.

## 8. Testing plan

- Vitest + React Testing Library per screen: rendering, states table above, keyboard flow.
- `jest-axe` on every screen's rendered output, asserting no violations.
- A token test that recomputes contrast ratios from the CSS variables, so a palette change
  that breaks 4.5:1 fails CI rather than review.
- Manual checks recorded in the self-review: keyboard-only, 200% zoom, reduced motion.

## 9. Decisions I need approved

1. **Progress stages.** The API has no streaming or stage endpoint, so "searching / drafting
   / verifying" cannot be real. I propose one honest status ("Searching the guidance…",
   then "Still working…") plus an elapsed timer, and a follow-up to add SSE stage events to
   the API. Showing three fake stage labels would be a lie about what the system is doing.
2. **Deep-linking to a passage.** Sources carry the document URL, section heading, edition
   and the quote's character offsets *within our chunk*, not an anchor in the GOV.UK page.
   I propose linking to the document and showing the quoted passage in the card, with an
   explicit line that the link opens the document. True passage links need anchors from
   ingestion.
3. **Sign-in needs a workspace ID.** `/v1/auth/magic-link` requires `tenant_id`, which a
   person does not know. I propose an email + workspace ID form, accepting `?tenant=<uuid>`
   from an invite link. The alternative is email-first login, which needs a new narrow
   endpoint (recorded in the auth plan).

## 10. Out of scope

Saved answers, history, team management, admin usage dashboard, dark-mode toggle (the OS
preference is respected), i18n, PDF export.

## Build notes

Built as approved: one honest status with an elapsed timer, quotes in the card with a
`#:~:text=` fragment on the document link, workspace ID from `?tenant=` with a labelled
fallback, focus moved to the answer or refusal heading, `Retry-After` driving the resend
time, and a static build for the public pages.

**Two artefacts, one build.** `dist/index.html` (and `/about`, `/help`, `/accessibility`)
are static HTML with **no JavaScript**; `dist/app.html` is the SPA shell with the bundle and
`noindex`. The server rewrites app routes to `app.html`. Without that rewrite, the app
routes would serve the landing page and never boot — the first build did exactly that until
the shell was preserved separately.

**Deliberately absent:** no UI library (React + three primitives was enough), no icon font,
no web font, no third-party script. The system font stack keeps the CSP at `default-src
'self'` and removes a render-blocking request.

## Self-review

### Accessibility (WCAG 2.2 AA)

| Item | Status | How verified |
|---|---|---|
| Landmarks, one `h1`, logical heading order | **Pass** | `Layout` renders `header`/`nav`/`main`/`footer`; tests assert exactly one `h1` on every page; axe checks heading order |
| Full keyboard use, visible focus | **Pass (automated part)** | Playwright confirms the first Tab lands on the skip link; focus moves to the answer/refusal heading on result. Focus ring is `3px` accent with offset — reviewed in CSS, not visually screenshotted |
| Skip link | **Pass** | Rendered first; e2e asserts it takes focus |
| Contrast 4.5:1 text, 3:1 UI | **Pass** | `npm run contrast` recomputes ratios from `tokens.css`; `tests/contrast.test.ts` fails the build on any regression, in both schemes |
| Never colour alone | **Pass** | Verified badge is a tick plus text; "Considered, not quoted" is text; alert tone is text plus a left border |
| Form labels; errors announced and linked | **Pass** | `Field` wires `label for`, `aria-describedby`, `aria-invalid`; validation error is field-linked, request errors use `role="alert"`. One bug fixed during testing: the same message was rendered twice |
| Results and status announced | **Pass (partial)** | Progress uses `role="status"`, the timer is `aria-hidden`, and the result is announced once. The live region itself is not asserted by a test — only the heading focus is |
| Reduced motion | **Pass** | Global `prefers-reduced-motion` block; the only transition is a 120ms background change |
| Colour scheme | **Pass** | All tokens switch under `prefers-color-scheme: dark`, and the dark set is in the contrast test |
| Text resizable to 200% | **Not verified** | No fixed heights on text containers and sizes are in `rem`, but I have not run a 200% zoom pass in a browser. Stated as unverified rather than passed |
| Touch targets ≥ 24×24 | **Pass (by CSS)** | Buttons and inputs are 44px minimum; inline links are text and exempt. Not measured by a test |
| Screen-reader walkthrough | **Not verified** | No manual NVDA/VoiceOver session; axe and e2e are automated only |

### SEO (public pages)

| Item | Status | How verified |
|---|---|---|
| Prerendered/static HTML | **Pass** | The build writes four HTML files; `grep` confirms **zero** `<script>` tags in `dist/index.html` |
| Unique title, description, OG, canonical | **Pass** | Injected per page by `scripts/prerender.mjs`; verified by reading `dist/index.html` |
| Semantic headings, descriptive links | **Pass** | One `h1` per page; link text says what it opens ("Open the guidance at this passage") |
| `sitemap.xml` and `robots.txt` | **Pass** | Generated at build; `robots.txt` allows all and points at the sitemap |
| App routes noindex | **Partial** | `dist/app.html` carries `<meta name="robots" content="noindex">`. The `X-Robots-Tag` header and the app-route rewrite are server configuration and are **not** in this repo yet — documented in `web/README.md` |
| Core Web Vitals | **Not verified** | Lighthouse CI is configured with budgets (LCP 2.5s, CLS 0.1, TBT 200ms, performance ≥ 0.95) but could not run here: Chrome launched and its DevTools endpoint was unreachable in this sandbox. The static pages ship no JavaScript, which is the main reason to expect a good LCP, but expectation is not measurement |

## Correction after a browser check

The first self-review said the styling had been reviewed. It had not: the app rendered
**with no CSS at all**, and axe passed anyway because axe does not check whether a
stylesheet applied.

Two causes, both now fixed and pinned by a test:

1. `style-src 'self'` in a `<meta>` CSP blocks the inline `<style>` tags Vite injects in
   development. Measured: 16 blocked style tags, `document.styleSheets.length === 0`, body
   font `Times`. The CSP is now injected **at build time only** (a Vite plugin with
   `apply: "build"`), so development is unstyled-no-more and production stays strict.
   `frame-ancestors` was also removed from the meta: browsers ignore it there and it belongs
   in the server header.
2. An enabled primary button showed white text on the disabled grey for 120ms, because
   `background-color` had a transition and the label colour did not. The transition is gone.

Both are now asserted in a real browser (`e2e/ask.spec.ts`): the stylesheet count, the body
font, the `h1` size, and the enabled button's background colour.

The accessibility table above should be read with that correction: "contrast" and "focus
ring" were checked as *values*, not as rendered pixels, until this check existed.

### Known gaps

- 200% zoom and a screen-reader pass are unverified, as above.
- The answer is not addressable by URL; nothing is stored server-side yet.
- The dark scheme is contrast-checked but not visually reviewed.
- `VITE_API_BASE` cross-origin mode requires the CSP `connect-src` to be widened, which the
  meta tag cannot do per-environment; the server header should carry it.
