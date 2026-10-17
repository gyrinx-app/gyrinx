import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Copy, Trash2, Settings2, Plus } from "lucide-react";
import cotton from "./cotton.json";
import { CalloutReader } from "./callout-reader";
import { RichBody, cleanRich, plainDoc } from "./rich-body";
import { normalizeCallout, serializeCallout, types } from "./callout-model";
import { Button } from "./controls";

export const BLOCK_SELECTOR = "aside[data-callout],div[data-html-block]";
export const isHTMLBlock = (block) => block?.matches("div[data-html-block]");
export function codeFromBlock(block) {
    const code = JSON.parse(block.getAttribute("data-html-block"));
    if (typeof code !== "string" || code.length > 100000)
        throw Error("Invalid HTML block");
    return code;
}
export const configFromBlock = (block) =>
    normalizeCallout(JSON.parse(block.getAttribute("data-callout")));
export function bodyHTML(text, rich) {
    return renderToStaticMarkup(<RichBody document={rich || plainDoc(text)} />);
}

// Convert TinyMCE's basic HTML into the existing restricted body schema.
export function bodyDocument(html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    function inline(node, marks = []) {
        if (node.nodeType === 3)
            return node.textContent
                ? [{ type: "text", text: node.textContent, marks }]
                : [];
        if (node.nodeType !== 1) return [];
        if (["SCRIPT", "STYLE", "IFRAME", "OBJECT"].includes(node.tagName))
            return [];
        if (node.tagName === "BR") return [{ type: "hardBreak" }];
        const mark = {
            STRONG: "bold",
            B: "bold",
            EM: "italic",
            I: "italic",
            U: "underline",
        }[node.tagName];
        const next = mark ? [...marks, { type: mark }] : marks;
        return [...node.childNodes].flatMap((child) => inline(child, next));
    }
    function blocks(container) {
        const result = [];
        let run = [];
        const flush = () => {
            if (run.length) {
                result.push({ type: "paragraph", content: run });
                run = [];
            }
        };
        for (const node of container.childNodes) {
            if (node.nodeType === 3 && !node.textContent.trim() && !run.length)
                continue;
            if (node.nodeType === 1 && ["UL", "OL"].includes(node.tagName)) {
                flush();
                result.push({
                    type: node.tagName === "UL" ? "bulletList" : "orderedList",
                    content: [...node.children]
                        .filter((child) => child.tagName === "LI")
                        .map((child) => {
                            const content = blocks(child);
                            if (content[0]?.type !== "paragraph")
                                content.unshift({
                                    type: "paragraph",
                                    content: [],
                                });
                            return { type: "listItem", content };
                        }),
                });
            } else if (
                node.nodeType === 1 &&
                ["P", "H1", "H2", "H3", "H4", "H5", "H6"].includes(node.tagName)
            ) {
                flush();
                result.push({
                    type: "paragraph",
                    content: [...node.childNodes].flatMap((child) =>
                        inline(child),
                    ),
                });
            } else if (
                node.nodeType === 1 &&
                ["DIV", "BLOCKQUOTE"].includes(node.tagName)
            ) {
                flush();
                result.push(...blocks(node));
            } else run.push(...inline(node));
        }
        flush();
        return result.length ? result : [{ type: "paragraph", content: [] }];
    }
    return cleanRich({ type: "doc", content: blocks(doc.body) });
}
export function bodyText(document) {
    const walk = (node) =>
        node.type === "text"
            ? node.text
            : node.type === "hardBreak"
              ? "\n"
              : (node.content || [])
                    .map(walk)
                    .join(
                        [
                            "doc",
                            "listItem",
                            "bulletList",
                            "orderedList",
                        ].includes(node.type)
                            ? "\n\n"
                            : "",
                    );
    return walk(document);
}
function fallbackContent(config) {
    const bodies =
        config.type === "carousel" ? (
            config.slides.map((slide) => (
                <section key={slide.eyebrow}>
                    <p>
                        <strong>{slide.eyebrow}</strong>
                    </p>
                    <RichBody
                        document={slide.bodyRich || plainDoc(slide.body)}
                    />
                </section>
            ))
        ) : (
            <>
                <RichBody document={config.bodyRich || plainDoc(config.body)} />
                {config.type === "expanding-info" && (
                    <RichBody
                        document={config.detailRich || plainDoc(config.detail)}
                    />
                )}
            </>
        );
    return renderToStaticMarkup(
        <>
            <p>
                <strong>{config.label}</strong>
            </p>
            {bodies}
        </>,
    );
}
export function calloutHTML(config) {
    const block = document.createElement("aside");
    block.className = "gyrinx-block callout-editor";
    block.setAttribute("data-callout", serializeCallout(config));
    block.innerHTML = fallbackContent(config);
    return block.outerHTML;
}
export function htmlBlockHTML(code) {
    const block = document.createElement("div");
    block.className = "gyrinx-block callout-editor";
    block.setAttribute("data-html-block", JSON.stringify(code));
    const pre = document.createElement("pre"),
        content = document.createElement("code");
    content.textContent = code;
    pre.append(content);
    block.append(pre);
    return block.outerHTML;
}
function BlockControls({ label }) {
    return (
        <>
            <div className="callout-author-controls">
                <span>{label}</span>
                <Button
                    icon={Settings2}
                    data-block-action="edit"
                    aria-label="Edit block"
                    title="Edit block"
                />
                <Button
                    icon={Copy}
                    data-block-action="copy"
                    aria-label="Copy block"
                    title="Copy block"
                />
                <Button
                    icon={Trash2}
                    data-block-action="delete"
                    aria-label="Delete block"
                    title="Delete block"
                />
            </div>
        </>
    );
}
const renderedBlocks = new WeakMap();
export function enhanceBlock(block) {
    const html = isHTMLBlock(block);
    const value = html ? codeFromBlock(block) : configFromBlock(block);
    const encoded = JSON.stringify(value);
    if (renderedBlocks.get(block) === encoded) return;
    block.classList.add("gyrinx-block", "callout-editor");
    block.setAttribute("contenteditable", "false");
    const label = html
        ? "HTML block"
        : types.find((row) => row[0] === value.type)[1];
    const controls = renderToStaticMarkup(<BlockControls label={label} />);
    const reader = html
        ? renderToStaticMarkup(
              <pre className="html-block-code">
                  <code>{value}</code>
              </pre>,
          )
        : renderToStaticMarkup(<CalloutReader config={value} />);
    const plus = renderToStaticMarkup(
        <div className="callout-add-paragraph">
            <Button
                icon={Plus}
                data-block-action="paragraph"
                aria-label="Add paragraph below block"
                title="Add paragraph below block"
            />
        </div>,
    );
    // These views are generated from validated settings and escaped React text.
    block.innerHTML = `<div data-mce-bogus="all">${controls}</div><div data-mce-bogus="all" class="tiny-block-reader">${reader}</div><div data-mce-bogus="all">${plus}</div>`;
    renderedBlocks.set(block, encoded);
}
export function enhanceBlocks(editor) {
    editor
        .getBody()
        .querySelectorAll(BLOCK_SELECTOR)
        .forEach((block) => {
            if (block.closest('[data-mce-bogus="all"]')) return;
            try {
                enhanceBlock(block);
            } catch {
                /* Unknown saved blocks keep their original fallback content. */
            }
        });
}
export function publishedTinyHTML(html) {
    if (!/data-(callout|html-block)=/.test(html)) return html;
    const doc = new DOMParser().parseFromString(html, "text/html");
    doc.body.querySelectorAll(BLOCK_SELECTOR).forEach((block) => {
        try {
            block.outerHTML = isHTMLBlock(block)
                ? htmlBlockHTML(codeFromBlock(block))
                : calloutHTML(configFromBlock(block));
        } catch {
            block
                .querySelectorAll('[data-mce-bogus="all"]')
                .forEach((node) => node.remove());
        }
    });
    return doc.body.innerHTML;
}
