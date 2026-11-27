import { Mark } from "@tiptap/core";
import cotton from "./cotton.json";

export const TextColour = Mark.create({
    name: "textColour",
    addAttributes() {
        return {
            colour: {
                default: null,
                parseHTML: (element) =>
                    /^#[a-f0-9]{6}$/i.test(
                        element.getAttribute("data-text-colour") || "",
                    )
                        ? element.getAttribute("data-text-colour")
                        : element.style.color || null,
                renderHTML: (attributes) =>
                    attributes.colour
                        ? { style: `color: ${attributes.colour}` }
                        : {},
            },
        };
    },
    parseHTML() {
        return [
            {
                tag: "span[style]",
                getAttrs: (element) => (element.style.color ? {} : false),
            },
        ];
    },
    renderHTML({ HTMLAttributes }) {
        return ["span", HTMLAttributes, 0];
    },
});

// A visual reference to a control, rendered as ordinary inline text.
export const InterfaceLabel = Mark.create({
    name: "interfaceLabel",
    inclusive: false,
    parseHTML() {
        return [{ tag: "span.interface-label" }];
    },
    renderHTML() {
        return [
            "span",
            { class: `${cotton.button.subtle} interface-label` },
            0,
        ];
    },
});

export function selectedRange(editor) {
    // Capture the visible selection before a modal takes focus, including selections
    // within the editor’s shadow root.
    const selection =
        editor.view.dom.getRootNode().getSelection?.() || window.getSelection();
    if (
        selection?.anchorNode &&
        selection.focusNode &&
        editor.view.dom.contains(selection.anchorNode) &&
        editor.view.dom.contains(selection.focusNode)
    ) {
        const anchor = editor.view.posAtDOM(
            selection.anchorNode,
            selection.anchorOffset,
        );
        const focus = editor.view.posAtDOM(
            selection.focusNode,
            selection.focusOffset,
        );
        return { from: Math.min(anchor, focus), to: Math.max(anchor, focus) };
    }
    return { from: editor.state.selection.from, to: editor.state.selection.to };
}
