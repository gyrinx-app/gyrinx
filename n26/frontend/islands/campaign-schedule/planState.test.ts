import { afterEach, expect, test } from "vitest";
import { clearPlanDraft, retainPlanDraft, restorePlanDraft } from "./planState";
import type { Editor, Phase } from "./types";

const steps = [
    { id: "one", phase_id: "opening", count: 3 },
    { id: "two", phase_id: "downtime", count: 1 },
];
const phases = [{ id: "opening" }, { id: "downtime" }] as Phase[];
const editor: Editor = {
    heading: "Phase and schedule settings",
    lead: "",
    context: {},
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
