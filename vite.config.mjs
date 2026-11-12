import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";

export default defineConfig({
  base: process.env.PAGES_BASE || "/",          // GitHub Pages serves the site from /<repo>/
  build: {
    outDir: "dist/client",
    target: ["es2019", "safari13", "chrome64", "firefox68", "edge79"],   // old phones and tablets too
    cssTarget: ["safari13", "chrome64", "firefox68"],
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
  },
  plugins: [react(), legacy({ targets: ["defaults", "iOS >= 12", "Safari >= 12", "Android >= 6", "Chrome >= 60", "Firefox >= 60"], modernPolyfills: true })],
});
