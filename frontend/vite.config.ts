import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Node globals, declared here so the app tsconfig does not need @types/node.
declare const process: { env: Record<string, string | undefined> };

const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
    },
  },
});
