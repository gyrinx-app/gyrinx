import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
    ModifierKindPicker,
    type ModifierKindPickerProps,
} from "./ModifierKindPicker";

const props: ModifierKindPickerProps = {
    submitLabel: "Continue →",
    served: {
        scope: "targets_model",
        effect: "ef_adds",
    },
    scope: {
        name: "scope_kind",
        legend: "Who it reaches",
        cards: [
            {
                value: "targets_model",
                label: "The model carrying it",
                description: "Reaches one model.",
                example: "A fighter gains a subtype.",
                produces: "model",
                checked: true,
                disabled: false,
                reason: "",
                deprecated: false,
            },
            {
                value: "targets_weapons",
                label: "The model's weapons",
                description: "Reaches every weapon.",
                example: "Every weapon gains a trait.",
                produces: "weapon_profile",
                checked: false,
                disabled: false,
                reason: "",
                deprecated: true,
            },
        ],
    },
    effect: {
        name: "effect_kind",
        legend: "What it does",
        cards: [
            {
                value: "ef_adds",
                label: "Adds something",
                description: "Adds one thing.",
                example: "Adds a subtype.",
                accepts: ["model"],
                checked: true,
            },
            {
                value: "ef_changes_stat",
                label: "Changes a stat",
                description: "Changes one stat.",
                example: "Improves Strength.",
                accepts: ["model", "weapon_profile"],
                checked: false,
            },
        ],
    },
};

function setup(overrides: Partial<ModifierKindPickerProps> = {}) {
    const submit = vi.fn((event) => event.preventDefault());
    const componentProps = { ...props, ...overrides };
    const rendered = render(
        <form onSubmit={submit}>
            <ModifierKindPicker {...componentProps} />
        </form>,
    );
    const form = rendered.container.querySelector("form")!;
    return {
        ...rendered,
        form,
        data: () => new FormData(form),
        submit,
        user: userEvent.setup(),
    };
}

describe("modifier kind picker", () => {
    it("keeps the existing GET field names and disables the served pair", async () => {
        const { user, data } = setup();
        const button = screen.getByRole<HTMLButtonElement>("button", {
            name: "Continue →",
        });

        expect(data().get("scope_kind")).toBe("targets_model");
        expect(data().get("effect_kind")).toBe("ef_adds");
        expect(button.disabled).toBe(true);

        await user.click(screen.getByRole("radio", { name: /Changes a stat/ }));
        expect(data().get("effect_kind")).toBe("ef_changes_stat");
        expect(button.disabled).toBe(false);

        await user.click(screen.getByRole("radio", { name: /Adds something/ }));
        expect(button.disabled).toBe(true);
    });

    it("greys incompatible effects and clears one already selected", async () => {
        const { user, data } = setup();

        await user.click(
            screen.getByRole("radio", { name: /The model's weapons/ }),
        );

        const incompatible = screen.getByRole("radio", {
            name: /Adds something/,
        });
        expect(
            incompatible
                .closest("[aria-disabled]")
                ?.getAttribute("aria-disabled"),
        ).toBe("true");
        expect(incompatible.hasAttribute("disabled")).toBe(false);
        expect(data().get("effect_kind")).toBeNull();
    });

    it("clears an incompatible pair when the island first mounts", () => {
        const incompatible = structuredClone(props);
        incompatible.scope.cards[0].checked = false;
        incompatible.scope.cards[1].checked = true;

        const { data } = setup(incompatible);

        expect(data().get("scope_kind")).toBe("targets_weapons");
        expect(data().get("effect_kind")).toBeNull();
    });

    it("keeps carrier-blocked scopes disabled with their reason", () => {
        const blocked = structuredClone(props);
        blocked.scope.cards[1].disabled = true;
        blocked.scope.cards[1].reason =
            "A special rule is never fitted to a weapon.";

        setup(blocked);

        const radio = screen.getByRole<HTMLInputElement>("radio", {
            name: /The model's weapons/,
        });
        expect(radio.disabled).toBe(true);
        expect(
            screen.getByText("A special rule is never fitted to a weapon."),
        ).toBeTruthy();
    });

    it("renders prepared text as text and keeps the deprecated marker", () => {
        const safe = structuredClone(props);
        safe.scope.cards[0].label = "<strong>Model</strong>";

        const { container } = setup(safe);

        expect(screen.getByText("<strong>Model</strong>")).toBeTruthy();
        expect(container.querySelector("strong")).toBeNull();
        expect(screen.getByText("Deprecated")).toBeTruthy();
    });
});
