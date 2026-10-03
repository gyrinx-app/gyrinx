import { useEffect, useState } from "react";
import { Button } from "../../ui";

export type PreviewDisplay = {
    rows: { label: string; value: string }[];
    models: { id: string; name: string; lines: string[]; error: string }[];
};
type PreviewState = "ready" | "updating" | "failed";

export function PostBattlePreview(initial: PreviewDisplay) {
    const [preview, setPreview] = useState(initial);
    const [state, setState] = useState<PreviewState>(
        () =>
            (document.getElementById("post-battle-form")?.dataset
                .previewState as PreviewState) || "ready",
    );
    useEffect(() => {
        const form = document.getElementById("post-battle-form");
        const update = (event: Event) => {
            const detail = (
                event as CustomEvent<{
                    state: PreviewState;
                    preview?: PreviewDisplay;
                }>
            ).detail;
            if (detail.preview) setPreview(detail.preview);
            setState(detail.state);
        };
        form?.addEventListener("post-battle:preview", update);
        return () => form?.removeEventListener("post-battle:preview", update);
    }, []);
    return (
        <>
            <h2 id="changes-heading" className="text-lg font-semibold">
                Changes to apply
            </h2>
            <p className="mt-2 text-sm text-muted">
                The preview updates as you edit. Nothing changes until you apply
                the results.
            </p>
            <p
                className="mt-2 text-sm text-muted"
                role="status"
                aria-live="polite"
            >
                {state === "updating"
                    ? "Updating preview…"
                    : state === "failed"
                      ? "Preview is out of date. Use Save draft to retry."
                      : "Preview up to date"}
            </p>
            <div aria-busy={state === "updating"}>
                <dl className="mt-4 space-y-3 text-sm">
                    {preview.rows.map((row) => (
                        <div
                            key={row.label}
                            className="flex justify-between gap-3"
                        >
                            <dt>{row.label}</dt>
                            <dd className="tabular-nums">{row.value}</dd>
                        </div>
                    ))}
                </dl>
                <ul className="mt-4 space-y-3 text-sm">
                    {preview.models.map((model) => (
                        <li key={model.id}>
                            <p className="font-medium">{model.name}</p>
                            {model.lines.map((line, i) => (
                                <p key={i} className="text-muted">
                                    {line}
                                </p>
                            ))}
                            {model.error && (
                                <p className="text-red-700 dark:text-red-300">
                                    {model.error}
                                </p>
                            )}
                        </li>
                    ))}
                </ul>
            </div>
            <Button
                type="submit"
                name="intent"
                value="check"
                className="mt-4 w-full"
            >
                Check changes
            </Button>
        </>
    );
}
