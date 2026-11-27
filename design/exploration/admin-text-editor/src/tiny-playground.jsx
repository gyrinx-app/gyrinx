import React, { useEffect, useRef, useState } from "react";
import { Button } from "./controls";
import cotton from "./cotton.json";
import { themeColours } from "./colours";
import { RichPreview } from "./callouts";
import { readableHTML } from "./html-output";

export function TinyPlayground({ textarea }) {
    const frame = useRef(null),
        instance = useRef(null),
        changed = useRef(false),
        mounted = useRef(true);
    const [ready, setReady] = useState(false),
        [mode, setMode] = useState("edit"),
        [dark, setDark] = useState(false),
        [html, setHTML] = useState(textarea.value),
        [words, setWords] = useState(0),
        [error, setError] = useState(""),
        [preview, setPreview] = useState({ html: "", callouts: [] });
    useEffect(() => {
        mounted.current = true;
        const sync = () => {
            if (
                instance.current &&
                (changed.current || instance.current.isDirty())
            )
                textarea.value = instance.current.getContent();
        };
        textarea.form?.addEventListener("submit", sync);
        return () => {
            mounted.current = false;
            textarea.form?.removeEventListener("submit", sync);
            instance.current?.destroy();
            textarea.hidden = false;
        };
    }, [textarea]);
    useEffect(() => {
        textarea.nextElementSibling.classList.toggle("dark", dark);
        instance.current?.setDark(dark);
    }, [dark, textarea]);
    useEffect(() => {
        if (mode !== "preview") return;
        const controller = new AbortController();
        setError("");
        setPreview({ html: "", callouts: [] });
        fetch("/preview/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": document.querySelector(
                    "[name=csrfmiddlewaretoken]",
                ).value,
            },
            body: JSON.stringify({ html }),
            signal: controller.signal,
        })
            .then((response) => {
                if (!response.ok) throw Error();
                return response.json();
            })
            .then(setPreview)
            .catch((error) => {
                if (error.name !== "AbortError")
                    setError(
                        "Preview could not load. Your draft is still in the editor.",
                    );
            });
        return () => controller.abort();
    }, [mode, html]);
    async function initialize() {
        if (instance.current) return;
        try {
            const result =
                await frame.current.contentWindow.initializeGyrinxTiny({
                    html: textarea.value,
                    label: textarea.dataset.editorLabel || "Page content",
                    version: textarea.dataset.editorVersion,
                    dark,
                    colours: themeColours(
                        textarea.nextElementSibling.shadowRoot.querySelector(
                            ".gyrinx-editor",
                        ),
                    ),
                    csrfToken: document.querySelector(
                        "[name=csrfmiddlewaretoken]",
                    ).value,
                    onChange: (value, count) => {
                        if (!mounted.current) return;
                        changed.current = true;
                        textarea.value = value;
                        setHTML(value);
                        setWords(count);
                        textarea.dispatchEvent(
                            new Event("change", { bubbles: true }),
                        );
                    },
                });
            if (!mounted.current) {
                result.destroy();
                return;
            }
            instance.current = result;
            textarea.hidden = true;
            setReady(true);
        } catch {
            setError(
                "TinyMCE could not load. Your original text remains in the form.",
            );
        }
    }
    function changeView(view) {
        if (instance.current && changed.current)
            setHTML(instance.current.getContent());
        setMode(view);
    }
    return (
        <section
            className={`gyrinx-editor ${dark ? "dark" : ""}`}
            data-tiny-playground=""
            aria-label="TinyMCE callout playground"
        >
            <div className="editor-toolbar">
                <div className="editor-bar" aria-label="Editor views">
                    <span className="editor-label">
                        TinyMCE · Callout playground
                    </span>
                    {["edit", "preview", "html"].map((view) => (
                        <Button
                            key={view}
                            aria-pressed={mode === view}
                            onClick={() => changeView(view)}
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
            </div>
            <div hidden={mode !== "edit"}>
                <iframe
                    ref={frame}
                    className="tiny-editor-frame"
                    style={{
                        height:
                            textarea.dataset.editorHeight === "20vh"
                                ? "360px"
                                : "640px",
                    }}
                    title={`${textarea.dataset.editorLabel || "Document"} — TinyMCE`}
                    src={`/tiny-editor/?v=${encodeURIComponent(textarea.dataset.editorVersion)}`}
                    onLoad={initialize}
                />
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
                    {readableHTML(html)}
                </pre>
            )}
            {error && (
                <p role="alert" className={cotton.error}>
                    {error}
                </p>
            )}
            <div className="editor-foot">
                <span>{words} words</span>
                <span role="status">
                    {!ready
                        ? "Loading TinyMCE…"
                        : changed.current
                          ? "Unsaved changes"
                          : "Ready to edit"}
                </span>
                <span>Double-click a callout to edit its settings.</span>
            </div>
        </section>
    );
}
