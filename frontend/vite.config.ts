import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy the API through Vite so the dashboard is a single origin in dev and on
// demo day — one port to open, no CORS surprises on a venue network.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ingest": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
