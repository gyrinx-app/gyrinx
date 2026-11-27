import React from "react";

const tags = {
    doc: React.Fragment,
    paragraph: "p",
    bulletList: "ul",
    orderedList: "ol",
    listItem: "li",
    hardBreak: "br",
};
// Render only a small document schema as React text/elements; never execute saved HTML.
export function cleanRich(raw) {
    let count = 0,
        characters = 0;
    function visit(node, depth = 0) {
        if (!node || typeof node !== "object" || depth > 12 || ++count > 2000)
            return null;
        if (node.type === "text") {
            if (typeof node.text !== "string") return null;
            const text = node.text.slice(0, Math.max(0, 12000 - characters));
            characters += text.length;
            if (!text) return null;
            return {
                type: "text",
                text,
                marks: (Array.isArray(node.marks) ? node.marks : [])
                    .filter((mark) =>
                        ["bold", "italic", "underline"].includes(mark?.type),
                    )
                    .map((mark) => ({ type: mark.type })),
            };
        }
        if (!Object.hasOwn(tags, node.type)) return null;
        return {
            type: node.type,
            ...(node.type === "hardBreak"
                ? {}
                : {
                      content: (Array.isArray(node.content) ? node.content : [])
                          .map((child) => visit(child, depth + 1))
                          .filter(Boolean),
                  }),
        };
    }
    return raw?.type === "doc" ? visit(raw) : null;
}
export function plainDoc(text) {
    return {
        type: "doc",
        content: text.split(/\n\n+/).map((paragraph) => ({
            type: "paragraph",
            content: paragraph
                .split("\n")
                .flatMap((line, index) => [
                    ...(index ? [{ type: "hardBreak" }] : []),
                    ...(line ? [{ type: "text", text: line }] : []),
                ]),
        })),
    };
}
export function RichBody({ document, budget = Infinity }) {
    const clean = cleanRich(document);
    let remaining = budget;
    function render(node, key) {
        if (node.type === "text") {
            const text = node.text.slice(0, remaining);
            remaining = Math.max(0, remaining - text.length);
            const marked = node.marks.reduce(
                (value, mark) =>
                    React.createElement(
                        { bold: "strong", italic: "em", underline: "u" }[
                            mark.type
                        ],
                        null,
                        value,
                    ),
                text,
            );
            return <React.Fragment key={key}>{marked}</React.Fragment>;
        }
        return React.createElement(
            tags[node.type],
            { key },
            node.type === "hardBreak" ? undefined : node.content.map(render),
        );
    }
    return clean && <div className="callout-rich-body">{render(clean, 0)}</div>;
}
