import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Node } from "@tiptap/core";
import { NodeViewWrapper, ReactNodeViewRenderer } from "@tiptap/react";
import { Plugin } from "@tiptap/pm/state";
import { Copy, Settings2, Trash2, Plus, Minus } from "lucide-react";
import cotton from "./cotton.json";
import {
    icons,
    types,
    freshCallout,
    normalizeCallout,
    serializeCallout,
    hasIcon,
} from "./callout-model";
export { freshCallout } from "./callout-model";
import { CalloutReader } from "./callout-reader";
import { Button as SmallButton, Field, TextInput, useModal } from "./controls";
import { FileUpload } from "./uploads";
import { BodyInput } from "./callout-rich";
import { ParagraphDivider, useBlockCopy } from "./block-controls";
import { CalloutColour } from "./callout-colour";

function CalloutEditor({ node, updateAttributes, deleteNode, editor, getPos }) {
    const config = node.attrs.config;
    const [slide, setSlide] = useState(0);
    const [otherIcon, setOtherIcon] = useState(
        !Object.hasOwn(icons, config.icon),
    );
    const [iconDraft, setIconDraft] = useState(config.icon);
    const [iconError, setIconError] = useState("");
    const currentSlide = Math.min(slide, config.slides.length - 1);
    const [pendingLinks, setPendingLinks] = useState(new Set());
    useEffect(() => {
        setIconDraft(config.icon);
        setIconError("");
    }, [config.icon]);
    const latestConfig = useRef(config);
    latestConfig.current = config;
    const set = (patch) =>
        updateAttributes({ config: { ...latestConfig.current, ...patch } });
    const patchItem = (collection, key, patch) =>
        set({
            [collection]: latestConfig.current[collection].map((item, index) =>
                (collection === "links" ? item.id === key : index === key)
                    ? { ...item, ...patch }
                    : item,
            ),
        });
    const { copy, copied } = useBlockCopy({
        editor,
        getPos,
        label: "Callout",
        html: () => {
            const element = document.createElement("aside");
            element.setAttribute("data-callout", serializeCallout(config));
            element.textContent = config.body;
            return element.outerHTML;
        },
        text: () => `Gyrinx callout\n${serializeCallout(config)}`,
    });
    return (
        <NodeViewWrapper
            className="callout-editor"
            contentEditable={false}
            data-callout-editor={config.type}
        >
            <div className="callout-author-controls">
                <span>{types.find((row) => row[0] === config.type)[1]}</span>
                <SmallButton
                    icon={Copy}
                    aria-label="Copy callout"
                    title="Copy callout"
                    onClick={copy}
                />
                <SmallButton
                    icon={Trash2}
                    aria-label="Delete callout"
                    title="Delete callout"
                    onClick={deleteNode}
                />
            </div>
            <div
                onClick={(event) => {
                    if (event.target.closest("a")) event.preventDefault();
                }}
            >
                <CalloutReader key={serializeCallout(config)} config={config} />
            </div>
            <details className="callout-settings">
                <summary>
                    <Settings2 size={16} strokeWidth={1.7} />
                    Callout settings and text
                </summary>
                <div className="callout-fields">
                    <Field label="Colour">
                        <CalloutColour
                            value={config.colour}
                            onChange={(colour) => set({ colour })}
                        />
                    </Field>
                    <Field label="Lucide icon">
                        <select
                            className={cotton.select.className}
                            style={cotton.select.style}
                            value={otherIcon ? "other" : config.icon}
                            onChange={(event) => {
                                const value = event.target.value;
                                setOtherIcon(value === "other");
                                setIconError("");
                                if (value !== "other") set({ icon: value });
                            }}
                        >
                            {Object.keys(icons).map((icon) => (
                                <option key={icon} value={icon}>
                                    {icon}
                                </option>
                            ))}
                            <option value="other">Other…</option>
                        </select>
                    </Field>
                    {otherIcon && (
                        <div>
                            <Field label="Lucide icon name">
                                <TextInput
                                    value={iconDraft}
                                    maxLength={100}
                                    placeholder="e.g. compass"
                                    aria-invalid={Boolean(iconError)}
                                    onChange={(value) => {
                                        setIconDraft(value);
                                        const name = value.trim();
                                        if (hasIcon(name)) {
                                            setIconError("");
                                            set({ icon: name });
                                        } else
                                            setIconError(
                                                "Enter a Lucide icon name, such as compass.",
                                            );
                                    }}
                                />
                            </Field>
                            <p
                                className={
                                    iconError
                                        ? cotton.error
                                        : cotton.description
                                }
                                role={iconError ? "alert" : undefined}
                            >
                                {iconError ||
                                    "Paste the icon name from Lucide, such as compass or book-open."}
                            </p>
                        </div>
                    )}
                    <Field label="Label">
                        <TextInput
                            value={config.label}
                            maxLength={160}
                            onChange={(label) => set({ label })}
                        />
                    </Field>
                    <Field label="Eyebrow text">
                        <TextInput
                            value={config.eyebrow}
                            maxLength={200}
                            onChange={(eyebrow) => set({ eyebrow })}
                        />
                    </Field>
                    <label className="callout-stripe">
                        <input
                            type="checkbox"
                            checked={config.striped}
                            onChange={(event) =>
                                set({ striped: event.target.checked })
                            }
                        />
                        Striped header
                    </label>
                    <label className="callout-stripe">
                        <input
                            type="checkbox"
                            checked={config.glow === true}
                            onChange={(event) =>
                                set({ glow: event.target.checked })
                            }
                        />
                        Dark-mode glow
                    </label>
                    {config.type === "carousel" ? (
                        <>
                            <Field label="Card">
                                <select
                                    aria-label="Card"
                                    className={cotton.select.className}
                                    style={cotton.select.style}
                                    value={currentSlide}
                                    onChange={(event) =>
                                        setSlide(Number(event.target.value))
                                    }
                                >
                                    {config.slides.map((_, index) => (
                                        <option key={index} value={index}>
                                            Card {index + 1}
                                        </option>
                                    ))}
                                </select>
                            </Field>
                            <Field label="Card eyebrow">
                                <TextInput
                                    value={config.slides[currentSlide].eyebrow}
                                    onChange={(eyebrow) =>
                                        patchItem("slides", currentSlide, {
                                            eyebrow,
                                        })
                                    }
                                />
                            </Field>
                            <BodyInput
                                key={`slide-${currentSlide}`}
                                label="Card body text"
                                rich={config.slides[currentSlide].bodyRich}
                                value={config.slides[currentSlide].body}
                                onChange={(body, bodyRich) =>
                                    patchItem("slides", currentSlide, {
                                        body,
                                        bodyRich,
                                    })
                                }
                            />
                            <div className="callout-card-actions">
                                <SmallButton
                                    icon={Plus}
                                    disabled={config.slides.length >= 20}
                                    onClick={() => {
                                        set({
                                            slides: [
                                                ...config.slides,
                                                {
                                                    eyebrow: "",
                                                    body: "New card text.",
                                                    bodyRich: null,
                                                },
                                            ],
                                        });
                                        setSlide(config.slides.length);
                                    }}
                                >
                                    Add card
                                </SmallButton>
                                <SmallButton
                                    icon={Minus}
                                    disabled={config.slides.length === 1}
                                    onClick={() => {
                                        set({
                                            slides: config.slides.filter(
                                                (_, index) =>
                                                    index !== currentSlide,
                                            ),
                                        });
                                        setSlide(0);
                                    }}
                                >
                                    Remove card
                                </SmallButton>
                                <span className={cotton.description}>
                                    {config.slides.length} of 20 cards
                                </span>
                            </div>
                        </>
                    ) : (
                        <BodyInput
                            label="Body text"
                            value={config.body}
                            rich={config.bodyRich}
                            onChange={(body, bodyRich) =>
                                set({ body, bodyRich })
                            }
                        />
                    )}
                    {config.type === "expanding-info" && (
                        <BodyInput
                            label="Expanded body text"
                            value={config.detail}
                            rich={config.detailRich}
                            onChange={(detail, detailRich) =>
                                set({ detail, detailRich })
                            }
                        />
                    )}
                    {config.type === "download" && (
                        <>
                            <FileUpload onUploaded={(href) => set({ href })} />
                            <Field label="Download address">
                                <TextInput
                                    type="url"
                                    value={config.href}
                                    onChange={(href) => set({ href })}
                                />
                            </Field>
                        </>
                    )}
                    {config.type === "mail-link" && (
                        <Field label="Email recipient">
                            <TextInput
                                type="email"
                                value={config.recipient}
                                onChange={(recipient) => set({ recipient })}
                            />
                        </Field>
                    )}
                    {config.type === "link-cluster" && (
                        <div className="callout-links-settings">
                            {config.links.map((link, index) => (
                                <fieldset key={link.id}>
                                    <legend>Link {index + 1}</legend>
                                    <Field label="Link text">
                                        <TextInput
                                            value={link.label}
                                            onChange={(label) =>
                                                patchItem("links", link.id, {
                                                    label,
                                                })
                                            }
                                        />
                                    </Field>
                                    <Field label="Link address">
                                        <TextInput
                                            type="url"
                                            value={link.href}
                                            onChange={(href) =>
                                                patchItem("links", link.id, {
                                                    href,
                                                })
                                            }
                                        />
                                    </Field>
                                    <FileUpload
                                        label="Upload file for this link"
                                        onPendingChange={(pending) =>
                                            setPendingLinks((previous) => {
                                                const next = new Set(previous);
                                                if (pending) next.add(link.id);
                                                else next.delete(link.id);
                                                return next;
                                            })
                                        }
                                        onUploaded={(href) =>
                                            patchItem("links", link.id, {
                                                href,
                                            })
                                        }
                                    />
                                    <SmallButton
                                        disabled={pendingLinks.size > 0}
                                        onClick={() =>
                                            set({
                                                links: config.links.filter(
                                                    (_, i) => i !== index,
                                                ),
                                            })
                                        }
                                    >
                                        Remove link
                                    </SmallButton>
                                </fieldset>
                            ))}
                            <SmallButton
                                disabled={
                                    config.links.length >= 30 ||
                                    pendingLinks.size > 0
                                }
                                onClick={() =>
                                    set({
                                        links: [
                                            ...config.links,
                                            {
                                                id: crypto.randomUUID(),
                                                label: "New link",
                                                href: "",
                                            },
                                        ],
                                    })
                                }
                            >
                                Add link
                            </SmallButton>
                        </div>
                    )}
                </div>
            </details>
            <span role="status" className="callout-copy-status">
                {copied}
            </span>
            <ParagraphDivider
                editor={editor}
                getPos={getPos}
                node={node}
                label="Add paragraph below callout"
            />
        </NodeViewWrapper>
    );
}
export const CalloutNode = Node.create({
    name: "callout",
    group: "block",
    atom: true,
    draggable: true,
    addAttributes() {
        return { config: { default: freshCallout("info"), rendered: false } };
    },
    parseHTML() {
        return [
            {
                tag: "aside[data-callout]",
                getAttrs: (element) => {
                    try {
                        return {
                            config: normalizeCallout(
                                JSON.parse(
                                    element.getAttribute("data-callout"),
                                ),
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
            "aside",
            { "data-callout": serializeCallout(node.attrs.config) },
            ["p", node.attrs.config.body],
        ];
    },
    addNodeView() {
        return ReactNodeViewRenderer(CalloutEditor, {
            stopEvent: ({ event }) =>
                Boolean(
                    event.target.closest?.(
                        ".callout-settings, .callout-author-controls, .callout-add-paragraph",
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
                        if (!text?.startsWith("Gyrinx callout\n")) return false;
                        try {
                            const config = normalizeCallout(
                                JSON.parse(
                                    text.slice("Gyrinx callout\n".length),
                                ),
                            );
                            this.editor.commands.insertContent({
                                type: "callout",
                                attrs: { config },
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
export function CalloutMenu({ onChoose, onClose }) {
    const ref = useModal();
    return (
        <dialog
            ref={ref}
            className={`${cotton.dialog.root} editor-dialog`}
            aria-labelledby="callout-menu-title"
            onCancel={(event) => {
                event.preventDefault();
                onClose();
            }}
        >
            <div className={cotton.dialog.form}>
                <h2 id="callout-menu-title" className={cotton.dialog.title}>
                    Insert callout
                </h2>
                <div className="callout-menu-options">
                    {types.map(([type, name, icon]) => {
                        const Icon = icons[icon];
                        return (
                            <button
                                type="button"
                                className={cotton.button.ghost}
                                key={type}
                                onClick={() => onChoose(type)}
                            >
                                <Icon size={18} strokeWidth={1.7} />
                                {name}
                            </button>
                        );
                    })}
                </div>
                <div className="dialog-actions">
                    <SmallButton onClick={onClose}>Cancel</SmallButton>
                </div>
            </div>
        </dialog>
    );
}
export function RichPreview({ html, callouts = [] }) {
    const ref = useRef(null);
    const [targets, setTargets] = useState([]);
    useEffect(() => {
        setTargets(
            callouts
                .map((config, index) => ({
                    config,
                    target: ref.current.querySelector(
                        `[id="gyrinx-callout-${index}"]`,
                    ),
                }))
                .filter((item) => item.target),
        );
    }, [html, callouts]);
    return (
        <>
            <div
                ref={ref}
                className="rich-text flatpage-prose"
                aria-label="Rendered preview"
                dangerouslySetInnerHTML={{ __html: html }}
            />
            {targets.map(({ target, config }, index) =>
                createPortal(<CalloutReader config={config} />, target, index),
            )}
        </>
    );
}
