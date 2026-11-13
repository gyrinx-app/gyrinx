import { afterEach, expect, test } from "vitest";
import {
    clearPlanDraft,
    retainPlanDraft,
    restorePlanDraft,
    confirmPhaseDeletion,
} from "./planState";
import type { Editor, Phase } from "./types";

const steps = [
    { id: "one", phase_id: "opening", count: 3 },
    { id: "two", phase_id: "downtime", count: 1 },
];
const phases = [{ id: "opening" }, { id: "downtime" }] as Phase[];
const editor: Editor = {
    heading: "Phase and schedule settings",
    lead: "",
    context: { savedStepCounts: {} },
    initialConflict: false,
    current: null,
    templates: [],
    action: "/cycles/edit/plan/",
    commandHref: "/cycles/commands/plan/",
    csrfToken: "fresh",
    back: "/cycles/",
    kind: "plan",
    recoveryKey: "plan:user:campaign",
    errors: {},
    values: {
        request_key: "original-key",
        expected_revision: "1",
        mode: "fixed",
        steps: JSON.stringify(steps),
        date_mode: "manual",
        date_start: "",
        cycle_interval: "1",
        cycle_unit: "weeks",
        date_version: "1",
    },
};
afterEach(() => sessionStorage.clear());

test("a deleted phase is removed from each retained mode while edited surviving counts keep a fresh revision", () => {
    const draft = {
        ...editor.values,
        steps: JSON.stringify([{ ...steps[0], count: 7 }, steps[1]]),
    };
    retainPlanDraft(editor, draft, {
        fixed: draft.steps,
        repeating: draft.steps,
    });
    const fresh = {
        ...editor,
        values: {
            ...editor.values,
            request_key: "fresh",
            expected_revision: "2",
            steps: JSON.stringify([steps[0]], null, 2),
        },
    };
    const restored = restorePlanDraft(fresh, phases.slice(0, 1));
    expect(restored.values.request_key).toBe("fresh");
    expect(restored.values.expected_revision).toBe("2");
    expect(JSON.parse(restored.values.steps)).toEqual([
        { ...steps[0], count: 7 },
    ]);
    expect(JSON.parse(restored.modes.repeating)).toEqual([
        { ...steps[0], count: 7 },
    ]);
});

test("an unrelated plan change retains the draft's revision across repeated visits to require explicit review", () => {
    const draft = { ...editor.values, cycle_interval: "2" };
    retainPlanDraft(editor, draft, {});
    const fresh = {
        ...editor,
        values: { ...editor.values, expected_revision: "3", mode: "repeating" },
    };
    const restored = restorePlanDraft(fresh, phases);
    expect(restored.values.expected_revision).toBe("1");
    expect(restored.values.cycle_interval).toBe("2");
    retainPlanDraft(fresh, restored.values, restored.modes, restored.baseline);
    expect(restorePlanDraft(fresh, phases).values.expected_revision).toBe("1");
});

test("a retained uncertain command takes precedence over the planning draft", () => {
    retainPlanDraft(editor, { ...editor.values, cycle_interval: "7" }, {});
    sessionStorage.setItem(editor.recoveryKey, "request_key=uncertain");
    expect(restorePlanDraft(editor, phases).values).toEqual(editor.values);
});

test("clearing a planning draft leaves an unresolved command untouched", () => {
    retainPlanDraft(editor, { ...editor.values, cycle_interval: "7" }, {});
    sessionStorage.setItem(editor.recoveryKey, "request_key=uncertain");
    clearPlanDraft(editor);
    expect(sessionStorage.getItem(editor.recoveryKey)).toBe(
        "request_key=uncertain",
    );
    sessionStorage.removeItem(editor.recoveryKey);
    expect(restorePlanDraft(editor, phases).values).toEqual(editor.values);
});

