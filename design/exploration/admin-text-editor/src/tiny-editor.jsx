import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
    SquareDashedTopSolid,
    SquareCode,
    UsbCPort,
    Copy,
    Trash2,
    Settings2,
    Plus,
} from "lucide-react";
import cotton from "./cotton.json";
import {
    freshCallout,
    normalizeCallout,
    serializeCallout,
    types,
    icons,
} from "./callout-model";
import { writeBlockClipboard } from "./clipboard";
import { uploadFile, uploadFormats } from "./uploads";
import { openCalloutDialog } from "./tiny-callout-dialog";
import {
    BLOCK_SELECTOR,
    isHTMLBlock,
    codeFromBlock,
    configFromBlock,
    calloutHTML,
    htmlBlockHTML,
    enhanceBlock,
    enhanceBlocks,
    publishedTinyHTML,
} from "./tiny-callout-content";

const iconHTML = (Component) =>
    renderToStaticMarkup(
        <Component
            width={24}
            height={24}
            strokeWidth={1.7}
            style={{ fill: "none" }}
        />,
    );
window.initializeGyrinxTiny = async function (options) {
    const target = document.getElementById("tiny-document");
    target.value = options.html;
    const version = encodeURIComponent(options.version);
    const contentOptions = {
        base_url: "/static/tinymce",
        suffix: ".min",
        license_key: "gpl",
        promotion: false,
        branding: false,
        content_css: [`/static/tiny-content.css?v=${version}`],
        init_instance_callback: (instance) => {
            const doc = instance.getDoc();
            const fonts = doc.createElement("link");
            fonts.rel = "stylesheet";
            fonts.href = "https://use.typekit.net/rso6ezl.css";
            doc.head.append(fonts);
        },
        body_class: "gyrinx-editor rich-text flatpage-prose",
        content_style:
            "body {margin:0;padding:1rem 1.25rem;max-width:none;border:0;font-size:16px;line-height:1.6;} img {max-width:100%;height:auto;} .gyrinx-block {display:flow-root;} .tiny-block-reader a {pointer-events:none;} .gyrinx-block .mce-object {border:0;}",
        convert_urls: false,
        entity_encoding: "raw",
        formats: { underline: { inline: "u", exact: true } },
    };
    let main,
        bookmark,
        selectedBlock = null,
        closed = false,
        frame = 0;
    function currentBlock() {
        const block = main.selection.getNode().closest?.(BLOCK_SELECTOR);
        return block && !block.closest('[data-mce-bogus="all"]')
            ? block
            : selectedBlock?.isConnected
              ? selectedBlock
              : null;
    }
    function selectBlock(block) {
        selectedBlock = block;
        main.selection.select(block);
        main.nodeChanged();
    }
    function transaction(action) {
        main.undoManager.transact(action);
        main.setDirty(true);
        main.nodeChanged();
        main.dispatch("change");
    }
    function replaceBlock(block, html) {
        if (block && !main.getBody().contains(block)) {
            main.notificationManager.open({
                type: "warning",
                text: "This block was removed. Insert a new callout to continue.",
            });
            return;
        }
        transaction(() => {
            if (block) {
                const holder = main.getDoc().createElement("div");
                holder.innerHTML = html;
                const fresh = holder.firstElementChild;
                block.replaceWith(fresh);
                enhanceBlock(fresh);
                selectBlock(fresh);
            } else {
                main.selection.moveToBookmark(bookmark);
                main.insertContent(html + "<p></p>");
                enhanceBlocks(main);
            }
        });
    }
    function editCallout(block, type) {
        bookmark = main.selection.getBookmark(2, true);
        const config = block ? configFromBlock(block) : freshCallout(type);
        const save = (value) => replaceBlock(block, calloutHTML(value));
        save.existing = Boolean(block);
        openCalloutDialog(main, config, save, contentOptions);
    }
    function editHTML(block) {
        bookmark = main.selection.getBookmark(2, true);
        main.windowManager.open({
            title: block ? "Edit HTML block" : "Insert HTML block",
            size: "large",
            body: {
                type: "panel",
                items: [{ type: "textarea", name: "code", label: "HTML code" }],
            },
            initialData: { code: block ? codeFromBlock(block) : "" },
            buttons: [
                { type: "cancel", text: "Cancel" },
                { type: "submit", text: "Save HTML block", primary: true },
            ],
            onSubmit: (dialog) => {
                const code = dialog.getData().code;
                if (code.length > 100000) {
                    main.windowManager.alert(
                        "Use no more than 100,000 characters in an HTML block.",
                    );
                    return;
                }
                replaceBlock(block, htmlBlockHTML(code));
                dialog.close();
            },
        });
    }
    async function copyBlock(block) {
        try {
            const html = isHTMLBlock(block);
            const value = html ? codeFromBlock(block) : configFromBlock(block);
            await writeBlockClipboard(
                html ? htmlBlockHTML(value) : calloutHTML(value),
                html
                    ? "Gyrinx HTML block\n" + JSON.stringify(value)
                    : "Gyrinx callout\n" + serializeCallout(value),
            );
            main.notificationManager.open({
                type: "success",
                text: "Block copied. Paste it into the editor.",
                timeout: 2500,
            });
        } catch {
            selectBlock(block);
            main.focus();
            main.notificationManager.open({
                type: "info",
                text: "Block selected. Use ⌘/Ctrl+C to copy it.",
            });
        }
    }
    function paragraphAfter(block) {
        transaction(() => {
            const paragraph = main.dom.create(
                "p",
                {},
                '<br data-mce-bogus="1">',
            );
            block.after(paragraph);
            selectedBlock = null;
            main.selection.setCursorLocation(paragraph, 0);
            main.focus();
        });
    }
    function action(name, block = currentBlock()) {
        if (!block) return;
        if (name === "edit")
            isHTMLBlock(block) ? editHTML(block) : editCallout(block);
        if (name === "copy") copyBlock(block);
        if (name === "paragraph") paragraphAfter(block);
        if (name === "delete")
            transaction(() => {
                const next = block.nextElementSibling;
                block.remove();
                selectedBlock = null;
                if (next) main.selection.setCursorLocation(next, 0);
                main.focus();
            });
    }
    function scheduleEnhancement() {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
            if (!closed && main?.initialized) enhanceBlocks(main);
        });
    }
    function filePicker(callback, value, meta) {
        const input = document.createElement("input");
        input.type = "file";
        const kind = meta.filetype === "image" ? "image" : "file";
        input.accept = uploadFormats[kind].accept;
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) return;
            try {
                const result = await uploadFile(
                    file,
                    kind,
                    undefined,
                    options.csrfToken,
                );
                if (!closed)
                    callback(result.location, {
                        text: result.filename,
                        title: result.filename,
                    });
            } catch (error) {
                if (!closed)
                    main.notificationManager.open({
                        type: "error",
                        text: error.message,
                    });
            }
        };
        input.click();
    }
    const instances = await window.tinymce.init({
        ...contentOptions,
        target,
        height: "100%",
        min_height: 340,
        resize: false,
        plugins: "lists link image table code wordcount",
        menubar: false,
        toolbar_mode: "wrap",
        object_resizing: false,
        color_map: options.colours.flatMap(([name, value]) => [value, name]),
        color_cols: 6,
        color_rows: 3,
        image_dimensions: false,
        toolbar:
            "undo redo | blocks | bold italic underline | bullist numlist blockquote | interfacelabel forecolor | gyrinxcallouts htmlblock | link image table | removeformat code",
        file_picker_types: "file image",
        file_picker_callback: filePicker,
        automatic_uploads: true,
        images_upload_handler: async (blob) => {
            const result = await uploadFile(
                new File([blob.blob()], blob.filename(), {
                    type: blob.blob().type,
                }),
                "image",
                undefined,
                options.csrfToken,
            );
            return result.location;
        },
        noneditable_class: "gyrinx-block",
        formats: {
            ...contentOptions.formats,
            interfaceLabel: {
                inline: "span",
                classes: `${cotton.button.subtle} interface-label`,
            },
        },
        setup: (editor) => {
            main = editor;
            main.gyrinxDark = options.dark;
            const customIcons = {
                callout: SquareDashedTopSolid,
                htmlblock: SquareCode,
                interface: UsbCPort,
                copyblock: Copy,
                deleteblock: Trash2,
                editblock: Settings2,
                paragraphafter: Plus,
            };
            Object.entries(customIcons).forEach(([name, Component]) =>
                editor.ui.registry.addIcon(name, iconHTML(Component)),
            );
            const context = (name) => ({
                icon: {
                    edit: "editblock",
                    copy: "copyblock",
                    delete: "deleteblock",
                    paragraph: "paragraphafter",
                }[name],
                tooltip: {
                    edit: "Edit block",
                    copy: "Copy block",
                    delete: "Delete block",
                    paragraph: "Add paragraph below block",
                }[name],
                onAction: () => action(name),
            });
            for (const name of ["edit", "copy", "delete", "paragraph"])
                editor.ui.registry.addButton(`gyrinx${name}`, context(name));
            editor.ui.registry.addContextToolbar("gyrinxblock", {
                predicate: (node) => node.matches?.(BLOCK_SELECTOR),
                items: "gyrinxedit gyrinxcopy gyrinxdelete gyrinxparagraph",
                position: "node",
                scope: "node",
            });
            editor.ui.registry.addMenuButton("gyrinxcallouts", {
                icon: "callout",
                tooltip: "Insert callout",
                fetch: (callback) =>
                    callback(
                        types.map(([type, name, icon]) => ({
                            type: "menuitem",
                            text: name,
                            onAction: () => editCallout(null, type),
                        })),
                    ),
            });
            editor.ui.registry.addButton("htmlblock", {
                icon: "htmlblock",
                tooltip: "Insert HTML block",
                onAction: () => editHTML(null),
            });
            editor.ui.registry.addToggleButton("interfacelabel", {
                icon: "interface",
                tooltip: "Interface label",
                onAction: () => editor.formatter.toggle("interfaceLabel"),
                onSetup: (api) => {
                    const update = () =>
                        api.setActive(editor.formatter.match("interfaceLabel"));
                    editor.on("NodeChange", update);
                    return () => editor.off("NodeChange", update);
                },
            });
            editor.on("init", () => {
                editor.getBody().setAttribute("aria-label", options.label);
                enhanceBlocks(editor);
                editor
                    .getDoc()
                    .documentElement.classList.toggle(
                        "dark",
                        Boolean(options.dark),
                    );
                editor
                    .getBody()
                    .classList.toggle("dark", Boolean(options.dark));
                editor.undoManager.clear();
                editor.setDirty(false);
            });
            editor.on("PostProcess", (event) => {
                if (event.get && event.format !== "raw")
                    event.content = publishedTinyHTML(event.content);
            });
            editor.on(
                "SetContent Undo Redo PastePostProcess",
                scheduleEnhancement,
            );
            editor.on("click", (event) => {
                const block = event.target.closest?.(BLOCK_SELECTOR);
                if (block) selectedBlock = block;
                const control = event.target.closest?.("[data-block-action]");
                if (control && block) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    action(control.dataset.blockAction, block);
                }
            });
            editor.on("mousedown", (event) => {
                if (event.target.closest?.("[data-block-action]"))
                    event.preventDefault();
            });
            editor.on("dblclick", (event) => {
                const block = event.target.closest?.(BLOCK_SELECTOR);
                if (block) {
                    event.preventDefault();
                    action("edit", block);
                }
            });
            editor.on("paste", (event) => {
                const text = event.clipboardData?.getData("text/plain");
                if (!text) return;
                try {
                    let html;
                    if (text.startsWith("Gyrinx callout\n"))
                        html = calloutHTML(
                            normalizeCallout(
                                JSON.parse(
                                    text.slice("Gyrinx callout\n".length),
                                ),
                            ),
                        );
                    else if (text.startsWith("Gyrinx HTML block\n")) {
                        const code = JSON.parse(
                            text.slice("Gyrinx HTML block\n".length),
                        );
                        if (typeof code === "string" && code.length <= 100000)
                            html = htmlBlockHTML(code);
                    }
                    if (html) {
                        event.preventDefault();
                        editor.insertContent(html);
                        scheduleEnhancement();
                    }
                } catch {
                    /* Keep invalid clipboard text under TinyMCE's ordinary paste rules. */
                }
            });
            editor.on("PastePreProcess", (event) => {
                const text = event.content;
                let config, code;
                // TinyMCE HTML paste is handled by its parser; a text-only copy has a portable prefix.
                const plain = new DOMParser().parseFromString(text, "text/html")
                    .body.textContent;
                try {
                    if (plain.startsWith("Gyrinx callout\n")) {
                        config = normalizeCallout(
                            JSON.parse(plain.slice("Gyrinx callout\n".length)),
                        );
                        event.content = calloutHTML(config);
                    }
                    if (plain.startsWith("Gyrinx HTML block\n")) {
                        code = JSON.parse(
                            plain.slice("Gyrinx HTML block\n".length),
                        );
                        if (typeof code === "string" && code.length <= 100000)
                            event.content = htmlBlockHTML(code);
                    }
                } catch {
                    /* Unrecognised clipboard data remains ordinary pasted text. */
                }
            });
            editor.on("change input Undo Redo", () => {
                if (editor.initialized) {
                    options.onChange(
                        editor.getContent(),
                        editor
                            .getContent({ format: "text" })
                            .trim()
                            .split(/\s+/)
                            .filter(Boolean).length,
                    );
                }
            });
            editor.on("remove", () => {
                closed = true;
                cancelAnimationFrame(frame);
            });
        },
    });
    const editor = instances[0];
    const darkSkin = document.createElement("link");
    darkSkin.rel = "stylesheet";
    darkSkin.href = "/static/tinymce/skins/ui/oxide-dark/skin.min.css";
    darkSkin.media = options.dark ? "all" : "not all";
    document.head.append(darkSkin);

    return {
        editor,
        getContent: () => editor.getContent(),
        isDirty: () => editor.isDirty(),
        setDark: (dark) => {
            darkSkin.media = dark ? "all" : "not all";
            editor.gyrinxDark = dark;
            editor.getDoc().documentElement.classList.toggle("dark", dark);
            editor.getBody().classList.toggle("dark", dark);
        },
        destroy: () => editor.remove(),
    };
};
