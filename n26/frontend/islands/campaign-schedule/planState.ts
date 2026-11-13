import type { Editor, Phase, Step } from "./types";

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
    confirmedRevision?: string;
    fixedBaseline?: string;
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

function remainingDraftSteps(
    baseline: string,
    draft: string,
    fresh: string,
    phases: Phase[],
) {
    try {
        const before = JSON.parse(liveSteps(baseline, phases)) as Step[];
        const edited = JSON.parse(liveSteps(draft, phases)) as Step[];
        const after = JSON.parse(liveSteps(fresh, phases)) as Step[];
        if (
            ![before, edited, after].every(
                (steps) =>
                    Array.isArray(steps) &&
                    steps.every(
                        (step) =>
                            step &&
                            typeof step.id === "string" &&
                            typeof step.count === "number",
                    ),
            )
        )
            return liveSteps(draft, phases);
        return JSON.stringify(
            edited.flatMap((step) => {
                const previous = before.find((value) => value.id === step.id);
                const current = after.find((value) => value.id === step.id);
                const consumed = previous
                    ? previous.count - (current?.count ?? 0)
                    : 0;
                const count = step.count - consumed;
                return consumed > 0 && count <= 0 ? [] : [{ ...step, count }];
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
        const fixedBaseline =
            draft.fixedBaseline ??
            (draft.baseline.mode === "fixed"
                ? draft.baseline.steps
                : undefined);
        const fixedFresh = Array.isArray(editor.context.fixedSteps)
            ? JSON.stringify(editor.context.fixedSteps)
            : editor.values.mode === "fixed"
              ? editor.values.steps
              : undefined;
        // Only the exact confirmed deletion may consume steps and advance the date baseline.
        if (
            draft.confirmedRevision === editor.values.expected_revision &&
            Number(draft.confirmedRevision) === Number(draft.revision) + 1 &&
            (values.mode !== "fixed" ||
                (typeof fixedBaseline === "string" && fixedFresh !== undefined))
        ) {
            for (const field of fields)
                if (
                    field !== "steps" &&
                    draft.values[field] === draft.baseline[field]
                )
                    values[field] = editor.values[field];
            if (typeof fixedBaseline === "string" && fixedFresh !== undefined) {
                const reconcile = (steps: string) =>
                    remainingDraftSteps(
                        fixedBaseline,
                        steps,
                        fixedFresh,
                        phases,
                    );
                if (values.mode === "fixed")
                    values.steps = reconcile(draft.values.steps);
                if (modes.fixed) modes.fixed = reconcile(modes.fixed);
            }
            if (values.steps === "[]" && editor.values.mode === "fixed")
                values.mode = "fixed";
            return { values, baseline: editor.values, modes };
        }
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
            modes,
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
                fixedBaseline: Array.isArray(editor.context.fixedSteps)
                    ? JSON.stringify(editor.context.fixedSteps)
                    : baseline.mode === "fixed"
                      ? baseline.steps
                      : undefined,
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
