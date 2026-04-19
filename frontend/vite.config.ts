/// <reference types="vitest" />
// Vite + Vitest config for the Scenarios App frontend.
//
// We use `defineConfig` from `vite` and rely on the `vitest`
// reference directive above to extend `UserConfig` with the `test`
// property. Importing from `vitest/config` would pull in vitest's
// own pinned `vite` types, conflicting with our top-level `vite`
// installation under `tsc --strict`.
//
// The dev-server proxy rewrites `/api/*` -> `http://localhost:8000/*`
// so the production app code makes plain relative fetches (no
// hardcoded host) and CORS stays simple in dev.

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    // jsdom needs an explicit base URL for relative fetch() calls
    // to resolve; without this MSW would never see the requests.
    environmentOptions: {
      jsdom: { url: "http://localhost:5173" },
    },
  },
});
