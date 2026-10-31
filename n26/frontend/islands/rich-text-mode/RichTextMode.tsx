import { useEffect, useRef, useState } from "react";
import cotton from "../../generated/cotton.json";

export type RichTextModeProps = {
    /** Sanitised HTML for a switch that has no textarea to read. */
    initial: string;
};

type Editor = { getContent: () => string };

declare global {
    interface Window {
        tinymce?: { get: (id: string) => Editor | null };
    }
}

const recipe = cotton.richTextMode;

function shellOf(node: HTMLElement | null) {
    return node?.closest<HTMLElement>("[data-rich-text]") ?? null;
}

/**
 * Live preview is the editor's own HTML, the same trust as the field being
 * typed into. It is not run through the sanitiser. A textarea TinyMCE has
 * not taken over yet supplies its value; `initial` is only for a switch
 * with no textarea at all.
 */
function read(root: HTMLElement | null, fallback: string) {
    const field = root?.querySelector<HTMLTextAreaElement>("textarea.tinymce");
    if (!field) return fallback;
    const editor = field.id ? window.tinymce?.get(field.id) : null;
    return editor ? editor.getContent() : field.value;
}

/** Edit and Preview for one rich text field. The editor stays in the page. */
export function RichTextMode({ initial }: RichTextModeProps) {
    const group = useRef<HTMLDivElement>(null);
    const empty = useRef<string | null>(null);
    const [mode, setMode] = useState<"edit" | "preview">("edit");

    useEffect(() => {
        const root = shellOf(group.current);
        return () => {
            const editor = root?.querySelector<HTMLElement>(
                "[data-rich-text-editor]",
            );
            const preview = root?.querySelector<HTMLElement>(
                "[data-rich-text-preview]",
            );
            if (editor) editor.style.display = "";
            if (preview) preview.hidden = true;
        };
    }, []);

    function show(next: "edit" | "preview") {
        const root = shellOf(group.current);
        const editor = root?.querySelector<HTMLElement>(
            "[data-rich-text-editor]",
        );
        const preview = root?.querySelector<HTMLElement>(
            "[data-rich-text-preview]",
        );
        if (next === "preview" && preview) {
            if (empty.current === null) empty.current = preview.innerHTML;
            const drawn = read(root, initial);
            // Live editor HTML, matching the previous preview. Empty keeps the
            // server's "Nothing to preview yet." paragraph.
            preview.innerHTML = drawn.trim() ? drawn : (empty.current ?? "");
            preview.hidden = false;
        } else if (preview) {
            preview.hidden = true;
        }
        // display, not removal: tearing the editor down drops its undo history.
        if (editor) editor.style.display = next === "edit" ? "" : "none";
        setMode(next);
    }

    const on = recipe.active;
    const off = recipe.idle;
    return (
        <div ref={group} data-rich-text-switch className={recipe.group}>
            <button
                type="button"
                className={mode === "edit" ? on : off}
                aria-pressed={mode === "edit"}
                onClick={() => show("edit")}
            >
                Edit
            </button>
            <button
                type="button"
                className={mode === "preview" ? on : off}
                aria-pressed={mode === "preview"}
                onClick={() => show("preview")}
            >
                Preview
            </button>
        </div>
    );
}
