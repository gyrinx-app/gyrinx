import { useEffect, useState } from "react";
import { Button, Icon } from "../../ui";

export type PreviewDisplay = {
    rows: { id: string; label: string; value: string }[];
    models: { id: string; name: string; lines: string[]; error: string }[];
};
type PreviewState = "ready" | "updating" | "failed";

export function PostBattlePreview(initial: PreviewDisplay) {
    const latest = () => {
        const cached =
            document.getElementById("post-battle-form")?.dataset
                .previewSnapshot;
        return cached ? (JSON.parse(cached) as PreviewDisplay) : initial;
    };
    const [preview, setPreview] = useState(latest);
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
        setPreview(latest());
        setState((form?.dataset.previewState as PreviewState) || "ready");
        return () => form?.removeEventListener("post-battle:preview", update);
    }, []);
    return (
        <>
            <h2 id="changes-heading" className="text-lg font-semibold">
                Changes to apply
            </h2>
            <p className="mt-2 text-sm text-muted">
                These changes take effect when you apply the results.
            </p>
            <div aria-busy={state === "updating"}>
                <dl className="mt-4 space-y-3 text-sm">
                    {preview.rows.map((row) => (
                        <div
                            key={row.id}
                            className="flex min-w-0 justify-between gap-3"
                        >
                            <dt className="min-w-0 break-words">{row.label}</dt>
                            <dd className="min-w-0 break-words text-right tabular-nums">
                                {row.value}
                            </dd>
                        </div>
                    ))}
                </dl>
                <ul className="mt-4 space-y-3 text-sm">
                    {preview.models.map((model) => (
                        <li key={model.id}>
                            <p className="font-medium">{model.name}</p>
                            {model.lines.map((line, i) => (
                                <p key={i} className="text-muted tabular-nums">
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
            <p
                className="mt-4 flex items-start gap-2 border-t border-box-border pt-3 text-xs text-muted"
                role="status"
                aria-live="polite"
            >
                <Icon
                    name={
                        state === "updating"
                            ? "loader-circle"
                            : state === "failed"
                              ? "triangle-alert"
                              : "check-check"
                    }
                    className={
                        state === "updating"
                            ? "size-4 shrink-0 motion-safe:animate-spin"
                            : "size-4 shrink-0"
                    }
                />
                <span>
                    {state === "updating"
                        ? "Updating preview…"
                        : state === "failed"
                          ? "Preview is out of date. Use Save draft to retry."
                          : "Preview up to date."}
                </span>
            </p>
        </>
    );
}
