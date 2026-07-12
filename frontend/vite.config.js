import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Vite config for the Mini AI Assistant UI.
//
// Dev proxy: forward every `/api/*` request to the FastAPI backend on
// localhost:8000. The frontend itself reads `import.meta.env.VITE_API_BASE`
// (default "/api") and the proxy rewrites /api/foo -> http://localhost:8000/foo
// so we don't have to deal with CORS during local dev.
//
// In production, set `VITE_API_BASE` to the deployed backend origin at build
// time and serve `dist/` from any static host. See README for details.
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        host: true, // 0.0.0.0 so Docker / other host browsers can reach us
        proxy: {
            "/api": {
                target: "http://localhost:8000",
                changeOrigin: true,
                rewrite: function (path) { return path.replace(/^\/api/, ""); },
            },
        },
    },
    build: {
        outDir: "dist",
        sourcemap: true,
    },
});
