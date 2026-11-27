// Indent block structure for inspection only. Inline text and preformatted text
// stay verbatim; this display representation is never submitted to Django.
const blocks = new Set([
    "ASIDE",
    "DIV",
    "SECTION",
    "ARTICLE",
    "P",
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
    "H6",
    "UL",
    "OL",
    "LI",
    "BLOCKQUOTE",
    "PRE",
    "TABLE",
    "THEAD",
    "TBODY",
    "TFOOT",
    "TR",
    "TH",
    "TD",
    "HR",
]);
export function readableHTML(html) {
    const template = document.createElement("template");
    template.innerHTML = html;
    function render(node, depth) {
        const indent = "  ".repeat(depth);
        if (node.nodeType !== Node.ELEMENT_NODE)
            return (
                indent +
                (node.nodeType === Node.TEXT_NODE
                    ? node.textContent
                    : node.outerHTML || "")
            );
        const children = [...node.childNodes];
        if (
            node.tagName === "PRE" ||
            !children.length ||
            children.some(
                (child) =>
                    child.nodeType !== Node.ELEMENT_NODE ||
                    !blocks.has(child.tagName),
            )
        )
            return indent + node.outerHTML;
        const empty = node.cloneNode(false).outerHTML;
        const split = empty.indexOf("></") + 1;
        if (split === 0) return indent + node.outerHTML;
        return (
            indent +
            empty.slice(0, split) +
            "\n" +
            children.map((child) => render(child, depth + 1)).join("\n") +
            "\n" +
            indent +
            empty.slice(split)
        );
    }
    return [...template.content.childNodes]
        .map((node) => render(node, 0))
        .join("\n");
}
