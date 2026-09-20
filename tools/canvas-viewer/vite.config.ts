import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";
import { defineConfig } from "vite";

import {
    listCanvases,
    resolveCanvasDirectory,
} from "./src/canvas-directory.js";

const viewerRoot = fileURLToPath(new URL(".", import.meta.url));
const repositoryRoot = resolve(viewerRoot, "../..");
const canvasDirectory = resolveCanvasDirectory(repositoryRoot);

function canvasDirectoryPlugin(): Plugin {
    return {
        name: "gyrinx-canvas-directory",
        configureServer(server) {
            server.middlewares.use((request, response, next) => {
                const pathname = new URL(request.url ?? "/", "http://127.0.0.1")
                    .pathname;
                if (pathname !== "/api/canvases") {
                    next();
                    return;
                }

                response.statusCode = 200;
                response.setHeader(
                    "Content-Type",
                    "application/json; charset=utf-8",
                );
                response.setHeader("Cache-Control", "no-store");
                response.end(
                    JSON.stringify({
                        canvasDirectory,
                        canvases: listCanvases(canvasDirectory),
                    }),
                );
            });

            server.watcher.add(canvasDirectory);
            const reloadIfCanvas = (path: string) => {
                if (
                    path.startsWith(canvasDirectory) &&
                    path.endsWith(".canvas.tsx")
                ) {
                    server.ws.send({ type: "full-reload", path: "*" });
                }
            };
            server.watcher.on("add", reloadIfCanvas);
            server.watcher.on("change", reloadIfCanvas);
            server.watcher.on("unlink", reloadIfCanvas);

            server.config.logger.info(`Canvas directory: ${canvasDirectory}`);
        },
    };
}

export default defineConfig({
    root: viewerRoot,
    plugins: [canvasDirectoryPlugin()],
    resolve: {
        alias: {
            "cursor/canvas": resolve(viewerRoot, "src/canvas-runtime.tsx"),
        },
        dedupe: ["react", "react-dom"],
    },
    server: {
        host: "127.0.0.1",
        port: Number(process.env.CANVAS_PORT ?? 4173),
        strictPort: false,
        open: false,
        cors: false,
        headers: {
            "Content-Security-Policy":
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:*; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        },
        fs: {
            strict: true,
            allow: [viewerRoot, canvasDirectory],
        },
    },
    build: {
        outDir: resolve(viewerRoot, "dist"),
        emptyOutDir: true,
    },
});
