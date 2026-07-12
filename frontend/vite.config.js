import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Vite config for the Mini AI Assistant UI.
//
// Local dev: the frontend calls same-origin paths (`/chat`, `/healthz`,
// …). Vite proxies those to the FastAPI backend on localhost:8000 so we
// don't have to deal with CORS.
//
// Production: the Dockerfile builds the SPA into `web/dist` and FastAPI
// serves it. Both UI and API share the same origin, so no rewrite is
// needed.
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        host: true, // 0.0.0.0 so Docker / other host browsers can reach us
        proxy: {
            "^/(chat|sessions|session|ingest|healthz|metrics|admin|kb|tools)(/.*)?$": {
                target: "http://localhost:8000",
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: "../web/dist",
        emptyOutDir: true,
        sourcemap: true,
    },
});
