import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The /api proxy keeps the frontend same-origin in dev, so there is no base-URL or CORS juggling.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
