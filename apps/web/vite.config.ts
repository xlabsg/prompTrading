import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
    server: {
        host: "::",
        port: 3000,
        proxy: {
            "/api": {
                target: process.env.VITE_API_BASE_URL || "http://api:8000",
                changeOrigin: true,
            },
            "/ws": {
                target: process.env.VITE_API_BASE_URL ? process.env.VITE_API_BASE_URL.replace("http", "ws") : "ws://api:8000",
                ws: true,
                changeOrigin: true,
            }
        },
        hmr: {
            overlay: false,
        },
    },
    // `vite preview` serves the production build; the E2E suite drives it so the
    // tests exercise the same artifact the app ships. It has no `server.proxy`,
    // so mirror the API proxy here (host-side API is localhost:8000).
    preview: {
        host: "::",
        port: 4173,
        proxy: {
            "/api": {
                target: process.env.VITE_API_BASE_URL || "http://localhost:8000",
                changeOrigin: true,
            },
            "/ws": {
                target: (process.env.VITE_API_BASE_URL || "http://localhost:8000").replace("http", "ws"),
                ws: true,
                changeOrigin: true,
            },
        },
    },
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
});
