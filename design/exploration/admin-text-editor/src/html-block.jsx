import React from "react";
import { Plugin } from "@tiptap/pm/state";
import { Node } from "@tiptap/core";
import { NodeViewWrapper, ReactNodeViewRenderer } from "@tiptap/react";
import { SquareCode, Trash2, Copy } from "lucide-react";
import cotton from "./cotton.json";
import { Button, Field, Icon } from "./controls";
import { ParagraphDivider, useBlockCopy } from "./block-controls";

const MAX_HTML_LENGTH = 100000;
const CLIPBOARD_PREFIX = "Gyrinx HTML block\n";
function parseCode(value) {
    const code = JSON.parse(value);
    if (typeof code !== "string" || code.length > MAX_HTML_LENGTH)
        throw Error("Invalid HTML block");
    return code;
}
function clipboardHTML(code) {
    const block = document.createElement("div");
    block.setAttribute("data-html-block", JSON.stringify(code));
    const pre = document.createElement("pre"),
        content = document.createElement("code");
    content.textContent = code;
    pre.append(content);
    block.append(pre);
    return block.outerHTML;
}

function HTMLBlockEditor({
    node,
    updateAttributes,
    deleteNode,
    editor,
    getPos,
}) {
    const { copy, copied } = useBlockCopy({
        editor,
        getPos,
        label: "HTML block",
        html: () => clipboardHTML(node.attrs.code),
        text: () => CLIPBOARD_PREFIX + JSON.stringify(node.attrs.code),
    });
    return (
        <NodeViewWrapper
            className="callout-editor html-block-editor"
            contentEditable={false}
            data-html-block-editor=""
        >
            <div className="callout-author-controls">
                <Icon icon={SquareCode} size={16} />
                <span>HTML block</span>
                <Button
                    icon={Copy}
                    aria-label="Copy HTML block"
                    title="Copy HTML block"
                    onClick={copy}
                />
                <Button
                    icon={Trash2}
                    aria-label="Delete HTML block"
                    title="Delete HTML block"
                    onClick={deleteNode}
                />
            </div>
            <div className="html-block-field">
                <Field label="HTML code">
                    <textarea
                        className={`${cotton.input.control} html-block-code`}
                        value={node.attrs.code}
                        maxLength={MAX_HTML_LENGTH}
                        spellCheck={false}
                        autoCapitalize="off"
                        autoCorrect="off"
                        placeholder="<p>Your HTML content</p>"
                        onChange={(event) =>
                            updateAttributes({ code: event.target.value })
                        }
                    />
                </Field>
            </div>
            <p className={cotton.description}>
                Preview renders supported HTML. Scripts and embedded frames are
                removed.
            </p>
            <span role="status" className="callout-copy-status">
                {copied}
            </span>
            <ParagraphDivider
                editor={editor}
                getPos={getPos}
                node={node}
                label="Add paragraph below HTML block"
            />
        </NodeViewWrapper>
    );
}

export const HTMLBlock = Node.create({
    name: "htmlBlock",
    group: "block",
    atom: true,
    draggable: true,
    addAttributes() {
        return { code: { default: "", rendered: false } };
    },
    parseHTML() {
        return [
            {
                tag: "div[data-html-block]",
                getAttrs: (element) => {
                    try {
                        return {
                            code: parseCode(
                                element.getAttribute("data-html-block"),
                            ),
                        };
                    } catch {
                        return false;
                    }
                },
            },
        ];
    },
    renderHTML({ node }) {
        return [
            "div",
            { "data-html-block": JSON.stringify(node.attrs.code) },
            ["pre", ["code", node.attrs.code]],
        ];
    },
    addNodeView() {
        return ReactNodeViewRenderer(HTMLBlockEditor, {
            stopEvent: ({ event }) =>
                Boolean(
                    event.target.closest?.(
                        ".html-block-field,.callout-author-controls,.callout-add-paragraph",
                    ),
                ),
        });
    },
    addProseMirrorPlugins() {
        return [
            new Plugin({
                props: {
                    handlePaste: (view, event) => {
                        const text = event.clipboardData?.getData("text/plain");
                        if (!text?.startsWith(CLIPBOARD_PREFIX)) return false;
                        try {
                            const code = parseCode(
                                text.slice(CLIPBOARD_PREFIX.length),
                            );
                            this.editor.commands.insertContent({
                                type: "htmlBlock",
                                attrs: { code },
                            });
                            return true;
                        } catch {
                            return false;
                        }
                    },
                },
            }),
        ];
    },
});
