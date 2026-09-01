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
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
});
