import { useEffect, useRef, useState } from "react";
import { fieldErrors } from "../../http/command";
import { Alert, Button, FieldErrors, useWorkflowForm } from "../../ui";
import { clearMove } from "./moveRecovery";
import type { DropIntent, Editor } from "./types";

export type PreparedMove = { editor: Editor; intent: DropIntent; href: string };

/** A drag is an inline command; the separate Move form is never mounted. */
export function InlineMove({
    move,
    markerKey,
    setGuard,
    onPending,
    preparing,
    onComplete,
    onDismiss,
}: {
    move: PreparedMove;
    markerKey: string;
    setGuard: (guarded: boolean) => void;
    onPending: (pending: boolean) => void;
    preparing: boolean;
    onComplete: (url: string) => void;
    onDismiss: (refresh: boolean) => void;
}) {
    const { editor, intent } = move;
    const submitted = useRef(false);
    const [storageError, setStorageError] = useState("");
    const stale = Number(editor.values.expected_revision) !== intent.revision;
    const unavailable = editor.context.unavailable === true;
    const form = useWorkflowForm({
        ...editor,
        values: { ...editor.values, ...intent.destination },
        // The overview owns bfcache restoration and fresh command preparation.
        onReload: () => {},
        onNavigate: (url) => {
            clearMove(markerKey);
            onComplete(url);
        },
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
            if (
                status === 409 &&
                data.code === "revision_conflict" &&
                fieldErrors(data.errors) &&
                data.current &&
                typeof data.current === "object" &&
                "cycle" in data.current &&
                typeof data.current.cycle === "string" &&
                "revision" in data.current &&
                typeof data.current.revision === "number"
            )
                return { kind: "conflict", errors: data.errors };
            if (
                (status === 422 ||
                    (status === 409 && data.code === "request_key_conflict")) &&
                fieldErrors(data.errors)
            )
                return { kind: "invalid", errors: data.errors };
            return null;
        },
    });
    function retainMarker() {
        try {
            sessionStorage.setItem(
                markerKey,
                JSON.stringify({
                    ...intent,
                    revision: Number(form.values.expected_revision),
                    destination:
                        editor.kind === "move-phase"
                            ? {
                                  after_occurrence_id:
                                      form.values.after_occurrence_id ?? "",
                              }
                            : {
                                  occurrence_id: form.values.occurrence_id,
                                  after_cycle_id:
                                      form.values.after_cycle_id ?? "",
                              },
                    href: move.href,
                    recoveryKey: editor.recoveryKey,
                }),
            );
        } catch {
            setStorageError(
                "Your browser could not keep this move for recovery. Allow this site to store data, then try again.",
            );
            return false;
        }
        setStorageError("");
        return true;
    }
    async function save() {
        if (!retainMarker()) return;
        await form.submit(new URLSearchParams(form.values));
    }
    useEffect(() => {
        if (submitted.current) return;
        submitted.current = true;
        if (intent.recoveryKey && !form.recovered) {
            clearMove(markerKey);
            onDismiss(false);
            return;
        }
        if (form.recovered && form.uncertain) retainMarker();
        if (
            !stale &&
            !unavailable &&
            !form.recovered &&
            !form.hasErrors &&
            !form.frozen
        )
            void save();
    }, []);
    useEffect(() => {
        setGuard(form.pending || form.uncertain);
        onPending(form.pending);
        return () => {
            setGuard(false);
            onPending(false);
        };
    }, [form.pending, form.uncertain, setGuard, onPending]);
    useEffect(() => {
        if (
            stale ||
            unavailable ||
            storageError ||
            form.recovered ||
            form.conflicted ||
            Object.keys(editor.errors).length
        )
            form.summary.current?.focus();
    }, [
        stale,
        unavailable,
        storageError,
        form.recovered,
        form.conflicted,
        editor.errors,
    ]);
    if (
        form.pending ||
        (!stale &&
            !unavailable &&
            !form.hasErrors &&
            !form.conflicted &&
            !storageError)
    )
        return null;
    const refresh =
        form.conflicted || (!form.uncertain && (stale || unavailable));
    return (
        <Alert
            tone="error"
            className="mb-3"
            dismissible={false}
            ref={form.summary}
            tabIndex={-1}
            aria-label="Move could not be completed"
        >
            <MoveSummary editor={editor} values={form.values} />
            <FieldErrors
                errors={[
                    ...Object.values(form.errors).flat(),
                    ...(storageError ? [storageError] : []),
                    ...(form.notice ? [form.notice] : []),
                    ...((stale || form.conflicted) && !form.notice
                        ? [
                              "The schedule changed. Refresh it before moving this item.",
                          ]
                        : []),
                    ...(unavailable && !form.uncertain
                        ? ["This item can no longer be moved."]
                        : []),
                ]}
            />
            <div className="mt-2 flex flex-wrap gap-2">
                {refresh ? (
                    <Button
                        size="xs"
                        disabled={preparing}
                        onClick={() => {
                            clearMove(markerKey);
                            if (form.conflicted) form.review(editor.back);
                            else onDismiss(true);
                        }}
                    >
                        Refresh schedule
                    </Button>
                ) : (
                    <Button
                        size="xs"
                        disabled={preparing}
                        onClick={() => void save()}
                    >
                        {form.uncertain ? "Retry move" : "Try again"}
                    </Button>
                )}
                {!form.uncertain && (
                    <Button
                        size="xs"
                        variant="ghost"
                        disabled={preparing}
                        onClick={() => {
                            clearMove(markerKey);
                            onDismiss(false);
                        }}
                    >
                        Dismiss
                    </Button>
                )}
            </div>
        </Alert>
    );
}

type MoveOccurrence = {
    id: string;
    number?: number;
    name: string;
    cycles: Array<{ id: string; name: string }>;
};
function MoveSummary({
    editor,
    values,
}: {
    editor: Editor;
    values: Record<string, string>;
}) {
    const occurrences = (editor.context.timelineOccurrences ??
        []) as MoveOccurrence[];
    const phaseName = (id: string) => {
        const phase = occurrences.find((item) => item.id === id);
        return phase
            ? `${String(phase.number ?? occurrences.indexOf(phase) + 1).padStart(2, "0")} ${phase.name}`
            : "Phase no longer available";
    };
    const phaseMove = editor.kind === "move-phase";
    const selected = editor.context.selectedCycle as
        { id: string; name: string } | undefined;
    const cycle =
        occurrences
            .flatMap((item) => item.cycles)
            .find((item) => item.id === values.cycle_id) ??
        (selected?.id === values.cycle_id ? selected : undefined);
    const source = phaseMove
        ? phaseName(values.occurrence_id)
        : (cycle?.name ?? "Cycle no longer available");
    const destination = phaseMove
        ? values.after_occurrence_id
            ? `After ${phaseName(values.after_occurrence_id)}`
            : "Start of timeline"
        : `${phaseName(values.occurrence_id)} · ${values.after_cycle_id ? `After ${occurrences.flatMap((item) => item.cycles).find((item) => item.id === values.after_cycle_id)?.name ?? "cycle no longer available"}` : "Start of phase"}`;
    return (
        <dl className="mb-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 text-sm [&_dd]:wrap-anywhere">
            <dt className="font-semibold">Move</dt>
            <dd>{source}</dd>
            <dt className="font-semibold">To</dt>
            <dd>{destination}</dd>
        </dl>
    );
}
