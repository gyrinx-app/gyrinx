import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { listCanvases, workspaceSlug } from "./canvas-directory";

const temporaryDirectories: string[] = [];

afterEach(() => {
    for (const directory of temporaryDirectories.splice(0)) {
        rmSync(directory, { recursive: true, force: true });
    }
});

describe("workspaceSlug", () => {
    it("matches the directory shape used by Cursor projects", () => {
        expect(workspaceSlug("/Users/tom/code/gyrinx/gyrinx")).toBe(
            "Users-tom-code-gyrinx-gyrinx",
        );
    });
});

describe("listCanvases", () => {
    it("returns only Canvas TSX files in stable name order", () => {
        const directory = mkdtempSync(join(tmpdir(), "canvas-viewer-"));
        temporaryDirectories.push(directory);
        writeFileSync(
            join(directory, "z.canvas.tsx"),
            "export default () => null;",
        );
        writeFileSync(
            join(directory, "a.canvas.tsx"),
            "export default () => null;",
        );
        writeFileSync(
            join(directory, "notes.tsx"),
            "export default () => null;",
        );

        const canvases = listCanvases(directory);

        expect(canvases.map((canvas) => canvas.name)).toEqual([
            "a.canvas.tsx",
            "z.canvas.tsx",
        ]);
        expect(canvases[0]?.moduleUrl).toBe(
            `/@fs${join(directory, "a.canvas.tsx")}`,
        );
    });
});
