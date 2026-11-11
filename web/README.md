# Firebrief web

Vite + React + TypeScript. Plain CSS modules, no UI library.

```bash
npm install --cache ./.npm-cache   # the sandbox's npm cache is not writable
npm run dev                        # http://127.0.0.1:5173
npm test                           # Vitest + Testing Library + jest-axe
npm run build                      # typecheck, client build, static pages, sitemap
npm run contrast                   # recompute WCAG ratios from the tokens
npx playwright install chromium    # once, for e2e
npm run e2e
npm run lighthouse                 # needs Chrome on CHROME_PATH
```

## Two artefacts from one build

- `dist/index.html`, `dist/about/index.html`, `dist/help/index.html`,
  `dist/accessibility/index.html` — static HTML, **no JavaScript**, indexed.
- `dist/app.html` — the single-page app shell with the bundle, **noindex**.

The server must rewrite the app routes (`/sign-in`, `/auth/verify`, `/ask`, `/signed-out`)
to `dist/app.html`, and send `X-Robots-Tag: noindex` on those responses. Public routes are
served from their own static files. `dist/sitemap.xml` and `dist/robots.txt` are generated.

App routes are deliberately **not** disallowed in `robots.txt`: a disallowed URL is never
fetched, so the crawler never sees the `noindex`, and the page can still be indexed by URL.
The meta tag plus the header is the enforceable pair.

## API

`credentials: "include"` on every request; the session is an `HttpOnly` cookie. Set
`VITE_API_BASE` when the API is on another origin (the CSP `connect-src` must match).

## Security

The CSP is a `<meta http-equiv>` tag: `default-src 'self'`, no third-party scripts, styles or
fonts. The system font stack means no font request at all. Serve the real header from the
server as well; a meta tag cannot express `frame-ancestors` reliably in every browser.
