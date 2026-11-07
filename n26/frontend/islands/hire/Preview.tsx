import { useEffect, useRef, useState } from "react";
import {
    Button,
    isModelPreview,
    ModelPreview,
    type ModelPreviewProps,
} from "../../ui";

export type PreviewCache = Map<string, ModelPreviewProps>;
type ReadState = { key: string; card?: ModelPreviewProps; error?: string };
class PreviewError extends Error {}

export function previewAddress(href: string, selection: string[]) {
    return `${href}${href.includes("?") ? "&" : "?"}selection=${encodeURIComponent(JSON.stringify([...selection].sort()))}`;
}

export function Preview({
    href,
    selection,
    cache,
}: {
    href: string;
    selection: string[];
    cache: PreviewCache;
}) {
    const key = previewAddress(href, selection);
    const region = useRef<HTMLElement>(null);
    const [attempt, setAttempt] = useState(0);
    const [read, setRead] = useState<ReadState>(() => ({
        key,
        card: cache.get(key),
    }));
    useEffect(() => {
        const cached = cache.get(key);
        if (cached) {
            setRead((previous) =>
                previous.key === key && previous.card === cached
                    ? previous
                    : { key, card: cached },
            );
            return;
        }
        const controller = new AbortController();
        let current = true;
        setRead({ key });
        async function load() {
            try {
                const response = await fetch(key, {
                    credentials: "same-origin",
                    redirect: "error",
                    signal: controller.signal,
                    headers: { Accept: "application/json" },
                });
                if (response.status === 401)
                    throw new PreviewError(
                        "Sign in again to load this preview.",
                    );
                if (response.status === 404)
                    throw new PreviewError(
                        "This preview is no longer available.",
                    );
                if (
                    !response.ok ||
                    !response.headers
                        .get("Content-Type")
                        ?.includes("application/json")
                )
                    throw new Error();
                const body: unknown = await response.json();
                if (
                    !body ||
                    typeof body !== "object" ||
                    !("preview" in body) ||
                    !isModelPreview(body.preview)
                )
                    throw new Error();
                if (!current) return;
                cache.set(key, body.preview);
                setRead({ key, card: body.preview });
            } catch (error) {
                if (!current || controller.signal.aborted) return;
                const message =
                    error instanceof PreviewError
                        ? error.message
                        : "The preview could not be loaded. Try again.";
                setRead({ key, error: message });
            }
        }
        void load();
        return () => {
            current = false;
            controller.abort();
        };
    }, [key, attempt, cache]);
    const current: ReadState =
        read.key === key ? read : { key, card: cache.get(key) };
    return (
        <section
            ref={region}
            aria-label="Model preview"
            tabIndex={-1}
            className="focus-ring"
            aria-busy={!current.card && !current.error}
        >
            {current.card ? (
                <>
                    <ModelPreview {...current.card} />
                    <p className="sr-only" role="status">
                        Preview loaded.
                    </p>
                </>
            ) : current.error ? (
                <div role="alert">
                    <p>{current.error}</p>
                    <Button
                        size="sm"
                        onClick={() => {
                            region.current?.focus();
                            setAttempt((value) => value + 1);
                        }}
                    >
                        Retry preview
                    </Button>
                </div>
            ) : (
                <p role="status">Loading preview…</p>
            )}
        </section>
    );
}
