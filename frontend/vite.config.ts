import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the desk at http://localhost:5173 (or the next free port).
// The page calls the FastAPI backend directly at VITE_API_URL (default http://localhost:8000); the
// backend's CORS settings allow this origin.
export default defineConfig({
  plugins: [react()],
  server: { port: Number(process.env.PORT ?? 5173) },
});
