/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The /api proxy keeps the frontend same-origin in dev, so there is no base-URL or CORS juggling.
// VOUCH_API_PORT overrides the backend port for the case where 8000 is already taken (a stray
// uvicorn holding the socket is easier to route around than to hunt down mid-demo).
const API_PORT = process.env.VOUCH_API_PORT ?? "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${API_PORT}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
