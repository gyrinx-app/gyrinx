import { readFileSync, writeFileSync } from "node:fs";
// A normal document inside TinyMCE's iframe needs :root instead of :host.
const theme = readFileSync("public/theme.css", "utf8")
    .replace(/:host\(([^)]+)\)/g, ":root$1")
    .replaceAll(":host", ":root");
writeFileSync("public/tiny-content.css", theme);
