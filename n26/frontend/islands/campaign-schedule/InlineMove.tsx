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
    onComplete,
    onDismiss,
}: {
    move: PreparedMove;
    markerKey: string;
    setGuard: (guarded: boolean) => void;
    onPending: (pending: boolean) => void;
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
    async function save() {
        try {
            sessionStorage.setItem(
                markerKey,
                JSON.stringify({
                    ...intent,
                    href: move.href,
                    recoveryKey: editor.recoveryKey,
                }),
            );
        } catch {
            setStorageError(
                "Your browser could not keep this move for recovery. Allow this site to store data, then try again.",
            );
            return;
        }
        setStorageError("");
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
                        onClick={() => {
                            clearMove(markerKey);
                            if (form.conflicted) form.review(editor.back);
                            else onDismiss(true);
                        }}
                    >
                        Refresh schedule
                    </Button>
                ) : (
                    <Button size="xs" onClick={() => void save()}>
                        {form.uncertain ? "Retry move" : "Try again"}
                    </Button>
                )}
                {!form.uncertain && (
                    <Button
                        size="xs"
                        variant="ghost"
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
