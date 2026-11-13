import type { Editor, Phase, Step } from "./types";

const fields = [
    "mode",
    "steps",
    "date_mode",
    "date_start",
    "cycle_interval",
    "cycle_unit",
];
type Values = Record<string, string>;
type Draft = {
    baseline: Values;
    values: Values;
    modes: Values;
    revision: string;
    confirmedRevision?: string;
    savedStepCounts?: Record<string, number>;
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

function savedCounts(value: unknown): Record<string, number> | null {
    if (
        !value ||
        typeof value !== "object" ||
        Array.isArray(value) ||
        !Object.values(value).every(
            (count) =>
                typeof count === "number" &&
                Number.isInteger(count) &&
                count >= 0,
        )
    )
        return null;
    return value as Record<string, number>;
}

function remainingDraftSteps(
    draft: string,
    consumed: Record<string, number>,
    phases: Phase[],
) {
    try {
        const edited = JSON.parse(liveSteps(draft, phases)) as Step[];
        if (
            !Array.isArray(edited) ||
            !edited.every(
                (step) =>
                    step &&
                    typeof step.id === "string" &&
                    typeof step.count === "number",
            )
        )
            return liveSteps(draft, phases);
        return JSON.stringify(
            edited.flatMap((step) => {
                const saved = consumed[step.id] ?? 0;
                const count = step.count - saved;
                return saved > 0 && count <= 0 ? [] : [{ ...step, count }];
            }),
        );
    } catch {
        return liveSteps(draft, phases);
    }
}

export function confirmPhaseDeletion(
    editor: Editor,
    values: Values,
    revision: unknown,
) {
    const key = editor.context.planRecoveryKey;
    if (
        editor.kind !== "delete-phase" ||
        typeof key !== "string" ||
        typeof revision !== "number" ||
        revision !== Number(values.expected_revision) + 1
    )
        return;
    try {
        const saved = sessionStorage.getItem(`${key}:plan-draft`);
        if (!saved) return;
        const draft = JSON.parse(saved) as Draft;
        if (draft.revision === values.expected_revision)
            sessionStorage.setItem(
                `${key}:plan-draft`,
                JSON.stringify({
                    ...draft,
                    confirmedRevision: String(revision),
                }),
            );
    } catch {
        /* A confirmed deletion does not depend on retaining a planning draft. */
    }
}

export function restorePlanDraft(editor: Editor, phases: Phase[]) {
    const fallback = {
        values: editor.values,
        modes: {} as Values,
        baseline: editor.values,
        savedStepCounts: savedCounts(editor.context.savedStepCounts),
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
        const modes = Object.fromEntries(
            Object.entries(draft.modes).map(([mode, steps]) => [
                mode,
                liveSteps(steps, phases),
            ]),
        );
        // Only the exact confirmed deletion may consume steps and advance the date baseline.
        if (
            draft.confirmedRevision === editor.values.expected_revision &&
            Number(draft.confirmedRevision) === Number(draft.revision) + 1
        ) {
            const before = savedCounts(draft.savedStepCounts);
            const after = savedCounts(editor.context.savedStepCounts);
            if (
                !before ||
                !after ||
                Object.entries(before).some(
                    ([id, count]) => (after[id] ?? 0) < count,
                )
            ) {
                values.expected_revision = draft.revision;
                return {
                    values,
                    baseline: draft.baseline,
                    modes,
                    savedStepCounts: before,
                };
            }
            const consumed = Object.fromEntries(
                Object.entries(after).map(([id, count]) => [
                    id,
                    count - (before[id] ?? 0),
                ]),
            );
            for (const field of fields)
                if (
                    field !== "steps" &&
                    field !== "mode" &&
                    draft.values[field] === draft.baseline[field]
                )
                    values[field] = editor.values[field];
            if (values.mode === "fixed")
                values.steps = remainingDraftSteps(
                    draft.values.steps,
                    consumed,
                    phases,
                );
            if (modes.fixed)
                modes.fixed = remainingDraftSteps(
                    modes.fixed,
                    consumed,
                    phases,
                );
            if (values.steps === "[]" && editor.values.mode === "fixed")
                values.mode = "fixed";
            return {
                values,
                baseline: editor.values,
                modes,
                savedStepCounts: after,
            };
        }
        // A separate plan edit must still conflict; phase changes may refresh the revision.
        if (baseline.steps === "[]" && editor.values.mode === "fixed") {
            baseline.mode = "fixed";
            if (values.steps === "[]") values.mode = "fixed";
        }
        const before = savedCounts(draft.savedStepCounts);
        const after = savedCounts(editor.context.savedStepCounts);
        const savedChanged =
            before &&
            after &&
            Object.keys({ ...before, ...after }).some(
                (id) => (before[id] ?? 0) !== (after[id] ?? 0),
            );
        const changed =
            savedChanged ||
            fields.some(
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
            modes,
            savedStepCounts: changed ? before : after,
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
    counts = savedCounts(editor.context.savedStepCounts),
) {
    try {
        sessionStorage.setItem(
            planDraftKey(editor),
            JSON.stringify({
                baseline: business(baseline),
                values: business(values),
                modes,
                revision: values.expected_revision,
                savedStepCounts: counts ?? undefined,
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
