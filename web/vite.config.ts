import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
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
