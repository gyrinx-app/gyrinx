import { init } from "@github/markdownlint-github";
import markdownIt from "markdown-it";

const markdownItFactory = () => markdownIt({ html: true });

const options = {
    config: init({
        // Disable line length checking to accommodate existing long lines in documentation
        "line-length": false,
        // Allow dash style for unordered lists to match existing codebase
        "ul-style": { style: "dash" },
        // Disable emphasis-as-heading rule for existing documentation
        "no-emphasis-as-heading": false,
        // Disable fenced-code-language rule for existing documentation
        "fenced-code-language": false,
        // Allow duplicate headings for existing documentation structure
        "no-duplicate-heading": false,
        // Allow heading level jumps for existing documentation
        "heading-increment": false,
        // Use 2-space indentation for lists (standard for markdownlint)
        "ul-indent": { indent: 2 },
    }),
    customRules: ["@github/markdownlint-github"],
    markdownItFactory,
    outputFormatters: [
        ["markdownlint-cli2-formatter-pretty", { appendLink: true }],
    ],
    ignores: [
        "node_modules",
        "CHANGELOG.md",
        ".claude",
        "staticfiles",
        ".venv",
        "analytics/streamlit/.venv",
    ],
};

export default options;