test.each([false, true])(
    "a confirmed projected replacement reconciles consumed counts and dates (edited date: %s)",
    (editedDate) => {
        const baseline = {
            ...editor,
            values: {
                ...editor.values,
                date_mode: "planned",
                date_start: "2026-11-08",
                steps: JSON.stringify([steps[0], { ...steps[1], count: 4 }]),
            },
        };
        const draft = {
            ...baseline.values,
            cycle_interval: "2",
            date_start: editedDate ? "2026-12-10" : baseline.values.date_start,
            steps: JSON.stringify([steps[0], { ...steps[1], count: 7 }]),
        };
        retainPlanDraft(baseline, draft, {
            fixed: draft.steps,
            repeating: draft.steps,
        });
        confirmPhaseDeletion(
            {
                ...editor,
                kind: "delete-phase",
                context: { planRecoveryKey: editor.recoveryKey },
            },
            { expected_revision: "1" },
            2,
        );
        const fresh = {
            ...baseline,
            context: { savedStepCounts: { two: 2 } },
            values: {
                ...baseline.values,
                request_key: "fresh-key",
                expected_revision: "2",
                date_start: "2026-11-22",
                steps: JSON.stringify([{ ...steps[1], count: 2 }]),
            },
        };
        const restored = restorePlanDraft(fresh, phases.slice(1));
        expect(restored.values.expected_revision).toBe("2");
        expect(restored.values.request_key).toBe("fresh-key");
        expect(restored.values.date_start).toBe(
            editedDate ? "2026-12-10" : "2026-11-22",
        );
        expect(restored.values.cycle_interval).toBe("2");
        expect(JSON.parse(restored.values.steps)).toEqual([
            { ...steps[1], count: 5 },
        ]);
        expect(JSON.parse(restored.modes.fixed)).toEqual([
            { ...steps[1], count: 5 },
        ]);
        expect(JSON.parse(restored.modes.repeating)).toEqual([
            { ...steps[1], count: 7 },
        ]);
        retainPlanDraft(
            fresh,
            restored.values,
            restored.modes,
            restored.baseline,
        );
        expect(
            restorePlanDraft(fresh, phases.slice(1)).values.expected_revision,
        ).toBe("2");
    },
);

test.each(["before", "after"])(
    "a separate plan revision %s the deletion cannot refresh the retained draft",
    (when) => {
        const draft = { ...editor.values, cycle_interval: "2" };
        retainPlanDraft(editor, draft, {});
        confirmPhaseDeletion(
            {
                ...editor,
                kind: "delete-phase",
                context: { planRecoveryKey: editor.recoveryKey },
            },
            { expected_revision: when === "before" ? "2" : "1" },
            when === "before" ? 3 : 2,
        );
        const fresh = {
            ...editor,
            values: {
                ...editor.values,
                expected_revision: "3",
                mode: "repeating",
            },
        };
        const restored = restorePlanDraft(fresh, phases);
        expect(restored.values.expected_revision).toBe("1");
        expect(restored.values.cycle_interval).toBe("2");
    },
);

test("a fixed-mode draft consumes only the saved prefix when the persisted plan was repeating", () => {
    const baseline = {
        ...editor,
        context: {
            fixedSteps: [{ ...steps[1], count: 4 }],
            savedStepCounts: {},
        },
        values: { ...editor.values, mode: "repeating" },
    };
    const draft = {
        ...baseline.values,
        mode: "fixed",
        steps: JSON.stringify([{ ...steps[1], count: 7 }]),
    };
    retainPlanDraft(baseline, draft, { fixed: draft.steps });
    confirmPhaseDeletion(
        {
            ...editor,
            kind: "delete-phase",
            context: { planRecoveryKey: editor.recoveryKey },
        },
        { expected_revision: "1" },
        2,
    );
    const fresh = {
        ...baseline,
        context: {
            fixedSteps: [{ ...steps[1], count: 2 }],
            savedStepCounts: { two: 2 },
        },
        values: {
            ...baseline.values,
            expected_revision: "2",
            steps: JSON.stringify([steps[1]]),
        },
    };
    const restored = restorePlanDraft(fresh, phases.slice(1));
    expect(restored.values.mode).toBe("fixed");
    expect(restored.values.expected_revision).toBe("2");
    expect(JSON.parse(restored.values.steps)).toEqual([
        { ...steps[1], count: 5 },
    ]);
});

test("a fixed draft subtracts every newly saved cycle across repetition boundaries", () => {
    const a = { id: "a-step", phase_id: "opening", count: 1 };
    const b = { id: "b-step", phase_id: "downtime", count: 2 };
    const baseline = {
        ...editor,
        context: {
            fixedSteps: [b],
            savedStepCounts: { "a-step": 1, "b-step": 0 },
        },
        values: {
            ...editor.values,
            mode: "repeating",
            steps: JSON.stringify([a, b]),
        },
    };
    const draft = {
        ...baseline.values,
        mode: "fixed",
        steps: JSON.stringify([{ ...b, count: 5 }]),
    };
    retainPlanDraft(baseline, draft, { fixed: draft.steps });
    confirmPhaseDeletion(
        {
            ...editor,
            kind: "delete-phase",
            context: { planRecoveryKey: editor.recoveryKey },
        },
        { expected_revision: "1" },
        2,
    );
    const fresh = {
        ...baseline,
        context: {
            fixedSteps: [{ ...b, count: 1 }],
            savedStepCounts: { "a-step": 2, "b-step": 3 },
        },
        values: {
            ...baseline.values,
            expected_revision: "2",
            steps: JSON.stringify([b]),
        },
    };
    const restored = restorePlanDraft(fresh, phases.slice(1));
    expect(restored.values.expected_revision).toBe("2");
    expect(JSON.parse(restored.values.steps)).toEqual([{ ...b, count: 2 }]);
    expect(JSON.parse(restored.modes.fixed)).toEqual([{ ...b, count: 2 }]);
});

