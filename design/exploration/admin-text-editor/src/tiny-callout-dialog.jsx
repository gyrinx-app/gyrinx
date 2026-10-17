import cotton from "./cotton.json";
import { hasIcon, normalizeCallout, types } from "./callout-model";
import { bodyDocument, bodyHTML, bodyText } from "./tiny-callout-content";

export function openCalloutDialog(editor, initial, onSave, contentOptions) {
    const draft = structuredClone(initial);
    let activeCard = 0,
        api,
        closed = false,
        generation = 0,
        bodyEditors = [];
    const bodyID = `callout-body-${crypto.randomUUID()}`,
        detailID = `callout-detail-${crypto.randomUUID()}`;
    const name = types.find((row) => row[0] === draft.type)[1];
    function removeBodyEditors() {
        generation++;
        bodyEditors.forEach((instance) => instance.remove());
        bodyEditors = [];
    }
    function capture() {
        const data = api.getData();
        Object.assign(draft, {
            colour: data.colour,
            icon: data.icon,
            label: data.label,
            eyebrow: data.eyebrow,
            striped: data.striped,
            glow: data.glow,
        });
        const active =
            draft.type === "carousel" ? draft.slides[activeCard] : draft;
        if (draft.type === "carousel") active.eyebrow = data.cardEyebrow;
        if (bodyEditors[0]) {
            active.bodyRich = bodyDocument(bodyEditors[0].getContent());
            active.body = bodyText(active.bodyRich);
        }
        if (bodyEditors[1]) {
            draft.detailRich = bodyDocument(bodyEditors[1].getContent());
            draft.detail = bodyText(draft.detailRich);
        }
        if (draft.type === "download") draft.href = data.href;
        if (draft.type === "mail-link") draft.recipient = data.recipient;
        if (draft.type === "link-cluster")
            draft.links = draft.links.map((link, index) => ({
                ...link,
                label: data[`linkLabel${index}`],
                href: data[`linkHref${index}`].value,
            }));
    }
    async function mountBodies() {
        const serial = generation;

        const active =
            draft.type === "carousel" ? draft.slides[activeCard] : draft;
        const fields = [
            { id: bodyID, text: active.body, rich: active.bodyRich },
        ];
        if (draft.type === "expanding-info")
            fields.push({
                id: detailID,
                text: draft.detail,
                rich: draft.detailRich,
            });
        const mounted = await Promise.all(
            fields.map(async (field, index) => {
                const target = document.getElementById(field.id);
                if (!target) return null;
                target.innerHTML = bodyHTML(field.text, field.rich);
                const instances = await window.tinymce.init({
                    ...contentOptions,
                    target,
                    inline: true,
                    toolbar_persist: false,
                    toolbar_mode: "wrap",
                    fixed_toolbar_container: `#${field.id}-toolbar`,
                    content_css: false,
                    content_style: "",
                    menubar: false,
                    statusbar: false,
                    resize: false,
                    height: 210,
                    min_height: 160,
                    plugins: "lists",
                    toolbar: false,
                    formats: { underline: { inline: "u", exact: true } },
                    setup: (instance) => {
                        bodyEditors[index] = instance;
                        instance.on("init", () =>
                            instance
                                .getDoc()
                                .documentElement.classList.toggle(
                                    "dark",
                                    Boolean(editor.gyrinxDark),
                                ),
                        );
                    },
                });
                return instances[0];
            }),
        );
        if (closed || serial !== generation) {
            mounted.forEach((instance) => instance?.remove());
            return;
        }
        bodyEditors = mounted.filter(Boolean);
    }
    function specification() {
        const input = (name, label) => ({ type: "input", name, label });
        const richField = (id, label) => ({
            type: "panel",
            items: [
                {
                    type: "htmlpanel",
                    html: `<label id="${id}-label">${label}</label>`,
                },
                {
                    type: "bar",
                    items: [
                        ["bold", "Bold", "bold"],
                        ["italic", "Italic", "italic"],
                        ["underline", "Underline", "underline"],
                        ["bullist", "Bulleted list", "unordered-list"],
                        ["numlist", "Numbered list", "ordered-list"],
                        ["clear", "Clear formatting", "remove-formatting"],
                    ].map(([command, text, icon]) => ({
                        type: "button",
                        name: `format:${id}:${command}`,
                        text,
                        icon,
                        buttonType: "toolbar",
                    })),
                },
                {
                    type: "htmlpanel",
                    html: `<div id="${id}" data-callout-body="" aria-labelledby="${id}-label" role="textbox" aria-multiline="true" style="min-height:150px;max-height:240px;overflow:auto;padding:10px;border:1px solid #d9dde3;border-radius:4px;font-size:16px;line-height:1.5;outline:none"></div>`,
                },
            ],
        });
        const items = [
            {
                type: "selectbox",
                name: "colour",
                label: "Colour",
                items: [
                    { text: "Gyrinx default", value: "default" },
                    ...cotton.colours.map((colour) => ({
                        text: colour.name,
                        value: colour.name.toLowerCase(),
                    })),
                ],
            },
            input("icon", "Lucide icon name"),
            input("label", "Label"),
            input("eyebrow", "Eyebrow text"),
            { type: "checkbox", name: "striped", label: "Striped header" },
            { type: "checkbox", name: "glow", label: "Dark-mode glow" },
        ];
        const data = {
            colour: draft.colour,
            icon: draft.icon,
            label: draft.label,
            eyebrow: draft.eyebrow,
            striped: draft.striped,
            glow: draft.glow,
        };
        if (draft.type === "carousel") {
            items.push(
                {
                    type: "selectbox",
                    name: "card",
                    label: "Card",
                    items: draft.slides.map((_, index) => ({
                        text: `Card ${index + 1}`,
                        value: String(index),
                    })),
                },
                input("cardEyebrow", "Card eyebrow"),
            );
            Object.assign(data, {
                card: String(activeCard),
                cardEyebrow: draft.slides[activeCard].eyebrow,
            });
        }
        items.push(
            richField(
                bodyID,
                draft.type === "carousel" ? "Card body text" : "Body text",
            ),
        );
        if (draft.type === "expanding-info")
            items.push(richField(detailID, "Expanded body text"));
        if (draft.type === "download") {
            items.push({
                type: "urlinput",
                name: "href",
                label: "Download address",
                filetype: "file",
            });
            data.href = { value: draft.href };
        }
        if (draft.type === "mail-link") {
            items.push(input("recipient", "Email recipient"));
            data.recipient = draft.recipient;
        }
        if (draft.type === "link-cluster") {
            draft.links.forEach((link, index) => {
                items.push({
                    type: "label",
                    label: `Link ${index + 1}`,
                    items: [
                        input(`linkLabel${index}`, "Link text"),
                        {
                            type: "urlinput",
                            name: `linkHref${index}`,
                            label: "Link address",
                            filetype: "file",
                        },
                        {
                            type: "button",
                            name: `removeLink${index}`,
                            text: `Remove link ${index + 1}`,
                        },
                    ],
                });
                data[`linkLabel${index}`] = link.label;
                data[`linkHref${index}`] = { value: link.href };
            });
            items.push({
                type: "button",
                name: "addLink",
                text: "Add link",
                enabled: draft.links.length < 30,
            });
        }
        return {
            title: `${onSave.existing ? "Edit" : "Insert"} ${name.toLowerCase()}`,
            size: "large",
            body: { type: "panel", items },
            initialData: data,
            buttons: [
                { type: "cancel", text: "Cancel" },
                ...(draft.type === "carousel"
                    ? [
                          {
                              type: "custom",
                              name: "addCard",
                              text: "Add card",
                              enabled: draft.slides.length < 20,
                          },
                          {
                              type: "custom",
                              name: "removeCard",
                              text: "Remove card",
                              enabled: draft.slides.length > 1,
                          },
                      ]
                    : []),
                {
                    type: "submit",
                    name: "save",
                    text: "Save callout",
                    primary: true,
                },
            ],
            onChange: (dialog, details) => {
                if (details.name === "card") {
                    capture();
                    activeCard = Number(dialog.getData().card);
                    redial();
                }
            },
            onAction: (dialog, details) => {
                if (details.name.startsWith("format:")) {
                    const [, id, command] = details.name.split(":");
                    const instance = window.tinymce.get(id);
                    if (!instance?.initialized) return;
                    instance.focus();
                    if (["bold", "italic", "underline"].includes(command))
                        instance.formatter.toggle(command);
                    else
                        instance.execCommand(
                            {
                                bullist: "InsertUnorderedList",
                                numlist: "InsertOrderedList",
                                clear: "RemoveFormat",
                            }[command],
                        );
                    instance.nodeChanged();
                    return;
                }
                capture();
                if (details.name === "addCard" && draft.slides.length < 20) {
                    draft.slides.push({
                        eyebrow: "",
                        body: "New card text.",
                        bodyRich: null,
                    });
                    activeCard = draft.slides.length - 1;
                }
                if (details.name === "removeCard" && draft.slides.length > 1) {
                    draft.slides.splice(activeCard, 1);
                    activeCard = Math.min(activeCard, draft.slides.length - 1);
                }
                if (details.name === "addLink" && draft.links.length < 30)
                    draft.links.push({
                        id: crypto.randomUUID(),
                        label: "New link",
                        href: "",
                    });
                if (details.name.startsWith("removeLink"))
                    draft.links.splice(
                        Number(details.name.slice("removeLink".length)),
                        1,
                    );
                redial();
            },
            onSubmit: () => {
                if (
                    !bodyEditors.length ||
                    bodyEditors.some((instance) => !instance.initialized)
                ) {
                    editor.windowManager.alert(
                        "Wait for the body editor to finish loading.",
                    );
                    return;
                }
                capture();
                if (!hasIcon(draft.icon)) {
                    editor.windowManager.alert(
                        "Enter a valid Lucide icon name, such as compass.",
                    );
                    return;
                }
                if (draft.type === "download")
                    draft.href = api.getData().href.value;
                onSave(normalizeCallout(draft));
                api.close();
            },
            onClose: () => {
                closed = true;
                removeBodyEditors();
            },
        };
    }
    function redial() {
        removeBodyEditors();
        api.redial(specification());
        requestAnimationFrame(mountBodies);
    }
    api = editor.windowManager.open(specification());
    requestAnimationFrame(mountBodies);
    return api;
}
