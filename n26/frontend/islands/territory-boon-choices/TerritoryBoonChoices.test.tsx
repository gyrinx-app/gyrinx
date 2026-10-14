import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, afterEach } from "vitest";
import {
    TerritoryBoonChoices,
    type TerritoryBoonChoicesProps,
} from "./TerritoryBoonChoices";
import { saveTerritoryBoons, navigateToSavedTerritory } from "./entry";

const props: TerritoryBoonChoicesProps = {
    saveUrl: "/territory/boons/",
    csrfToken: "csrf",
    snapshot: "snapshot",
    effects: [],
    groups: [
        {
            key: "production",
            label: "Production",
            selected: "income",
            options: [
                {
                    value: "income",
                    label: "Income",
                    description: "Use the territory income.",
                    disabled: false,
                },
                {
                    value: "supplies",
                    label: "Supplies",
                    description: "Resolve the supplies manually.",
                    disabled: false,
                },
            ],
        },
        {
            key: "support",
            label: "Support",
            selected: "rep",
            options: [
                {
                    value: "rep",
                    label: "Reputation",
                    description: "",
                    disabled: false,
                },
                {
                    value: "medic",
                    label: "Medic",
                    description: "",
                    disabled: false,
                },
            ],
        },
    ],
};
afterEach(() => vi.unstubAllGlobals());

describe("Territory boon choices", () => {
    it("shows the saved selections and reveals one Save only while choices differ", async () => {
        const user = userEvent.setup();
        render(<TerritoryBoonChoices {...props} onSave={vi.fn()} />);
        expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
        expect(
            (screen.getByRole("radio", { name: "Income" }) as HTMLInputElement)
                .checked,
        ).toBe(true);
        expect(
            screen
                .getByRole("radio", { name: "Income" })
                .getAttribute("aria-describedby"),
        ).toBeTruthy();
        await user.click(screen.getByRole("radio", { name: "Supplies" }));
        expect(screen.getAllByRole("button", { name: "Save" })).toHaveLength(1);
        await user.click(screen.getByRole("radio", { name: "Income" }));
        expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    });
    it("saves changed groups together and disables controls while saving", async () => {
        const user = userEvent.setup();
        const save = vi.fn(() => new Promise<void>(() => {}));
        render(<TerritoryBoonChoices {...props} onSave={save} />);
        await user.click(screen.getByRole("radio", { name: "Supplies" }));
        await user.click(screen.getByRole("radio", { name: "Medic" }));
        await user.click(screen.getByRole("button", { name: "Save" }));
        expect(save).toHaveBeenCalledWith({
            production: "supplies",
            support: "medic",
        });
        expect(
            (
                screen.getByRole("button", {
                    name: "Saving…",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
        expect(
            (
                screen.getByRole("group", {
                    name: "Production",
                }) as HTMLFieldSetElement
            ).disabled,
        ).toBe(true);
    });
    it("keeps a failed draft for retry and submits only the changed choice", async () => {
        const user = userEvent.setup();
        const save = vi
            .fn()
            .mockRejectedValue(
                new Error(
                    "The boon choices changed. Reload this page before saving.",
                ),
            );
        render(<TerritoryBoonChoices {...props} onSave={save} />);
        await user.click(screen.getByRole("radio", { name: "Supplies" }));
        await user.click(screen.getByRole("button", { name: "Save" }));
        expect((await screen.findByRole("alert")).textContent).toContain(
            "Reload this page",
        );
        expect(
            (
                screen.getByRole("radio", {
                    name: "Supplies",
                }) as HTMLInputElement
            ).checked,
        ).toBe(true);
        expect(save).toHaveBeenCalledWith({ production: "supplies" });
        await waitFor(() =>
            expect(
                (
                    screen.getByRole("button", {
                        name: "Save",
                    }) as HTMLButtonElement
                ).disabled,
            ).toBe(false),
        );
    });
    it("keeps groups independent and supports native keyboard selection", async () => {
        const user = userEvent.setup();
        render(<TerritoryBoonChoices {...props} onSave={vi.fn()} />);
        const production = within(
            screen.getByRole("group", { name: "Production" }),
        );
        production.getByRole("radio", { name: "Income" }).focus();
        await user.keyboard("{ArrowDown}");
        expect(
            (
                production.getByRole("radio", {
                    name: "Supplies",
                }) as HTMLInputElement
            ).checked,
        ).toBe(true);
        expect(
            (
                screen.getByRole("radio", {
                    name: "Reputation",
                }) as HTMLInputElement
            ).checked,
        ).toBe(true);
    });
    it("preserves the server's error and sends the snapshot and CSRF token", async () => {
        const fetch = vi.fn().mockResolvedValue({
            ok: false,
            headers: new Headers({ "Content-Type": "application/json" }),
            json: async () => ({ error: "The boon choices changed." }),
        });
        vi.stubGlobal("fetch", fetch);
        await expect(
            saveTerritoryBoons(props, { production: "supplies" }),
        ).rejects.toThrow("The boon choices changed.");
        const [, request] = fetch.mock.calls[0];
        expect(request.headers["X-CSRFToken"]).toBe("csrf");
        expect(request.body.get("snapshot")).toBe("snapshot");
        expect(request.body.get("choice_production")).toBe("supplies");
    });
    it("rejects an unexpected HTML response without losing the draft", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({
                ok: true,
                headers: new Headers({ "Content-Type": "text/html" }),
            }),
        );
        await expect(
            saveTerritoryBoons(props, { production: "supplies" }),
        ).rejects.toThrow("Reload the page");
    });
});

it("reloads the saved territory when only its section anchor changes", () => {
    const reload = vi.fn();
    const assign = vi.fn();
    const replaceState = vi.fn();
    vi.stubGlobal("window", {
        location: { pathname: "/territory/", search: "", reload, assign },
        history: { replaceState },
    });
    navigateToSavedTerritory(
        new URL("http://localhost/territory/#n26-territory-boons"),
    );
    expect(replaceState).toHaveBeenCalledWith(
        null,
        "",
        "http://localhost/territory/#n26-territory-boons",
    );
    expect(reload).toHaveBeenCalledOnce();
    expect(assign).not.toHaveBeenCalled();
});
