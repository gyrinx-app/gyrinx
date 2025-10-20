import markdownIt from "markdown-it"
import configOptions, {init} from "@github/markdownlint-github"

const markdownItFactory = () => markdownIt({ html: true })

const options = {
  config: init({
    // Disable line length checking to accommodate existing long lines in documentation
    "line-length": false,
    // Allow dash style for unordered lists to match existing codebase
    "ul-style": { "style": "dash" },
    // Disable emphasis-as-heading rule for existing documentation
    "no-emphasis-as-heading": false,
    // Disable fenced-code-language rule for existing documentation
    "fenced-code-language": false,
    // Allow duplicate headings for existing documentation structure
    "no-duplicate-heading": false,
    // Allow heading level jumps for existing documentation
    "heading-increment": false,
    // Disable list indentation rule for existing documentation with mixed styles
    "ul-indent": false
  }),
  customRules: ["@github/markdownlint-github"],
  markdownItFactory,
  outputFormatters: [
    ["markdownlint-cli2-formatter-pretty", { "appendLink": true }]
  ],
  ignores: [
    "node_modules",
    "CHANGELOG.md",
    ".claude",
    "staticfiles",
    ".venv"
  ]
}

export default options
