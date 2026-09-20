import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const repositoryRoot = fileURLToPath(new URL(".", import.meta.url));
const frontendRoot = resolve(repositoryRoot, "n26/frontend");
const islandsRoot = resolve(frontendRoot, "islands");

const entries = Object.fromEntries(
    readdirSync(islandsRoot, { withFileTypes: true })
        .filter((item) => item.isDirectory())
        .map((item) => [
            item.name,
            resolve(islandsRoot, item.name, "entry.tsx"),
        ]),
);

export default defineConfig(({ mode }) => ({
    root: frontendRoot,
    base: "./",
    build: {
        outDir: resolve(repositoryRoot, "n26/core/static/n26/react"),
        emptyOutDir: true,
        manifest: "manifest.json",
        modulePreload: { polyfill: false },
        sourcemap: mode === "development",
        rolldownOptions: {
            preserveEntrySignatures: "strict",
            input: entries,
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
}));
