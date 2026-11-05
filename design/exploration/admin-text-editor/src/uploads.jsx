import React, { useEffect, useRef, useState } from "react";
import cotton from "./cotton.json";
import { Field } from "./controls";

export const uploadFormats = {
    image: {
        accept: ".png,.jpg,.jpeg,.gif,.webp",
        help: "PNG, JPEG, GIF or WebP. Up to 10 MB.",
    },
    file: {
        accept: ".pdf,.txt,.md,.csv,.docx,.xlsx,.pptx",
        help: "PDF, text, Markdown, CSV, Word, Excel or PowerPoint. Up to 10 MB.",
    },
};

export async function uploadFile(
    file,
    kind,
    signal,
    csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value,
) {
    if (!file) throw Error("Choose a file to upload.");
    if (file.size > 10 * 1024 * 1024)
        throw Error("Choose a file no larger than 10 MB.");
    const data = new FormData();
    data.append("file", file);
    data.append("kind", kind);
    const response = await fetch("/tinymce/upload/", {
        method: "POST",
        body: data,
        credentials: "same-origin",
        headers: {
            "X-CSRFToken": csrfToken || "",
        },
        signal,
    });
    const result = await response.json();
    if (!response.ok)
        throw Error(result.error || "The file could not be uploaded.");
    if (typeof result.location !== "string")
        throw Error("The upload did not return an address.");
    return result;
}

// Abort on unmount or replacement; an obsolete request must not edit a new target.
export function useUpload(kind = "file", onPendingChange) {
    const [pending, setPending] = useState(false),
        [error, setError] = useState("");
    const request = useRef(null),
        notify = useRef(onPendingChange);
    notify.current = onPendingChange;
    useEffect(
        () => () => {
            request.current?.abort();
            notify.current?.(false);
        },
        [],
    );
    async function upload(file, onUploaded) {
        request.current?.abort();
        const controller = new AbortController();
        request.current = controller;
        setError("");
        setPending(true);
        notify.current?.(true);
        try {
            const result = await uploadFile(file, kind, controller.signal);
            if (!controller.signal.aborted) onUploaded(result);
        } catch (failure) {
            if (!controller.signal.aborted)
                setError(
                    failure.message ||
                        "The file could not be uploaded. Try again.",
                );
        } finally {
            if (!controller.signal.aborted) {
                setPending(false);
                notify.current?.(false);
            }
        }
    }
    return { upload, pending, error, setError };
}

export function FileUpload({
    onUploaded,
    label = "Upload download file",
    onPendingChange,
}) {
    const [status, setStatus] = useState("");
    const { upload, pending, error } = useUpload("file", onPendingChange);
    async function choose(event) {
        const file = event.target.files[0];
        if (!file) return;
        // Reset the native input so the same file can be selected after an error.
        event.target.value = "";
        setStatus("");
        await upload(file, (result) => {
            onUploaded(result.location);
            setStatus(
                `${result.filename || file.name} uploaded. Save the page to keep the link.`,
            );
        });
    }
    return (
        <div>
            <Field label={label}>
                <input
                    type="file"
                    className={cotton.fileInput}
                    accept={uploadFormats.file.accept}
                    disabled={pending}
                    onChange={choose}
                />
            </Field>
            <p className={cotton.description}>{uploadFormats.file.help}</p>
            {error && (
                <p role="alert" className={cotton.error}>
                    {error}
                </p>
            )}
            <p role="status" className={cotton.description}>
                {pending ? "Uploading…" : status}
            </p>
        </div>
    );
}
