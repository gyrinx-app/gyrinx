import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { useEditor, useEditorState, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import { TableKit } from "@tiptap/extension-table";
import {
    Undo2,
    Redo2,
    List,
    ListOrdered,
    Quote,
    Link as LinkIcon,
    Image as ImageIcon,
    RemoveFormatting,
    Palette,
    SquareDashedTopSolid,
    SquareCode,
} from "lucide-react";
import cotton from "./cotton.json";
import { HTMLBlock } from "./html-block";
import { readableHTML } from "./html-output";
import {
    Button as SharedButton,
    Icon as ToolbarIcon,
    useModal,
} from "./controls";
import { useUpload, uploadFormats } from "./uploads";
const Button = (props) => <SharedButton preserveSelection {...props} />;
import {
    CalloutNode,
    CalloutMenu,
    RichPreview,
    freshCallout,
} from "./callouts";
import { TextColour, selectedRange } from "./text-formatting";

function ColourDialog({ initial, onApply, onClose }) {
    const ref = useModal();
    const [colours, setColours] = useState([]);
    const [colour, setColour] = useState(() => {
        if (/^#[a-f0-9]{6}$/i.test(initial || "")) return initial;
        const rgb = /^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/.exec(initial || "");
        return rgb
            ? "#" +
                  rgb
                      .slice(1)
                      .map((value) =>
                          Number(value).toString(16).padStart(2, "0"),
                      )
                      .join("")
            : "#b91c1c";
    });
    useEffect(() => {
        const theme = getComputedStyle(ref.current);
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 1;
        const context = canvas.getContext("2d");
        // Freeze the gallery's actual theme shades into authored text, as for a
        // custom colour, so preview and saved text use the same sRGB value.
        const resolved = cotton.colours.map(({ name, token }) => {
            context.clearRect(0, 0, 1, 1);
            context.fillStyle = theme.getPropertyValue(token).trim();
            context.fillRect(0, 0, 1, 1);
            const value =
                "#" +
                [...context.getImageData(0, 0, 1, 1).data]
                    .slice(0, 3)
                    .map((channel) => channel.toString(16).padStart(2, "0"))
                    .join("");
            return [name, value];
        });
        setColours(resolved);
        if (!initial) setColour(resolved.find(([name]) => name === "Red")[1]);
    }, []);
    return (
        <dialog
            ref={ref}
            className={`${cotton.dialog.root} editor-dialog`}
            aria-labelledby="colour-title"
            onCancel={(event) => {
                event.preventDefault();
                onClose();
            }}
        >
            <form
                className={cotton.dialog.form}
                onSubmit={(event) => {
                    event.preventDefault();
                    onApply(colour);
                }}
            >
                <h2 id="colour-title" className={cotton.dialog.title}>
                    Text colour
                </h2>
                <div className="editor-colours">
                    {colours.map(([name, value]) => (
                        <Button
                            key={name}
                            title={name}
                            aria-label={name}
                            aria-pressed={colour === value}
                            onClick={() => setColour(value)}
                        >
                            <span
                                className="colour-swatch"
                                style={{ backgroundColor: value }}
                            />
                            {name}
                        </Button>
                    ))}
                </div>
                <label className={cotton.label} htmlFor="custom-colour">
                    Custom colour
                </label>
                <input
                    id="custom-colour"
                    type="color"
                    value={colour}
                    onChange={(event) => setColour(event.target.value)}
                />
                <p className={cotton.description}>
                    Applies to selected text or the text you type next.
                </p>
                <div className="dialog-actions">
                    <Button onClick={onClose}>Cancel</Button>
                    <Button onClick={() => onApply(null)}>
                        Default colour
                    </Button>
                    <button type="submit" className={cotton.button.primary}>
                        Apply colour
                    </button>
                </div>
            </form>
        </dialog>
    );
}

function URLDialog({ kind, initialURL, onApply, onClose }) {
    const ref = useModal();
    const [url, setURL] = useState(initialURL);
    const [alt, setAlt] = useState("");
    const { upload, pending, error, setError } = useUpload(
        kind === "image" ? "image" : "file",
    );
    const [source, setSource] = useState(
        kind === "image" ? "upload" : "address",
    );
    const [file, setFile] = useState(null);
    async function apply(event) {
        event.preventDefault();
        if (pending) return;
        setError("");
        if (source === "upload") {
            await upload(file, (result) =>
                onApply(result.location, alt, result.filename),
            );
            return;
        }
        try {
            const parsed = new URL(url);
            if (!["https:", "http:"].includes(parsed.protocol))
                throw new Error();
            onApply(parsed.href, alt);
        } catch {
            setError("Enter a full http or https address.");
        }
    }
    return (
        <dialog
            ref={ref}
            className={`${cotton.dialog.root} editor-dialog`}
            aria-labelledby="url-title"
            onCancel={(event) => {
                event.preventDefault();
                onClose();
            }}
        >
            <form onSubmit={apply} className={cotton.dialog.form}>
                <h2 id="url-title" className={cotton.dialog.title}>
                    {kind === "image" ? "Insert image" : "Edit link"}
                </h2>
                <div
                    role="group"
                    aria-label="Content source"
                    className="editor-upload-modes"
                >
                    <Button
                        variant={source === "address" ? "primary" : "ghost"}
                        aria-pressed={source === "address"}
                        disabled={pending}
                        onClick={() => {
                            setSource("address");
                            setFile(null);
                            setError("");
                        }}
                    >
                        Address
                    </Button>
                    <Button
                        variant={source === "upload" ? "primary" : "ghost"}
                        aria-pressed={source === "upload"}
                        disabled={pending}
                        onClick={() => {
                            if (source !== "upload") setFile(null);
                            setSource("upload");
                            setError("");
                        }}
                    >
                        {kind === "image" ? "Upload image" : "Upload file"}
                    </Button>
                </div>
                {source === "address" ? (
                    <div>
                        <label htmlFor="editor-url" className={cotton.label}>
                            {kind === "image"
                                ? "Image address"
                                : "Link address"}
                        </label>
                        <div className={cotton.input.root}>
                            <input
                                id="editor-url"
                                autoFocus
                                required
                                type="url"
                                className={cotton.input.control}
                                value={url}
                                onChange={(event) => setURL(event.target.value)}
                            />
                        </div>
                    </div>
                ) : (
                    <div>
                        <label htmlFor="editor-file" className={cotton.label}>
                            {kind === "image" ? "Image file" : "File"}
                        </label>
                        <input
                            id="editor-file"
                            type="file"
                            autoFocus
                            disabled={pending}
                            className={cotton.fileInput}
                            aria-describedby="upload-help"
                            accept={
                                uploadFormats[
                                    kind === "image" ? "image" : "file"
                                ].accept
                            }
                            onChange={(event) => {
                                setFile(event.target.files[0] || null);
                                setError("");
                            }}
                        />
                        <p
                            id="upload-help"
                            className={`${cotton.description} text-sm`}
                        >
                            {
                                uploadFormats[
                                    kind === "image" ? "image" : "file"
                                ].help
                            }
                        </p>
                    </div>
                )}
                {kind === "image" && (
                    <div>
                        <label htmlFor="editor-alt" className={cotton.label}>
                            Image description
                        </label>
                        <div className={cotton.input.root}>
                            <input
                                id="editor-alt"
                                className={cotton.input.control}
                                disabled={pending}
                                value={alt}
                                onChange={(event) => setAlt(event.target.value)}
                            />
                        </div>
                    </div>
                )}
                {error && (
                    <p role="alert" className={`${cotton.error} editor-error`}>
                        {error}
                    </p>
                )}
                {pending && (
                    <p
                        role="status"
                        className={`${cotton.description} text-sm`}
                    >
                        Uploading…
                    </p>
                )}
                <div className="dialog-actions">
                    <Button onClick={onClose}>Cancel</Button>
                    {kind === "link" && initialURL && (
                        <Button disabled={pending} onClick={() => onApply("")}>
                            Remove link
                        </Button>
                    )}
                    <button
                        type="submit"
                        disabled={pending}
                        className={cotton.button.primary}
                    >
                        {pending
                            ? "Uploading…"
                            : source === "upload"
                              ? "Upload and insert"
                              : "Apply"}
                    </button>
                </div>
            </form>
        </dialog>
    );
}

function Editor({ textarea }) {
    const changed = useRef(false);
    const toolbarSelection = useRef(null);
    const [mode, setMode] = useState("edit");
    const [dark, setDark] = useState(false);
    const [dialog, setDialog] = useState(null);
    const [preview, setPreview] = useState({ html: "", callouts: [] });
    const [calloutMenu, setCalloutMenu] = useState(null);
    const [error, setError] = useState("");
    const [status, setStatus] = useState("Ready to edit");
    const [colourDialog, setColourDialog] = useState(null);
    useEffect(() => {
        textarea.nextElementSibling.classList.toggle("dark", dark);
    }, [dark, textarea]);
    const editor = useEditor({
        extensions: [
            StarterKit.configure({ link: { openOnClick: false } }),
            Image,
            TableKit,
            TextColour,
            CalloutNode,
            HTMLBlock,
        ],
        content: textarea.value,
        editorProps: {
            attributes: {
                class: "rich-text flatpage-prose",
                role: "textbox",
                "aria-multiline": "true",
                "aria-label": textarea.dataset.editorLabel || "Document body",
            },
        },
        onUpdate: ({ editor }) => {
            changed.current = true;
            textarea.value = editor.getHTML();
            setStatus("Unsaved changes");
            textarea.dispatchEvent(new Event("change", { bubbles: true }));
        },
    });
    const state = useEditorState({
        editor,
        selector: ({ editor }) =>
            editor
                ? {
                      bold: editor.isActive("bold"),
                      italic: editor.isActive("italic"),
                      underline: editor.isActive("underline"),
                      bullet: editor.isActive("bulletList"),
                      ordered: editor.isActive("orderedList"),
                      quote: editor.isActive("blockquote"),
                      block: editor.isActive("codeBlock")
                          ? "pre"
                          : String(
                                [1, 2, 3, 4, 5, 6].find((level) =>
                                    editor.isActive("heading", { level }),
                                ) || 0,
                            ),
                      undo: editor.can().undo(),
                      redo: editor.can().redo(),
                      words: editor
                          .getText()
                          .trim()
                          .split(/\s+/)
                          .filter(Boolean).length,
                      html: editor.getHTML(),
                      colour: editor.getAttributes("textColour").colour,
                      selection: {
                          from: editor.state.selection.from,
                          to: editor.state.selection.to,
                      },
                  }
                : null,
    });
    useEffect(() => {
        if (!editor) return;
        // Keep untouched fields unchanged, including an empty introduction inline.
        const sync = () => {
            if (changed.current) textarea.value = editor.getHTML();
        };
        textarea.form?.addEventListener("submit", sync);
        textarea.hidden = true;
        return () => {
            textarea.form?.removeEventListener("submit", sync);
            textarea.hidden = false;
        };
    }, [editor, textarea]);
    useEffect(() => {
        if (mode !== "preview" || !state) return;
        const controller = new AbortController();
        setPreview({ html: "", callouts: [] });
        setError("");
        fetch("/preview/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": document.querySelector(
                    "[name=csrfmiddlewaretoken]",
                ).value,
            },
            body: JSON.stringify({ html: state.html }),
            signal: controller.signal,
        })
            .then((response) => {
                if (!response.ok) throw new Error();
                return response.json();
            })
            .then((data) => setPreview(data))
            .catch((err) => {
                if (err.name !== "AbortError")
                    setError(
                        "Preview could not load. Your draft is still in the editor.",
                    );
            });
        return () => controller.abort();
    }, [mode, state?.html]);
    if (!editor || !state) return null;
    const actions = [
        [
            "Bold",
            "B",
            state.bold,
            () => editor.chain().focus().toggleBold().run(),
        ],
        [
            "Italic",
            "I",
            state.italic,
            () => editor.chain().focus().toggleItalic().run(),
        ],
        [
            "Underline",
            "U",
            state.underline,
            () => editor.chain().focus().toggleUnderline().run(),
        ],
        [
            "Bulleted list",
            List,
            state.bullet,
            () => editor.chain().focus().toggleBulletList().run(),
        ],
        [
            "Numbered list",
            ListOrdered,
            state.ordered,
            () => editor.chain().focus().toggleOrderedList().run(),
        ],
        [
            "Quote",
            Quote,
            state.quote,
            () => editor.chain().focus().toggleBlockquote().run(),
        ],
    ];
    return (
        <section
            className={`gyrinx-editor ${dark ? "dark" : ""}`}
            style={{
                "--editor-height": textarea.dataset.editorHeight || "300px",
            }}
            aria-label="Gyrinx text editor"
        >
            <div className="editor-toolbar">
                <div className="editor-bar" aria-label="Editor views">
                    <span className="editor-label">
                        Gyrinx editor · Design playground
                    </span>
                    {["edit", "preview", "html"].map((view) => (
                        <Button
                            key={view}
                            aria-pressed={mode === view}
                            onClick={() => setMode(view)}
                        >
                            {view === "html"
                                ? "HTML"
                                : view[0].toUpperCase() + view.slice(1)}
                        </Button>
                    ))}
                    <Button aria-pressed={dark} onClick={() => setDark(!dark)}>
                        Dark theme
                    </Button>
                </div>
                {mode === "edit" && (
                    <div
                        className="editor-bar"
                        role="group"
                        aria-label="Text formatting"
                    >
                        <Button
                            aria-label="Undo"
                            title="Undo"
                            disabled={!state.undo}
                            onClick={() => editor.chain().focus().undo().run()}
                        >
                            <ToolbarIcon icon={Undo2} />
                        </Button>
                        <Button
                            aria-label="Redo"
                            title="Redo"
                            disabled={!state.redo}
                            onClick={() => editor.chain().focus().redo().run()}
                        >
                            <ToolbarIcon icon={Redo2} />
                        </Button>
                        <select
                            className={cotton.select.className}
                            style={cotton.select.style}
                            aria-label="Text style"
                            value={state.block}
                            onChange={(event) => {
                                const format = event.target.value;
                                if (format === "pre")
                                    editor.chain().focus().setCodeBlock().run();
                                else if (format === "0")
                                    editor.chain().focus().setParagraph().run();
                                else
                                    editor
                                        .chain()
                                        .focus()
                                        .setHeading({ level: Number(format) })
                                        .run();
                            }}
                        >
                            <option value="0">Paragraph</option>
                            {[1, 2, 3, 4, 5, 6].map((level) => (
                                <option key={level} value={level}>
                                    Heading {level}
                                </option>
                            ))}
                            <option value="pre">Preformatted</option>
                        </select>
                        {actions.map(([label, content, active, action]) => (
                            <Button
                                key={label}
                                aria-label={label}
                                title={label}
                                aria-pressed={active}
                                onClick={action}
                            >
                                {typeof content === "string" ? (
                                    content
                                ) : (
                                    <ToolbarIcon icon={content} />
                                )}
                            </Button>
                        ))}
                        <Button
                            aria-label="Text colour"
                            title="Text colour"
                            onMouseDown={(event) => {
                                event.preventDefault();
                                toolbarSelection.current =
                                    selectedRange(editor);
                            }}
                            onClick={() => {
                                setColourDialog({
                                    kind: "colour",
                                    selection:
                                        toolbarSelection.current ||
                                        selectedRange(editor),
                                });
                                toolbarSelection.current = null;
                            }}
                        >
                            <ToolbarIcon icon={Palette} />
                        </Button>
                        <Button
                            aria-label="Insert callout"
                            title="Insert callout"
                            onMouseDown={(event) => {
                                event.preventDefault();
                                toolbarSelection.current =
                                    selectedRange(editor);
                            }}
                            onClick={() => {
                                setCalloutMenu(
                                    toolbarSelection.current ||
                                        selectedRange(editor),
                                );
                                toolbarSelection.current = null;
                            }}
                        >
                            <ToolbarIcon icon={SquareDashedTopSolid} />
                        </Button>
                        <Button
                            aria-label="Insert HTML block"
                            title="Insert HTML block"
                            onMouseDown={(event) => {
                                event.preventDefault();
                                toolbarSelection.current =
                                    selectedRange(editor);
                            }}
                            onClick={() => {
                                const selection =
                                    toolbarSelection.current ||
                                    selectedRange(editor);
                                toolbarSelection.current = null;
                                editor
                                    .chain()
                                    .focus()
                                    .setTextSelection(selection.from)
                                    .insertContent([
                                        {
                                            type: "htmlBlock",
                                            attrs: { code: "" },
                                        },
                                        { type: "paragraph" },
                                    ])
                                    .run();
                            }}
                        >
                            <ToolbarIcon icon={SquareCode} />
                        </Button>
                        <Button
                            aria-label="Link"
                            title="Link"
                            onClick={() => setDialog("link")}
                        >
                            <ToolbarIcon icon={LinkIcon} />
                        </Button>
                        <Button
                            aria-label="Image"
                            title="Image"
                            onClick={() => setDialog("image")}
                        >
                            <ToolbarIcon icon={ImageIcon} />
                        </Button>
                        <Button
                            aria-label="Clear formatting"
                            title="Clear formatting"
                            onClick={() => {
                                const chain = editor.chain().focus();
                                Object.keys(editor.schema.marks).forEach(
                                    (name) => chain.unsetMark(name),
                                );
                                chain.clearNodes().run();
                            }}
                        >
                            <ToolbarIcon icon={RemoveFormatting} />
                        </Button>
                    </div>
                )}
            </div>
            <div hidden={mode !== "edit"} className="editor-document">
                <EditorContent editor={editor} />
            </div>
            {mode === "preview" && (
                <div className="editor-document">
                    <RichPreview
                        html={preview.html}
                        callouts={preview.callouts}
                    />
                </div>
            )}
            {mode === "html" && (
                <pre className="editor-source" aria-label="HTML output">
                    {readableHTML(state.html)}
                </pre>
            )}
            {error && (
                <p role="alert" className={`${cotton.error} editor-error`}>
                    {error}
                </p>
            )}
            <div className="editor-foot">
                <span>{state.words} words</span>
                <span role="status">{status}</span>
                <span>⌘/Ctrl+B bold · ⌘/Ctrl+I italic</span>
            </div>
            {colourDialog?.kind === "colour" && (
                <ColourDialog
                    initial={state.colour}
                    onClose={() => {
                        setColourDialog(null);
                        editor.commands.focus();
                    }}
                    onApply={(colour) => {
                        const chain = editor
                            .chain()
                            .focus()
                            .setTextSelection(colourDialog.selection);
                        if (colour)
                            chain.setMark("textColour", { colour }).run();
                        else chain.unsetMark("textColour").run();
                        setColourDialog(null);
                    }}
                />
            )}
            {calloutMenu && (
                <CalloutMenu
                    onClose={() => {
                        setCalloutMenu(null);
                        editor.commands.focus();
                    }}
                    onChoose={(type) => {
                        editor
                            .chain()
                            .focus()
                            .setTextSelection(calloutMenu.from)
                            .insertContent([
                                {
                                    type: "callout",
                                    attrs: { config: freshCallout(type) },
                                },
                                { type: "paragraph" },
                            ])
                            .run();
                        setCalloutMenu(null);
                    }}
                />
            )}
            {dialog && (
                <URLDialog
                    kind={dialog}
                    initialURL={
                        dialog === "link"
                            ? editor.getAttributes("link").href || ""
                            : ""
                    }
                    onClose={() => {
                        setDialog(null);
                        editor.commands.focus();
                    }}
                    onApply={(url, alt, filename) => {
                        if (dialog === "image")
                            editor
                                .chain()
                                .focus()
                                .setImage({ src: url, alt })
                                .run();
                        else if (
                            url &&
                            editor.state.selection.empty &&
                            !editor.isActive("link")
                        )
                            editor
                                .chain()
                                .focus()
                                .insertContent({
                                    type: "text",
                                    text: filename || url,
                                    marks: [
                                        { type: "link", attrs: { href: url } },
                                    ],
                                })
                                .run();
                        else if (url)
                            editor
                                .chain()
                                .focus()
                                .extendMarkRange("link")
                                .setLink({ href: url })
                                .run();
                        else
                            editor
                                .chain()
                                .focus()
                                .extendMarkRange("link")
                                .unsetLink()
                                .run();
                        setDialog(null);
                    }}
                />
            )}
        </section>
    );
}

function mountEditors() {
    if (!document.querySelector("[data-gyrinx-fonts]")) {
        const fonts = document.createElement("link");
        fonts.rel = "stylesheet";
        fonts.href = "https://use.typekit.net/rso6ezl.css";
        fonts.dataset.gyrinxFonts = "";
        document.head.append(fonts);
    }
    document.querySelectorAll("[data-gyrinx-editor]").forEach((textarea) => {
        const host = document.createElement("div");
        host.style.width = "100%";
        host.dataset.editorHost = "";
        textarea.after(host);
        // Django's hidden-overflow form row would become the sticky toolbar's scroll container.
        const row = host.closest(".form-row");
        if (row) row.style.overflow = "visible";
        const shadow = host.attachShadow({ mode: "open" });
        const style = document.createElement("link");
        style.rel = "stylesheet";
        style.href = "/static/theme.css";
        shadow.append(style);
        const container = document.createElement("div");
        shadow.append(container);
        createRoot(container).render(<Editor textarea={textarea} />);
    });
}
if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", mountEditors, { once: true });
else mountEditors();
