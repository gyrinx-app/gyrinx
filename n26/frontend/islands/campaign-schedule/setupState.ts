import type { Editor } from "./types";

const fields = [
    "template_id",
    "setup_definition",
    "mode",
    "date_mode",
    "date_start",
    "cycle_interval",
    "cycle_unit",
    "current_number",
    "no_current",
];
export const setupDraftKey = (editor: Editor) =>
    `${editor.recoveryKey}:setup-draft`;

export function restoreSetupDraft(editor: Editor) {
    try {
        const pending = sessionStorage.getItem(editor.recoveryKey);
        if (pending) {
            const body = new URLSearchParams(pending);
            if (!body.has("date_mode") && body.get("date_start"))
                return { ...editor.values, date_mode: "planned" };
            return editor.values;
        }
    } catch {
        /* The workflow controller owns command recovery. */
    }
    if (editor.kind !== "setup" || Object.keys(editor.errors).length)
        return editor.values;
    try {
        const saved: unknown = JSON.parse(
            sessionStorage.getItem(setupDraftKey(editor)) ?? "null",
        );
        if (!saved || typeof saved !== "object") return editor.values;
        const restored = {
            ...editor.values,
            ...Object.fromEntries(
                fields.flatMap((name) => {
                    const value = (saved as Record<string, unknown>)[name];
                    return typeof value === "string" ? [[name, value]] : [];
                }),
            ),
        };
        if (!("date_mode" in saved) && "date_start" in saved)
            restored.date_mode = "planned";
        if (!restored.template_id && !restored.setup_definition)
            restored.setup_definition = editor.values.setup_definition;
        return restored;
    } catch {
        return editor.values;
    }
}

export function retainSetupDraft(
    editor: Editor,
    values: Record<string, string>,
) {
    try {
        sessionStorage.setItem(
            setupDraftKey(editor),
            JSON.stringify(
                Object.fromEntries(
                    fields
                        .filter((name) => name in values)
                        .map((name) => [name, values[name]]),
                ),
            ),
        );
    } catch {
        /* The in-memory draft remains available when storage is blocked. */
    }
}

export function setupStageHref(action: string, stage: number) {
    const url = new URL(action, window.location.href);
    url.searchParams.set("step", String(stage));
    return url.pathname + url.search;
}
