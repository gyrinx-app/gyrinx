import type { Editor } from "./types";

const fields = [
    "template_id",
    "setup_definition",
    "mode",
    "date_start",
    "cycle_interval",
    "cycle_unit",
    "current_number",
    "no_current",
];
export const setupDraftKey = (editor: Editor) =>
    `${editor.recoveryKey}:setup-draft`;

export function restoreSetupDraft(editor: Editor) {
    if (editor.kind !== "setup" || Object.keys(editor.errors).length)
        return editor.values;
    try {
        const saved: unknown = JSON.parse(
            sessionStorage.getItem(setupDraftKey(editor)) ?? "null",
        );
        if (!saved || typeof saved !== "object") return editor.values;
        return {
            ...editor.values,
            ...Object.fromEntries(
                fields.flatMap((name) => {
                    const value = (saved as Record<string, unknown>)[name];
                    return typeof value === "string" ? [[name, value]] : [];
                }),
            ),
        };
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
