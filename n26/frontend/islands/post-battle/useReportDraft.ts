import { useEffect, useRef, useState } from "react";
import { CommandError, postForm } from "../../http/command";
import { fields, type PostBattleProps, type ReportDisplay } from "./types";
import { displayResponse } from "./displayResponse";

type Retained = {
    draft: string;
    command: string | null;
    intent: string;
    rejected: boolean;
    generation?: string;
    revision?: number;
    models?: { id: string; name: string }[];
};
function retained(key: string): Retained | null {
    try {
        const value = JSON.parse(sessionStorage.getItem(key) || "null");
        return value &&
            typeof value.draft === "string" &&
            (value.command === null || typeof value.command === "string") &&
            typeof value.intent === "string"
            ? value
            : null;
    } catch {
        return null;
    }
}
function acknowledgedVersion(
    value: unknown,
): value is Pick<ReportDisplay, "generation" | "revision"> {
    if (!value || typeof value !== "object") return false;
    const version = value as Partial<ReportDisplay>;
    return (
        typeof version.generation === "string" &&
        Number.isInteger(version.revision)
    );
}
function mergeLater(
    canonical: URLSearchParams,
    submitted: URLSearchParams,
    latest: URLSearchParams,
) {
    const merged = new URLSearchParams(canonical);
    for (const name of new Set([...submitted.keys(), ...latest.keys()])) {
        if (
            JSON.stringify(submitted.getAll(name)) ===
            JSON.stringify(latest.getAll(name))
        )
            continue;
        merged.delete(name);
        for (const value of latest.getAll(name)) merged.append(name, value);
    }
    return merged;
}
export function useReportDraft(props: PostBattleProps) {
    const [restored] = useState(() => retained(props.recoveryKey));
    const restoredConflict =
        !!restored &&
        !restored.command &&
        (restored.generation !== props.generation ||
            restored.revision !== props.revision);
    const initial = fields(props);
    const modelNames = useRef(
        Array.isArray(restored?.models)
            ? restored.models.filter(
                  (model) =>
                      typeof model?.id === "string" &&
                      typeof model?.name === "string",
              )
            : props.models.map(({ id, name }) => ({ id, name })),
    );
    const [draft, setDraft] = useState(
        () => new URLSearchParams(restored?.draft ?? initial),
    );
    const [display, setDisplay] = useState<ReportDisplay>(props);
    const [pending, setPending] = useState<string | null>(null);
    const [busyIntent, setBusyIntent] = useState<string | null>(null);
    const [uncertain, setUncertain] = useState(
        !!restored?.command && !restored.rejected,
    );
    const [notice, setNotice] = useState(
        restored?.command
            ? "An earlier save has not been confirmed. Retry it before continuing."
            : "",
    );
    const [conflict, setConflict] = useState<ReportDisplay | null>(
        restoredConflict || (!restored && props.initialConflict)
            ? (props.currentDisplay ?? props)
            : null,
    );
    const [dirty, setDirty] = useState(!!restored && !restored.command);
    const [showErrors, setShowErrors] = useState(props.showErrors);
    const current = useRef(draft);
    const saved = useRef(initial);
    const info = useRef(display);
    const command = useRef<URLSearchParams | null>(
        restored?.command ? new URLSearchParams(restored.command) : null,
    );
    const inFlight = useRef(false);
    const unknown = useRef(!!restored?.command && !restored.rejected);
    const leaving = useRef(false);
    const editableRefusal = useRef(false);
    const summary = useRef<HTMLDivElement>(null);
    const queued = useRef<string | null>(null);
    const form = useRef<HTMLFormElement>(null);
    function persist(
        nextDraft: URLSearchParams,
        nextCommand: URLSearchParams | null,
        intent: string,
        rejected = false,
        baseline: Pick<ReportDisplay, "generation" | "revision"> = info.current,
    ) {
        sessionStorage.setItem(
            props.recoveryKey,
            JSON.stringify({
                draft: nextDraft.toString(),
                command: nextCommand?.toString() ?? null,
                intent,
                rejected,
                generation: baseline.generation,
                revision: baseline.revision,
                models: modelNames.current,
            }),
        );
    }
    function update(next: URLSearchParams) {
        if (
            unknown.current ||
            conflict ||
            info.current.applied ||
            (inFlight.current && command.current?.get("intent") === "apply")
        )
            return;
        try {
            persist(next, command.current, pending || "autosave");
        } catch {
            setNotice(
                "Your browser could not keep these entries for recovery. Allow this site to store data before continuing.",
            );
            return;
        }
        current.current = next;
        setDraft(next);
        setDirty(next.toString() !== saved.current.toString());
        if (editableRefusal.current) {
            editableRefusal.current = false;
            setNotice("");
            setDisplay((previous) => ({ ...previous, errors: [] }));
        }
    }
    function change(name: string, value: string | string[]) {
        const next = new URLSearchParams(current.current);
        next.delete(name);
        for (const item of Array.isArray(value) ? value : [value])
            next.append(name, item);
        update(next);
    }
    async function send(intent: string) {
        if (inFlight.current || conflict || info.current.applied) return;
        const initiating = intent;
        if (
            intent === "apply" &&
            current.current.toString() !== saved.current.toString() &&
            !unknown.current
        ) {
            queued.current = "apply";
            intent = "autosave";
        }
        const retrying = unknown.current;
        const snapshot = new URLSearchParams(current.current);
        let body = command.current;
        if (!retrying || !body) {
            body = new URLSearchParams(snapshot);
            body.set("generation", info.current.generation);
            body.set("revision", String(info.current.revision));
            body.set("review", info.current.review);
            body.set("submission_key", crypto.randomUUID());
            body.set("command_key", crypto.randomUUID());
            body.set("intent", intent);
            if (showErrors) body.set("showing_errors", "1");
        } else intent = body.get("intent") || "autosave";
        try {
            persist(current.current, body, intent);
        } catch {
            setNotice(
                "Your browser could not keep this save for recovery. Allow this site to store data, then try again.",
            );
            return;
        }
        command.current = body;
        inFlight.current = true;
        setPending(intent);
        setBusyIntent(initiating);
        setNotice("");
        try {
            const { status, data } = await postForm(
                props.commandHref,
                body,
                props.csrfToken,
            );
            if (
                acknowledgedVersion(data.acknowledged) &&
                (typeof data.nextUrl === "string" ||
                    (displayResponse(data.display) &&
                        (!data.newer || displayResponse(data.currentDisplay))))
            ) {
                const canonical =
                    typeof data.nextUrl === "string"
                        ? null
                        : fields(data.display as ReportDisplay);
                if (typeof data.nextUrl === "string") {
                    unknown.current = false;
                    setUncertain(false);
                    command.current = null;
                    try {
                        sessionStorage.removeItem(props.recoveryKey);
                    } catch {
                        /* The receipt still makes a retained replay safe. */
                    }
                    leaving.current = true;
                    (
                        props.onNavigate ??
                        ((url) => window.location.assign(url))
                    )(data.nextUrl);
                    return;
                }
                if (!displayResponse(data.display))
                    throw new CommandError(
                        "The saved draft could not be loaded. Retry the save to check it.",
                        "unknown",
                    );
                if (!canonical)
                    throw new CommandError(
                        "The saved draft could not be loaded. Retry the save to check it.",
                        "unknown",
                    );
                const submitted = new URLSearchParams(body);
                for (const name of [
                    "generation",
                    "revision",
                    "review",
                    "submission_key",
                    "command_key",
                    "intent",
                    "showing_errors",
                ])
                    submitted.delete(name);
                const next = mergeLater(canonical, submitted, current.current);
                unknown.current = false;
                setUncertain(false);
                command.current = null;
                saved.current = canonical;
                current.current = next;
                setDraft(next);
                info.current = data.display;
                setDisplay(data.display);
                setShowErrors(data.display.showErrors);
                const changed = next.toString() !== canonical.toString();
                setDirty(changed);
                if (data.newer && displayResponse(data.currentDisplay)) {
                    setConflict(data.currentDisplay);
                    queued.current = null;
                    setNotice(
                        "This save completed, but the report has a newer saved draft. Compare the drafts before continuing.",
                    );
                    try {
                        persist(next, null, intent, false, data.acknowledged);
                    } catch {
                        setNotice(
                            "This save completed, but your browser could not keep the comparison draft. Keep this page open until you have reviewed it.",
                        );
                    }
                } else {
                    try {
                        if (changed) persist(next, null, "autosave");
                        else sessionStorage.removeItem(props.recoveryKey);
                    } catch {
                        setNotice(
                            "This draft was saved, but your browser could not update its recovery copy. Keep this page open and check this site's storage settings.",
                        );
                    }
                    if (!changed && queued.current === "apply") {
                        queued.current = null;
                        queueMicrotask(() => {
                            void send("apply");
                        });
                    }
                }
            } else if (
                (status === 409 || status === 422) &&
                Array.isArray(data.errors)
            ) {
                queued.current = null;
                setNotice((data.errors as string[]).join(" "));
                if (!retrying) {
                    command.current = null;
                    unknown.current = false;
                    setUncertain(false);
                    if (data.conflict && displayResponse(data.currentDisplay))
                        setConflict(data.currentDisplay);
                    if (displayResponse(data.display)) {
                        editableRefusal.current = !data.conflict;
                        setDisplay(data.display);
                        setShowErrors(true);
                    }
                    persist(current.current, null, intent, true);
                } else {
                    unknown.current = true;
                    setUncertain(true);
                }
            } else
                throw new CommandError(
                    "The save could not be confirmed. Retry it before continuing.",
                    "unknown",
                );
        } catch (error) {
            queued.current = null;
            const problem =
                error instanceof CommandError
                    ? error
                    : new CommandError(
                          "The save could not be confirmed. Retry it before continuing.",
                          "unknown",
                      );
            const unresolved = retrying || problem.outcome === "unknown";
            unknown.current = unresolved;
            setUncertain(unresolved);
            setNotice(problem.message);
            if (!unresolved) {
                command.current = null;
                persist(current.current, null, intent, true);
            }
        } finally {
            inFlight.current = false;
            setPending(null);
            setBusyIntent(null);
        }
    }
    useEffect(() => {
        if (
            !dirty ||
            pending ||
            uncertain ||
            conflict ||
            notice ||
            display.applied
        )
            return;
        const timer = window.setTimeout(() => {
            void send("autosave");
        }, 900);
        return () => window.clearTimeout(timer);
    });
    useEffect(() => {
        const warn = (event: BeforeUnloadEvent) => {
            if (
                !leaving.current &&
                (inFlight.current ||
                    unknown.current ||
                    current.current.toString() !== saved.current.toString())
            ) {
                event.preventDefault();
                event.returnValue = "";
            }
        };
        const restoredPage = (event: PageTransitionEvent) => {
            if (
                event.persisted &&
                (leaving.current || retained(props.recoveryKey)?.command)
            )
                (props.onReload ?? (() => window.location.reload()))();
        };
        window.addEventListener("beforeunload", warn);
        window.addEventListener("pageshow", restoredPage);
        return () => {
            window.removeEventListener("beforeunload", warn);
            window.removeEventListener("pageshow", restoredPage);
        };
    }, [props.onReload, props.recoveryKey]);
    useEffect(() => {
        if (notice) summary.current?.focus();
    }, [notice]);
    function reviewLatest() {
        if (
            !conflict ||
            conflict.applied ||
            inFlight.current ||
            unknown.current
        )
            return;
        // Explicit review keeps a recoverable copy of the local entries for comparison.
        try {
            sessionStorage.setItem(
                `${props.recoveryKey}:previous`,
                current.current.toString(),
            );
            sessionStorage.removeItem(props.recoveryKey);
        } catch {
            setNotice(
                "Your browser could not keep the previous entries. Check this site's storage settings before continuing.",
            );
            return;
        }
        const next = fields(conflict);
        current.current = next;
        saved.current = next;
        info.current = conflict;
        setDraft(next);
        setDisplay(conflict);
        setConflict(null);
        setDirty(false);
        setNotice("");
    }
    function reloadForRecovery() {
        if (inFlight.current) return;
        try {
            persist(
                current.current,
                command.current,
                command.current?.get("intent") || "autosave",
                !unknown.current,
            );
        } catch {
            setNotice(
                "Your browser could not keep these entries for recovery.",
            );
            return;
        }
        leaving.current = true;
        (props.onReload ?? (() => window.location.reload()))();
    }
    const unconfirmedModels =
        command.current?.getAll("model_id").map((id) => ({
            id,
            name:
                modelNames.current.find((model) => model.id === id)?.name ||
                `Model ${id}`,
            xp: command.current?.get(`model-${id}-xp`) || "0",
            note: command.current?.get(`model-${id}-note`) || "",
            participated:
                command.current?.get(`model-${id}-participated`) === "on",
        })) ?? [];
    return {
        unconfirmedModels,
        draft,
        display,
        pending,
        busyIntent,
        uncertain,
        notice,
        conflict,
        dirty,
        showErrors,
        summary,
        form,
        change,
        send,
        reviewLatest,
        reloadForRecovery,
        frozen:
            uncertain || !!conflict || display.applied || pending === "apply",
    };
}

export type Draft = ReturnType<typeof useReportDraft>;
