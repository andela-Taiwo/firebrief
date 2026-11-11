import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import type { Plugin } from "vite";

/**
 * The strict CSP is injected at build time only.
 *
 * A `style-src 'self'` policy delivered in the HTML blocks the inline `<style>` tags that
 * Vite injects in development, which left the whole app unstyled. `frame-ancestors` cannot
 * be delivered by a meta tag at all, so that directive belongs in the server header.
 */
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "base-uri 'none'",
  "form-action 'self'",
].join("; ");

function cspOnBuild(): Plugin {
  return {
    name: "firebrief-csp-on-build",
    apply: "build",
    transformIndexHtml(html) {
      return html.replace(
        "</head>",
        `    <meta http-equiv="Content-Security-Policy" content="${CSP}" />\n  </head>`,
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), cspOnBuild()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // Same origin in development, so the HttpOnly session cookie just works.
    proxy: {
      "/v1": "http://127.0.0.1:8010",
      "/health": "http://127.0.0.1:8010",
      "/ready": "http://127.0.0.1:8010",
    },
  },
  build: {
    target: "es2022",
    sourcemap: false,
  },
});
