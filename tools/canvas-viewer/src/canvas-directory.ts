import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, resolve } from "node:path";

export type CanvasEntry = {
    name: string;
    path: string;
    moduleUrl: string;
    mtimeMs: number;
};

export function workspaceSlug(workspacePath: string): string {
    return resolve(workspacePath).replace(/^\/+/, "").replaceAll("/", "-");
}

export function repositoryWorkspaceRoot(repositoryRoot: string): string {
    const commonDirectory = execFileSync(
        "git",
        ["rev-parse", "--git-common-dir"],
        { cwd: repositoryRoot, encoding: "utf8" },
    ).trim();
    const absoluteCommonDirectory = isAbsolute(commonDirectory)
        ? commonDirectory
        : resolve(repositoryRoot, commonDirectory);

    return basename(absoluteCommonDirectory) === ".git"
        ? dirname(absoluteCommonDirectory)
        : repositoryRoot;
}

export function defaultCanvasDirectory(
    repositoryRoot: string,
    homeDirectory = homedir(),
): string {
    const workspaceRoot = repositoryWorkspaceRoot(repositoryRoot);
    return join(
        homeDirectory,
        ".cursor",
        "projects",
        workspaceSlug(workspaceRoot),
        "canvases",
    );
}

export function resolveCanvasDirectory(
    repositoryRoot: string,
    configuredDirectory = process.env.CANVAS_DIR,
): string {
    return configuredDirectory
        ? resolve(configuredDirectory)
        : defaultCanvasDirectory(repositoryRoot);
}

export function listCanvases(directory: string): CanvasEntry[] {
    if (!existsSync(directory)) return [];
    return readdirSync(directory, { withFileTypes: true })
        .filter((entry) => entry.isFile() && entry.name.endsWith(".canvas.tsx"))
        .map((entry) => {
            const path = join(directory, entry.name);
            const { mtimeMs } = statSync(path);
            return {
                name: entry.name,
                path,
                moduleUrl: `/@fs${path}`,
                mtimeMs,
            };
        })
        .sort((left, right) => left.name.localeCompare(right.name));
}
