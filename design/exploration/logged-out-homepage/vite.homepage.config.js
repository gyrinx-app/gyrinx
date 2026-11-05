import { defineConfig } from "vite";
import path from "node:path";

export default defineConfig({
    publicDir: false,
    define: { "process.env.NODE_ENV": JSON.stringify("production") },
    build: {
        rollupOptions: {
            input: path.resolve("src/homepage.jsx"),
            output: { entryFileNames: "homepage.js" },
        },
        outDir: "public",
        emptyOutDir: false,
    },
});
