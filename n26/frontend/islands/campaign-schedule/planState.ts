import type { Editor, Phase } from "./types";

const fields = [
    "mode",
    "steps",
    "date_mode",
    "date_start",
    "cycle_interval",
    "cycle_unit",
    "date_version",
];
type Values = Record<string, string>;
type Draft = {
    baseline: Values;
    values: Values;
    modes: Values;
    revision: string;
};
export const planDraftKey = (editor: Editor) =>
    `${editor.recoveryKey}:plan-draft`;
const business = (values: Values): Values =>
    Object.fromEntries(
        fields
            .filter((field) => field in values)
            .map((field) => [field, values[field]]),
    );

function liveSteps(value: string, phases: Phase[]) {
    try {
        const steps: unknown = JSON.parse(value);
        if (!Array.isArray(steps)) return value;
        return JSON.stringify(
            steps.filter((step) =>
                phases.some((phase) => phase.id === step.phase_id),
            ),
        );
    } catch {
        return value;
    }
}

export function restorePlanDraft(editor: Editor, phases: Phase[]) {
    const fallback = {
        values: editor.values,
        modes: {} as Values,
        baseline: editor.values,
    };
    if (
        editor.kind !== "plan" ||
        Object.keys(editor.errors).length ||
        editor.initialConflict
    )
        return fallback;
    try {
        // Command recovery has precedence over an editable planning draft.
        if (sessionStorage.getItem(editor.recoveryKey)) return fallback;
        const saved: unknown = JSON.parse(
            sessionStorage.getItem(planDraftKey(editor)) ?? "null",
        );
        if (!saved || typeof saved !== "object") return fallback;
        const draft = saved as Draft;
        if (
            !draft.baseline ||
            !draft.values ||
            !draft.modes ||
            typeof draft.revision !== "string" ||
            ![draft.baseline, draft.values, draft.modes].every((values) =>
                Object.values(values).every(
                    (value) => typeof value === "string",
                ),
            )
        )
            return fallback;
        const baseline = business(draft.baseline);
        baseline.steps = liveSteps(baseline.steps, phases);
        const values = { ...editor.values, ...business(draft.values) };
        values.steps = liveSteps(values.steps, phases);
        // A separate plan edit must still conflict; phase changes may refresh the revision.
        if (baseline.steps === "[]" && editor.values.mode === "fixed") {
            baseline.mode = "fixed";
            if (values.steps === "[]") values.mode = "fixed";
        }
        const changed = fields.some(
            (field) =>
                baseline[field] !==
                (field === "steps"
                    ? liveSteps(editor.values[field], phases)
                    : editor.values[field]),
        );
        if (changed) values.expected_revision = draft.revision;
        return {
            values,
            baseline: changed ? draft.baseline : editor.values,
            modes: Object.fromEntries(
                Object.entries(draft.modes).map(([mode, steps]) => [
                    mode,
                    liveSteps(steps, phases),
                ]),
            ),
        };
    } catch {
        return fallback;
    }
}

export function retainPlanDraft(
    editor: Editor,
    values: Values,
    modes: Values,
    baseline = editor.values,
) {
    try {
        sessionStorage.setItem(
            planDraftKey(editor),
            JSON.stringify({
                baseline: business(baseline),
                values: business(values),
                modes,
                revision: values.expected_revision,
            }),
        );
    } catch {
        /* The form stays editable when browser storage is unavailable. */
    }
}

export function clearPlanDraft(editor: Editor) {
    try {
        sessionStorage.removeItem(planDraftKey(editor));
    } catch {
        /* Saving does not depend on browser storage. */
    }
}
