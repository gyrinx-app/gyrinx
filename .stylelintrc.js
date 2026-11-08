// Prettier handles formatting. Disable stylistic rules in Stylelint so the
// tools agree. Read the installed plugin's rules to include newly added rules.

const stylisticPlugin = require("@stylistic/stylelint-plugin");

const stylisticRulesOff = Object.fromEntries(
    (stylisticPlugin.default || stylisticPlugin).map((rule) => [
        rule.ruleName,
        null,
    ]),
);

module.exports = {
    extends: ["stylelint-config-twbs-bootstrap"],
    reportInvalidScopeDisables: true,
    reportNeedlessDisables: true,
    overrides: [
        {
            files: "**/*.scss",
            rules: {
                "scss/selector-no-union-class-name": true,
            },
        },
    ],
    rules: {
        ...stylisticRulesOff,

        // Prettier controls SCSS spacing and line breaks, including wrapped calc().
        "scss/operator-no-newline-after": null,
        "scss/operator-no-newline-before": null,
        "scss/dollar-variable-colon-space-after": null,
        "scss/dollar-variable-colon-space-before": null,

        // Property ordering is cosmetic and Prettier does not enforce it.
        "order/properties-order": null,

        // Preserve font names and conventional CSS/SVG casing. An explicit list
        // avoids enabling camelCaseSvgKeywords, which also changes sRGB casing.
        "value-keyword-case": [
            "lower",
            {
                ignoreKeywords: [
                    "currentColor",
                    "geometricPrecision", // SVG shape-rendering value
                    "A4", // @page paper size
                ],
                ignoreProperties: ["/font-family/"],
            },
        ],

        // Card styles use BEM elements and modifiers alongside kebab-case names.
        "selector-class-pattern": [
            "^[a-z][a-z0-9]*(-[a-z0-9]+)*(__[a-z0-9]+(-[a-z0-9]+)*)?(--[a-z0-9]+(-[a-z0-9]+)*)?$",
            {
                message: (selector) =>
                    `Expected class selector "${selector}" to be kebab-case, optionally with BEM __element and --modifier`,
            },
        ],
    },
};
