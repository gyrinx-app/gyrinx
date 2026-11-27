import { readFileSync, writeFileSync } from "node:fs";

const path = "dist/theme.css";
const css = readFileSync(path, "utf8");
// Property registrations inside the shadow stylesheet do not initialise these
// defaults in Chrome. Reuse the compiler's values within this demo's boundary.
const defaults = [
    ...css.matchAll(/@property\s+(--tw-[\w-]+)\s*\{([^}]*)\}/g),
].flatMap(([, name, body]) => {
    const value = body.match(/initial-value\s*:\s*([^;}]+)/)?.[1]?.trim();
    return value === undefined ? [] : [`${name}:${value}`];
});
if (!defaults.some((value) => value.startsWith("--tw-border-style:")))
    throw new Error(
        "Tailwind property defaults changed. Check the history shadow theme.",
    );
const scope =
    ":where(.history-page,.history-page *,.history-page::before,.history-page::after,.history-page *::before,.history-page *::after,.history-page *::backdrop)";
writeFileSync(path, `${css}\n@layer base{${scope}{${defaults.join(";")}}}\n`);
console.log(
    `Prepared ${defaults.length} Tailwind defaults for the history shadow boundary.`,
);
