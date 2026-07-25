// Stylelint config.
//
// PRETTIER OWNS FORMATTING. `npm run fmt` runs prettier over .scss (and
// scripts/fmt.sh calls it), so stylelint must not also have opinions about
// whitespace, indentation, quotes or leading zeros — the two tools disagreed,
// and because stylelint lost that argument on every save, `npm run css-lint`
// sat at ~1,350 errors and stopped being read at all. It is not wired into CI
// or pre-commit, so nothing caught the rot.
//
// Everything purely stylistic is therefore switched off here, and stylelint is
// left to do the part prettier cannot: correctness and convention.
//
// The @stylistic list is derived from the installed plugin rather than typed
// out, so it stays complete when the plugin adds rules.

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

        // SCSS-flavoured formatting rules, same reasoning: prettier decides where
        // the line breaks go. `operator-no-newline-after` in particular fires on
        // any calc() prettier chose to wrap.
        "scss/operator-no-newline-after": null,
        "scss/operator-no-newline-before": null,
        "scss/dollar-variable-colon-space-after": null,
        "scss/dollar-variable-colon-space-before": null,

        // Declaration ordering is cosmetic and prettier does not do it, so keeping
        // it would just reintroduce a few hundred unfixable warnings.
        "order/properties-order": null,

        // Keyword casing: keep the rule, but stop it lowercasing things that are
        // conventionally cased. `--fix` turned `Roboto` into `roboto`,
        // `currentColor` into `currentcolor` and the SVG keyword
        // `geometricPrecision` into `geometricprecision`. CSS keywords are
        // case-insensitive so none of that changed behaviour — it just cost
        // legibility for a diff nobody asked for.
        // Not `camelCaseSvgKeywords`, which would also demand `in sRGB` inside
        // color-mix() — the CSS spec writes that colour space lowercase, and the
        // camelCase form only exists for SVG's color-interpolation-filters.
        // An explicit ignore list is narrower and says why each one is here.
        "value-keyword-case": [
            "lower",
            {
                ignoreKeywords: [
                    "currentColor",
                    "geometricPrecision", // SVG shape-rendering value
                    "A4", // @page size; reads as a paper size, not a keyword
                ],
                ignoreProperties: ["/font-family/"],
            },
        ],

        // BEM is deliberate in _classic_card.scss (.cc-tab__save-label,
        // .cc-injuries--wide). The default pattern only allows kebab-case, which
        // flagged 26 correct selectors. Widen it rather than rename a print
        // stylesheet's whole vocabulary to satisfy a lint default.
        "selector-class-pattern": [
            "^[a-z][a-z0-9]*(-[a-z0-9]+)*(__[a-z0-9]+(-[a-z0-9]+)*)?(--[a-z0-9]+(-[a-z0-9]+)*)?$",
            {
                message: (selector) =>
                    `Expected class selector "${selector}" to be kebab-case, optionally with BEM __element and --modifier`,
            },
        ],
    },
};
