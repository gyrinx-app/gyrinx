import React, { useEffect, useRef } from "react";
import { useEditor, useEditorState, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { AllSelection, TextSelection } from "@tiptap/pm/state";
import {
    Bold,
    Italic,
    Underline,
    List,
    ListOrdered,
    RemoveFormatting,
} from "lucide-react";
import cotton from "./cotton.json";
import { Button } from "./controls";

import { cleanRich, plainDoc } from "./rich-body";
export { cleanRich, plainDoc, RichBody } from "./rich-body";

export function BodyInput({ label, value, rich, onChange }) {
    const callback = useRef(onChange);
    callback.current = onChange;
    const editor = useEditor({
        extensions: [
            StarterKit.configure({
                heading: false,
                blockquote: false,
                code: false,
                codeBlock: false,
                horizontalRule: false,
                link: false,
                strike: false,
                trailingNode: false,
            }),
        ],
        content: cleanRich(rich) || plainDoc(value),
        editorProps: {
            // Native arrow-key collapse of Select All is unreliable for a nested
            // editable inside a shadow-root atom. Keep the document selection in sync.
            handleClick: (view, pos, event) => {
                if (event.shiftKey) return false;
                view.dispatch(
                    view.state.tr.setSelection(
                        TextSelection.near(view.state.doc.resolve(pos)),
                    ),
                );
                return true;
            },
            handleKeyDown: (view, event) => {
                if (
                    !event.shiftKey &&
                    view.state.selection instanceof AllSelection &&
                    [
                        "ArrowLeft",
                        "ArrowRight",
                        "ArrowUp",
                        "ArrowDown",
                        "Home",
                        "End",
                    ].includes(event.key)
                ) {
                    const end = ["ArrowRight", "ArrowDown", "End"].includes(
                        event.key,
                    );
                    view.dispatch(
                        view.state.tr.setSelection(
                            end
                                ? TextSelection.atEnd(view.state.doc)
                                : TextSelection.atStart(view.state.doc),
                        ),
                    );
                    return true;
                }
                return false;
            },
            attributes: {
                "aria-label": label,
                role: "textbox",
                "aria-multiline": "true",
                class: "callout-body-input",
            },
        },
        onUpdate: ({ editor }) =>
            callback.current(
                editor.getText({ blockSeparator: "\n\n" }),
                cleanRich(editor.getJSON()),
            ),
    });
    const state = useEditorState({
        editor,
        selector: ({ editor }) =>
            editor
                ? {
                      bold: editor.isActive("bold"),
                      italic: editor.isActive("italic"),
                      underline: editor.isActive("underline"),
                      bulletList: editor.isActive("bulletList"),
                      orderedList: editor.isActive("orderedList"),
                  }
                : null,
    });
    useEffect(() => {
        if (!editor) return;
        const doc = cleanRich(rich) || cleanRich(plainDoc(value));
        if (JSON.stringify(doc) !== JSON.stringify(cleanRich(editor.getJSON())))
            editor.commands.setContent(doc, { emitUpdate: false });
    }, [editor, value, rich]);
    if (!editor) return null;
    const buttons = [
        ["bold", "Bold", Bold, () => editor.chain().focus().toggleBold().run()],
        [
            "italic",
            "Italic",
            Italic,
            () => editor.chain().focus().toggleItalic().run(),
        ],
        [
            "underline",
            "Underline",
            Underline,
            () => editor.chain().focus().toggleUnderline().run(),
        ],
        [
            "bulletList",
            "Bulleted list",
            List,
            () => editor.chain().focus().toggleBulletList().run(),
        ],
        [
            "orderedList",
            "Numbered list",
            ListOrdered,
            () => editor.chain().focus().toggleOrderedList().run(),
        ],
        [
            "clear",
            "Clear formatting",
            RemoveFormatting,
            () => editor.chain().focus().unsetAllMarks().clearNodes().run(),
        ],
    ];
    return (
        <div className="callout-body-field">
            <span className={cotton.label}>{label}</span>
            <div className="callout-body-border">
                <div
                    role="toolbar"
                    aria-label={`${label} formatting`}
                    className="callout-body-toolbar"
                >
                    {buttons.map(([key, name, Icon, action]) => (
                        <Button
                            key={key}
                            preserveSelection
                            icon={Icon}
                            aria-label={name}
                            title={name}
                            aria-pressed={
                                key === "clear"
                                    ? undefined
                                    : Boolean(state?.[key])
                            }
                            onMouseDown={(event) => event.preventDefault()}
                            onClick={action}
                        ></Button>
                    ))}
                </div>
                <EditorContent editor={editor} />
            </div>
        </div>
    );
}
