import { useEffect, useRef, useState } from "react";
import { Textarea, FieldErrors } from "./index";

export type RichTextEditorConfig = {
    scriptUrl: string;
    imageSetupUrl: string;
    uploadUrl: string;
    config: Record<string, unknown>;
};
type Editor = {
    on: (events: string, callback: () => void) => void;
    getContent: () => string;
    setContent: (value: string) => void;
    remove: () => void;
    mode: { set: (mode: string) => void };
};
type TinyMCE = { init: (config: Record<string, unknown>) => Promise<Editor[]> };
type EditorWindow = Window & {
    tinymce?: TinyMCE;
    n26CampaignImages?: (editor: Editor) => void;
};
const scripts = new Map<string, Promise<void>>();
function loadScript(src: string) {
    if (!scripts.has(src)) {
        const promise = new Promise<void>((resolve, reject) => {
            const script = document.createElement("script");
            script.src = src;
            script.onload = () => resolve();
            script.onerror = () => {
                scripts.delete(src);
                reject(new Error("editor"));
            };
            document.head.append(script);
        });
        scripts.set(src, promise);
    }
    return scripts.get(src)!;
}

/** TinyMCE owns its editor DOM; React owns the draft and the editor lifecycle. */
export function RichTextEditor({
    id,
    label,
    value,
    onChange,
    config,
    csrfToken,
    disabled = false,
    onUploading,
}: {
    id: string;
    label: string;
    value: string;
    onChange: (value: string) => void;
    config?: RichTextEditorConfig;
    csrfToken: string;
    disabled?: boolean;
    onUploading?: (uploading: boolean) => void;
}) {
    const textarea = useRef<HTMLTextAreaElement>(null);
    const editor = useRef<Editor | null>(null);
    const current = useRef({
        value,
        onChange,
        disabled,
        csrfToken,
        onUploading,
    });
    current.current = { value, onChange, disabled, csrfToken, onUploading };
    const [error, setError] = useState("");
    useEffect(() => {
        if (!config || !textarea.current) return;
        let cancelled = false;
        let generation = 0;
        let uploads = 0;
        const editorWindow = window as EditorWindow;
        const initialize = async () => {
            const run = ++generation;
            await loadScript(config.imageSetupUrl);
            await loadScript(config.scriptUrl);
            if (cancelled || run !== generation) return;
            editor.current?.remove();
            editor.current = null;
            const dark = document.documentElement.classList.contains("dark");
            const editors = await editorWindow.tinymce!.init({
                ...config.config,
                target: textarea.current,
                height: 320,
                max_height: 520,
                skin: dark ? "oxide-dark" : "oxide",
                content_css: dark ? "dark" : "default",
                iframe_aria_text: label,
                readonly: current.current.disabled,
                setup(instance: Editor) {
                    editorWindow.n26CampaignImages?.(instance);
                    instance.on("init", () => {
                        instance.setContent(current.current.value);
                        instance.mode.set(
                            current.current.disabled ? "readonly" : "design",
                        );
                    });
                    instance.on("input change undo redo", () => {
                        current.current.onChange(instance.getContent());
                    });
                },
                async images_upload_handler(blob: {
                    blob: () => Blob;
                    filename: () => string;
                }) {
                    uploads += 1;
                    current.current.onUploading?.(true);
                    try {
                        const body = new FormData();
                        body.append("file", blob.blob(), blob.filename());
                        const response = await fetch(config.uploadUrl, {
                            method: "POST",
                            credentials: "same-origin",
                            headers: {
                                "X-CSRFToken": current.current.csrfToken,
                            },
                            body,
                        });
                        const data = await response.json();
                        if (!response.ok || typeof data.location !== "string")
                            throw new Error(
                                "Image upload failed. Try uploading the image again.",
                            );
                        return data.location;
                    } finally {
                        uploads -= 1;
                        if (!cancelled)
                            current.current.onUploading?.(uploads > 0);
                    }
                },
            });
            if (cancelled || run !== generation)
                editors.forEach((e) => e.remove());
            else editor.current = editors[0];
        };
        initialize().catch(() => {
            if (!cancelled)
                setError(
                    "The editor could not load. Reload the page to use formatting and images.",
                );
        });
        let dark = document.documentElement.classList.contains("dark");
        const observer = new MutationObserver(() => {
            const next = document.documentElement.classList.contains("dark");
            if (next !== dark) {
                dark = next;
                initialize().catch(() => {
                    if (!cancelled)
                        setError(
                            "The editor could not load. Reload the page to use formatting and images.",
                        );
                });
            }
        });
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["class"],
        });
        return () => {
            cancelled = true;
            generation += 1;
            observer.disconnect();
            editor.current?.remove();
            editor.current = null;
        };
    }, [config, id, label]);
    useEffect(() => {
        if (editor.current && editor.current.getContent() !== value)
            editor.current.setContent(value);
    }, [value]);
    useEffect(() => {
        editor.current?.mode.set(disabled ? "readonly" : "design");
    }, [disabled]);
    return (
        <div className="space-y-2">
            <Textarea
                ref={textarea}
                id={id}
                aria-label={label}
                rows={8}
                defaultValue={value}
                disabled={disabled}
                onChange={(e) => onChange(e.target.value)}
            />
            {error && <FieldErrors errors={[error]} />}
        </div>
    );
}
