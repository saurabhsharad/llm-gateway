import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev server runs on http://localhost:5173 (already allowed by backend CORS).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
