import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the React dev server (5173) proxies API and WebSocket
// traffic to the FastAPI backend (8000), so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  build: {
    outDir: "dist",
  },
});
