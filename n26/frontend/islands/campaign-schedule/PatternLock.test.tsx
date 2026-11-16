import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ScheduleEditor } from "./ScheduleEditor";
import type { Editor, Phase } from "./types";

Element.prototype.scrollIntoView = vi.fn();
afterEach(() => sessionStorage.clear());
const steps = [
    { id: "first", phase_id: "opening", count: 2 },
    { id: "second", phase_id: "opening", count: 1 },
];
const definition = {
    phases: [{ id: "opening", details: { name: "Opening" } }],
    steps,
};
const phases = [{ id: "opening", name: "Opening", count: 0 }] as Phase[];
function editor(kind: "pattern" | "setup"): Editor {
    return {
        kind,
        heading: "Edit pattern",
        lead: "",
        context: { setupStage: 2 },
        values: {
            request_key: "new-key",
            expected_revision: "1",
            mode: "repeating",
            steps: JSON.stringify(steps),
            setup_definition: JSON.stringify(definition),
            current_number: "1",
            no_current: "on",
            date_mode: "undated",
            date_start: "",
            cycle_interval: "1",
            cycle_unit: "weeks",
        },
        errors: {},
        initialConflict: false,
        current: null,
        templates: [],
        action: `/cycles/edit/${kind}/`,
        commandHref: `/cycles/commands/${kind}/`,
        csrfToken: "fresh-token",
        recoveryKey: `pattern-lock-${kind}`,
        back: "/cycles/",
    };
}

test.each(["pattern", "setup"] as const)(
    "%s cancels a drag when navigation locks its fieldset",
    (kind) => {
        const data = editor(kind);
        const navigation = {
            pending: false,
            error: "",
            retry: vi.fn(),
            setGuard: vi.fn(),
        };
        const view = render(
            <ScheduleEditor
                editor={data}
                phases={phases}
                navigation={navigation}
            />,
        );
        const handle = screen.getByRole("button", {
            name: "Move step 1",
        });
        handle.focus();
        fireEvent.keyDown(handle, { key: " " });
        fireEvent.keyDown(handle, { key: "End" });
        expect(handle.getAttribute("aria-pressed")).toBe("true");
        const payload = () =>
            (
                view.container.querySelector(
                    `input[name="${kind === "setup" ? "setup_definition" : "steps"}"]`,
                ) as HTMLInputElement
            ).value;
        const before = payload();
        view.rerender(
            <ScheduleEditor
                editor={data}
                phases={phases}
                navigation={{ ...navigation, pending: true }}
            />,
        );
        expect(handle.hasAttribute("disabled")).toBe(true);
        expect(handle.getAttribute("aria-pressed")).toBe("false");
        expect(
            view.container.querySelector("[data-reorder-active=true]"),
        ).toBeNull();
        fireEvent.keyDown(handle, { key: "Enter" });
        expect(payload()).toBe(before);
        view.rerender(
            <ScheduleEditor
                editor={data}
                phases={phases}
                navigation={navigation}
            />,
        );
        handle.focus();
        fireEvent.keyDown(handle, { key: " " });
        fireEvent.keyDown(handle, { key: "End" });
        fireEvent.keyDown(handle, { key: "Enter" });
        const changed = JSON.parse(payload());
        expect(
            (kind === "setup" ? changed.steps : changed).map(
                (step: { id: string }) => step.id,
            ),
        ).toEqual(["second", "first"]);
    },
);
