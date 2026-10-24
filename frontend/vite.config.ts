import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  // One .env at the repo root for backend and frontend. Vite only exposes VITE_* keys to the browser.
  envDir: path.resolve(import.meta.dirname, ".."),
  server: { port: 5173 },
  build: {
    rolldownOptions: {
      output: {
        // Split by library, not by route: every chunk loads at startup, so the offline demo never has to fetch a
        // screen it has not opened yet once the Wi-Fi is gone.
        codeSplitting: {
          groups: [
            { name: "charts", test: /node_modules[\\/](recharts|d3-[^\\/]+|victory-vendor|decimal\.js-light|internmap)[\\/]/ },
            { name: "motion", test: /node_modules[\\/](framer-motion|motion-dom|motion-utils)[\\/]/ },
            { name: "radix", test: /node_modules[\\/](radix-ui|@radix-ui|cmdk|sonner)[\\/]/ },
            { name: "react", test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler|@tanstack)[\\/]/ },
            { name: "vendor", test: /node_modules[\\/]/ },
          ],
        },
      },
    },
  },
});
