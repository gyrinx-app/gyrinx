import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
    root,
    base: "./",
    build: {
        outDir: "../core/static/n26/react",
        emptyOutDir: true,
        manifest: "manifest.json",
        modulePreload: { polyfill: false },
        rolldownOptions: {
            preserveEntrySignatures: "strict",
            input: readdirSync(`${root}entries`)
                .filter((name) => name.endsWith(".tsx"))
                .map((name) => `${root}entries/${name}`),
            output: {
                manualChunks(id) {
                    if (
                        /node_modules\/(react|react-dom|scheduler)\//.test(id)
                    ) {
                        return "react";
                    }
                },
            },
        },
    },
});
