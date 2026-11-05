import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";

import { resolveCheckoutModule } from "./n26/frontend/tooling/checkout_module.mjs";

const repositoryRoot = fileURLToPath(new URL(".", import.meta.url));
const frontendRoot = resolve(repositoryRoot, "n26/frontend");
const islandsRoot = resolve(frontendRoot, "islands");

function checkoutReact(checkout: string): Plugin {
    return {
        name: "checkout-react",
        enforce: "pre",
        resolveId(source) {
            return resolveCheckoutModule(checkout, source);
        },
    };
}

const entries = Object.fromEntries(
    readdirSync(islandsRoot, { withFileTypes: true })
        .filter((item) => item.isDirectory())
        .map((item) => [
            item.name,
            resolve(islandsRoot, item.name, "entry.tsx"),
        ]),
);

export default defineConfig(({ mode }) => {
    const development = mode === "development";

    return {
        root: frontendRoot,
        base: "./",
        plugins: [checkoutReact(repositoryRoot)],
        build: {
            outDir: resolve(repositoryRoot, "n26/core/static/n26/react"),
            emptyOutDir: true,
            manifest: "manifest.json",
            modulePreload: { polyfill: false },
            minify: !development,
            sourcemap: development,
            rolldownOptions: {
                preserveEntrySignatures: "strict",
                input: entries,
                output: {
                    manualChunks(id) {
                        if (
                            /node_modules\/(react|react-dom|scheduler)\//.test(
                                id,
                            )
                        ) {
                            return "react";
                        }
                    },
                },
            },
        },
    };
});
