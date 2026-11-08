import { type FormEvent, useEffect, useRef, useState } from "react";
import { CommandError, postForm, type FormErrors } from "../http/command";

type Values<V> = { [K in keyof V]: string };
export type WorkflowResult =
    | { kind: "saved"; nextUrl: string }
    | { kind: "invalid"; errors: FormErrors }
    | { kind: "conflict"; errors: FormErrors };

const REJECTED_DRAFT = "__workflow_rejected";
function recover(
    key: string,
    fields: string[],
): { body: URLSearchParams; rejected: boolean } | null {
    try {
        const stored = sessionStorage.getItem(key);
        if (!stored) return null;
        const data = new URLSearchParams(stored);
        if (!fields.every((name) => data.has(name))) return null;
        const rejected = data.get(REJECTED_DRAFT) === "1";
        data.delete(REJECTED_DRAFT);
        return { body: data, rejected };
    } catch {
        return null;
    }
}
function clearRecovery(key: string) {
    try {
        sessionStorage.removeItem(key);
    } catch {
        // A retained command can still be retried safely.
    }
}

/** Recovery and navigation for a form whose server supports safe retries. */
export function useWorkflowForm<
    V extends Record<string, string | number>,
>(options: {
    values: V;
    errors: FormErrors;
    initialConflict?: boolean;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
    interpret: (
        status: number,
        data: Record<string, unknown>,
    ) => WorkflowResult | null;
    onNavigate?: (url: string) => void;
    onReload?: () => void;
}) {
    const [fields] = useState(() => Object.keys(options.values));
    const [recovery] = useState(() => recover(options.recoveryKey, fields));
    const [values, setValues] = useState<Values<V>>(
        () =>
            Object.fromEntries(
                Object.entries(options.values).map(([key, value]) => [
                    key,
                    recovery ? recovery.body.get(key)! : String(value),
                ]),
            ) as Values<V>,
    );
    const [errors, setErrors] = useState<FormErrors>(
        recovery ? {} : options.errors,
    );
    const [conflicted, setConflicted] = useState(
        !recovery && !!options.initialConflict,
    );
    const [pending, setPending] = useState(false);
    const [uncertain, setUncertain] = useState(
        !!recovery && !recovery.rejected,
    );
    const [notice, setNotice] = useState(
        recovery?.rejected
            ? "Your earlier draft was not saved. Review it before saving."
            : recovery
              ? "An earlier save has not been confirmed. Retry it before making another change."
              : "",
    );
    const inFlight = useRef(false);
    const saved = useRef(false);
    const unknownOutcome = useRef(!!recovery && !recovery.rejected);
    const submitted = useRef<URLSearchParams | null>(recovery?.body ?? null);
    const summary = useRef<HTMLDivElement>(null);
    const [failure, setFailure] = useState(recovery ? 1 : 0);
    useEffect(() => {
        // A restored rejected draft has no outstanding write to recover.
        if (recovery?.rejected) clearRecovery(options.recoveryKey);
    }, [recovery, options.recoveryKey]);
    useEffect(() => {
        const restore = (event: PageTransitionEvent) => {
            if (
                event.persisted &&
                (saved.current || recover(options.recoveryKey, fields))
            )
                (options.onReload ?? (() => window.location.reload()))();
        };
        window.addEventListener("pageshow", restore);
        return () => window.removeEventListener("pageshow", restore);
    }, [options.onReload, options.recoveryKey, fields]);
    useEffect(() => {
        if (failure) summary.current?.focus();
    }, [failure]);
    useEffect(() => {
        if (!uncertain && !pending) return;
        const warn = (event: BeforeUnloadEvent) => {
            if (unknownOutcome.current) {
                event.preventDefault();
                event.returnValue = true;
            }
        };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [uncertain, pending]);

    async function save(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (inFlight.current || conflicted) return;
        inFlight.current = true;
        unknownOutcome.current = true;
        setPending(true);
        setNotice("");
        if (!uncertain) {
            submitted.current = new URLSearchParams();
            new FormData(event.currentTarget).forEach((value, name) =>
                submitted.current!.append(name, String(value)),
            );
            submitted.current.delete("csrfmiddlewaretoken");
        }
        try {
            try {
                sessionStorage.setItem(
                    options.recoveryKey,
                    submitted.current!.toString(),
                );
            } catch {
                throw new CommandError(
                    "Your browser could not keep this save for recovery. Allow this site to store data, then try again.",
                    "rejected",
                );
            }
            const body = new URLSearchParams(submitted.current!);
            body.set("csrfmiddlewaretoken", options.csrfToken);
            const { status, data } = await postForm(
                options.commandHref,
                body,
                options.csrfToken,
            );
            const result = options.interpret(status, data);
            if (result?.kind === "saved") {
                saved.current = true;
                unknownOutcome.current = false;
                clearRecovery(options.recoveryKey);
                setUncertain(false);
                (options.onNavigate ?? ((url) => window.location.assign(url)))(
                    result.nextUrl,
                );
                return;
            }
            if (result?.kind === "conflict") {
                setConflicted(true);
                setErrors(result.errors);
                setUncertain(true);
                unknownOutcome.current = false;
            } else if (result?.kind === "invalid") {
                setErrors(result.errors);
                if (uncertain) {
                    unknownOutcome.current = true;
                    setNotice(
                        "The earlier save is still unconfirmed. Retry it before making another change.",
                    );
                } else {
                    clearRecovery(options.recoveryKey);
                    unknownOutcome.current = false;
                    setUncertain(false);
                }
            } else {
                throw new CommandError(
                    "The save could not be confirmed. Retry this save before making another change.",
                    "unknown",
                );
            }
        } catch (error) {
            const problem =
                error instanceof CommandError
                    ? error
                    : new CommandError(
                          "The save could not be confirmed. Retry this save before making another change.",
                          "unknown",
                      );
            setNotice(problem.message);
            // Rejection of this request cannot resolve an earlier uncertain write.
            unknownOutcome.current = uncertain || problem.outcome === "unknown";
            if (!unknownOutcome.current) clearRecovery(options.recoveryKey);
            setUncertain(unknownOutcome.current);
        } finally {
            inFlight.current = false;
            setPending(false);
            setFailure((n) => n + 1);
        }
    }
    function review(url: string) {
        if (!conflicted || inFlight.current) return;
        try {
            sessionStorage.removeItem(options.recoveryKey);
        } catch {
            setNotice(
                "Your browser could not clear this draft. Check this site’s storage settings, then try again.",
            );
            return;
        }
        unknownOutcome.current = false;
        (options.onNavigate ?? ((href) => window.location.replace(href)))(url);
    }
    function recoverAt(url: string, element: HTMLFormElement) {
        if (inFlight.current) return;
        const retained =
            unknownOutcome.current && submitted.current
                ? new URLSearchParams(submitted.current)
                : new URLSearchParams(
                      Array.from(new FormData(element), ([name, value]) => [
                          name,
                          String(value),
                      ]),
                  );
        retained.delete("csrfmiddlewaretoken");
        retained.delete(REJECTED_DRAFT);
        if (!unknownOutcome.current) retained.set(REJECTED_DRAFT, "1");
        try {
            if (
                new URL(url, window.location.href).origin !==
                window.location.origin
            )
                throw new Error();
            sessionStorage.setItem(options.recoveryKey, retained.toString());
        } catch {
            setNotice(
                "Your browser could not keep this draft for recovery. Allow this site to store data, then try again.",
            );
            setFailure((value) => value + 1);
            return;
        }
        // This navigation continues the retained task instead of abandoning it.
        unknownOutcome.current = false;
        (options.onNavigate ?? ((href) => window.location.assign(href)))(url);
    }
    return {
        values,
        setValues,
        errors,
        conflicted,
        pending,
        uncertain,
        notice,
        save,
        review,
        recoverAt,
        summary,
        frozen: pending || uncertain || conflicted,
        hasErrors:
            !!notice ||
            Object.values(errors).some((messages) => messages.length > 0),
    };
}
