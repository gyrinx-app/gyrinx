import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import mermaid from "mermaid";

function markdownFiles(directory) {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) return markdownFiles(path);
        return path.endsWith(".md") ? [path] : [];
    });
}

let diagramCount = 0;
let failureCount = 0;

for (const file of markdownFiles("docs/security")) {
    const lines = readFileSync(file, "utf8").split(/\r?\n/);
    let fileDiagrams = 0;

    for (let index = 0; index < lines.length; index++) {
        const opening = lines[index].match(/^(`{3,}|~{3,})mermaid\s*$/);
        if (!opening) continue;

        const fence = opening[1];
        const startLine = index + 1;
        const body = [];
        while (++index < lines.length && lines[index].trim() !== fence) {
            body.push(lines[index]);
        }

        if (index === lines.length) {
            console.error(`${file}:${startLine}: Mermaid fence is not closed`);
            failureCount++;
            break;
        }

        fileDiagrams++;
        diagramCount++;
        try {
            await mermaid.parse(body.join("\n"));
        } catch (error) {
            console.error(`${file}:${startLine}: ${error.message}`);
            failureCount++;
        }
    }

    if (
        file.startsWith("docs/security/data-flows/") &&
        !file.endsWith("/index.md") &&
        fileDiagrams !== 1
    ) {
        console.error(
            `${file}: expected one Mermaid diagram, found ${fileDiagrams}`,
        );
        failureCount++;
    }
}

if (failureCount) {
    console.error(`${failureCount} security diagram check(s) failed`);
    process.exitCode = 1;
} else {
    console.log(`Parsed ${diagramCount} security diagrams`);
}
