import { defineConfig } from "vite";
import path from "node:path";
export default defineConfig({
    publicDir: false,
    define: { "process.env.NODE_ENV": JSON.stringify("production") },
    build: {
        lib: {
            entry: path.resolve("src/editor.jsx"),
            formats: ["es"],
            fileName: () => "editor.js",
        },
        outDir: "public",
        emptyOutDir: false,
    },
});