test("a fully consumed fixed step still deducts its newly saved cycle from the edited draft", () => {
    const baseline = {
        ...editor,
        values: { ...editor.values, steps: JSON.stringify([steps[1]]) },
    };
    const draft = {
        ...baseline.values,
        steps: JSON.stringify([{ ...steps[1], count: 5 }]),
    };
    retainPlanDraft(baseline, draft, { fixed: draft.steps });
    confirmPhaseDeletion(
        {
            ...editor,
            kind: "delete-phase",
            context: { planRecoveryKey: editor.recoveryKey },
        },
        { expected_revision: "1" },
        2,
    );
    const fresh = {
        ...baseline,
        context: { savedStepCounts: { two: 1 } },
        values: { ...baseline.values, expected_revision: "2", steps: "[]" },
    };
    const restored = restorePlanDraft(fresh, phases.slice(1));
    expect(restored.values.expected_revision).toBe("2");
    expect(JSON.parse(restored.values.steps)).toEqual([
        { ...steps[1], count: 4 },
    ]);
});

test("an older draft without saved-cycle provenance keeps its revision after confirmed deletion", () => {
    const baseline = { ...editor, context: {} };
    retainPlanDraft(baseline, baseline.values, {});
    confirmPhaseDeletion(
        {
            ...editor,
            kind: "delete-phase",
            context: { planRecoveryKey: editor.recoveryKey },
        },
        { expected_revision: "1" },
        2,
    );
    const fresh = {
        ...editor,
        context: { savedStepCounts: { two: 1 } },
        values: {
            ...editor.values,
            expected_revision: "2",
            steps: JSON.stringify([steps[1]]),
        },
    };
    expect(
        restorePlanDraft(fresh, phases.slice(1)).values.expected_revision,
    ).toBe("1");
});

test("an unrelated saved prefix after deletion keeps conflicting across repeated visits", () => {
    const baseline = {
        ...editor,
        values: { ...editor.values, mode: "repeating" },
    };
    const draft = {
        ...baseline.values,
        mode: "fixed",
        steps: JSON.stringify([{ ...steps[1], count: 5 }]),
    };
    retainPlanDraft(baseline, draft, {});
    confirmPhaseDeletion(
        {
            ...editor,
            kind: "delete-phase",
            context: { planRecoveryKey: editor.recoveryKey },
        },
        { expected_revision: "1" },
        2,
    );
    const fresh = {
        ...baseline,
        context: { savedStepCounts: { two: 3 } },
        values: {
            ...baseline.values,
            expected_revision: "3",
            steps: JSON.stringify([steps[1]]),
        },
    };
    const restored = restorePlanDraft(fresh, phases.slice(1));
    expect(restored.values.expected_revision).toBe("1");
    retainPlanDraft(
        fresh,
        restored.values,
        restored.modes,
        restored.baseline,
        restored.savedStepCounts,
    );
    expect(
        restorePlanDraft(fresh, phases.slice(1)).values.expected_revision,
    ).toBe("1");
});

test.each([false, true])(
    "deleting the persisted repeating phase preserves the draft mode unless its remaining steps are empty (%s)",
    (hasUnusedPhaseStep) => {
        const a = { ...steps[0], count: 1 };
        const b = { ...steps[1], count: 5 };
        const baseline = {
            ...editor,
            context: { savedStepCounts: { one: 1 } },
            values: {
                ...editor.values,
                mode: "repeating",
                steps: JSON.stringify([a]),
                date_mode: "planned",
                date_start: "2026-11-08",
            },
        };
        const draft = {
            ...baseline.values,
            steps: JSON.stringify(hasUnusedPhaseStep ? [a, b] : [a]),
            date_start: "2030-01-01",
            cycle_interval: "2",
        };
        retainPlanDraft(baseline, draft, { repeating: draft.steps });
        confirmPhaseDeletion(
            {
                ...editor,
                kind: "delete-phase",
                context: { planRecoveryKey: editor.recoveryKey },
            },
            { expected_revision: "1" },
            2,
        );
        const fresh = {
            ...baseline,
            values: {
                ...baseline.values,
                expected_revision: "2",
                mode: "fixed",
                steps: "[]",
            },
        };
        const restored = restorePlanDraft(fresh, phases.slice(1));
        expect(restored.values.expected_revision).toBe("2");
        expect(restored.values.mode).toBe(
            hasUnusedPhaseStep ? "repeating" : "fixed",
        );
        expect(JSON.parse(restored.values.steps)).toEqual(
            hasUnusedPhaseStep ? [b] : [],
        );
        expect(restored.values.date_mode).toBe("planned");
        expect(restored.values.date_start).toBe("2030-01-01");
        expect(restored.values.cycle_interval).toBe("2");
    },
);
