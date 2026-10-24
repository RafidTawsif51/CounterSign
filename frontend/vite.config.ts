import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  // One .env at the repo root for backend and frontend. Vite only exposes VITE_* keys to the browser.
  envDir: path.resolve(__dirname, ".."),
  server: { port: 5173 },
});
