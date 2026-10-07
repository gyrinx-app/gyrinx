import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mount } from "./entry";
import {
    PrintPicker,
    type PrintModel,
    type PrintPickerProps,
    type PrintWeapon,
} from "./PrintPicker";

function weapon(
    id: string,
    label: string,
    rating: number,
    slots = 1,
    ticked = true,
): PrintWeapon {
    return {
        id,
        label,
        slots,
        slotsLabel: slots === 1 ? "" : `${slots} slot${slots === 1 ? "" : "s"}`,
        rating,
        ticked,
    };
}

function model(
    id: string,
    name: string,
    baseRating: number,
    weapons: PrintWeapon[],
    ticked = true,
): PrintModel {
    return {
        id,
        name,
        profileName: "Ganger",
        rating: baseRating + weapons.reduce((sum, w) => sum + w.rating, 0),
        baseRating,
        ticked,
        hasWeapons: weapons.length > 0,
        weapons,
    };
}

const vex = () =>
    model("01VEX", "Vex", 50, [
        weapon("01LAS", "Lasgun", 15),
        weapon("01STUB", "Heavy stubber*", 40, 2),
    ]);
const sull = () => model("01SULL", "Sull", 60, [weapon("01KNIFE", "Knife", 5)]);

function setup(props: Partial<PrintPickerProps> = {}) {
    const rendered = render(
        <form>
            <PrintPicker
                marker="picker"
                slotBudget={3}
                models={[vex(), sull()]}
                {...props}
            />
        </form>,
    );
    const form = rendered.container.querySelector("form")!;
    return {
        ...rendered,
        user: userEvent.setup(),
        posted: () => {
            const data = new FormData(form);
            return {
                fighters: data.getAll("fighters"),
                weapons: data.getAll("weapons"),
            };
        },
        marker: () => new FormData(form).getAll("picker"),
        total: () =>
            screen.getByText("Crew total", { exact: false }).textContent,
    };
}

function card(name: string) {
    return screen.getByRole("checkbox", { name }).closest("label")!
        .parentElement!;
}

describe("PrintPicker", () => {
    it("posts every ticked model and weapon under the server's names", () => {
        const { posted, total } = setup();
        expect(posted()).toEqual({
            fighters: ["01VEX", "01SULL"],
            weapons: ["01LAS", "01STUB", "01KNIFE"],
        });
        // Each model's weaponless rating plus its ticked weapons.
        expect(total()).toBe("Crew total 170¢");
    });

    it("starts from the ticks it was given", () => {
        const { posted, total } = setup({
            models: [
                vex(),
                model(
                    "01SULL",
                    "Sull",
                    60,
                    [weapon("01KNIFE", "Knife", 5, 1, false)],
                    false,
                ),
            ],
        });
        expect(posted()).toEqual({
            fighters: ["01VEX"],
            weapons: ["01LAS", "01STUB"],
        });
        expect(total()).toBe("Crew total 105¢");
    });

    it("leaves an unticked model's weapons out and keeps their ticks", async () => {
        const { user, posted, total } = setup();
        const knife = screen.getByRole<HTMLInputElement>("checkbox", {
            name: /Knife/,
        });

        await user.click(screen.getByRole("checkbox", { name: "Sull" }));

        expect(knife.disabled).toBe(true);
        expect(knife.checked).toBe(true);
        expect(knife.closest("[inert]")).not.toBeNull();
        expect(posted()).toEqual({
            fighters: ["01VEX"],
            weapons: ["01LAS", "01STUB"],
        });
        expect(total()).toBe("Crew total 105¢");

        await user.click(screen.getByRole("checkbox", { name: "Sull" }));

        expect(knife.disabled).toBe(false);
        expect(posted().weapons).toEqual(["01LAS", "01STUB", "01KNIFE"]);
        expect(total()).toBe("Crew total 170¢");
    });

    it("takes an unticked weapon off the total and the post", async () => {
        const { user, posted, total } = setup();
        await user.click(
            screen.getByRole("checkbox", { name: /Heavy stubber\*/ }),
        );
        expect(posted().weapons).toEqual(["01LAS", "01KNIFE"]);
        expect(total()).toBe("Crew total 130¢");
    });

    it("counts slots against the budget and turns amber past it", async () => {
        const { user } = setup({
            models: [
                model("01VEX", "Vex", 50, [
                    weapon("01LAS", "Lasgun", 15),
                    weapon("01STUB", "Heavy stubber*", 40, 2),
                    weapon("01PIST", "Pistol", 10, 1, false),
                ]),
            ],
        });
        const count = within(card("Vex")).getByTitle(
            "Weapon slots used (3 per card)",
        );
        expect(count.textContent).toBe("3/3 slots");
        expect(count.className).toContain("text-muted");
        expect(count.className).not.toContain("text-amber-600");

        await user.click(screen.getByRole("checkbox", { name: /Pistol/ }));

        expect(count.textContent).toBe("4/3 slots");
        expect(count.className).toContain("text-amber-600");
        expect(count.className).not.toContain("text-muted");
    });

    it("draws each weapon's marks, slot words and rating", () => {
        setup();
        const row = screen
            .getByRole("checkbox", { name: /Heavy stubber\*/ })
            .closest("label")!;
        expect(within(row).getByText("2 slots")).toBeTruthy();
        expect(within(row).getByText("40¢")).toBeTruthy();
        const lasgun = screen
            .getByRole("checkbox", { name: /Lasgun/ })
            .closest("label")!;
        expect(within(lasgun).queryByText(/slot/)).toBeNull();
        expect(within(card("Vex")).getByText("105¢")).toBeTruthy();
        expect(within(card("Vex")).getByText("Ganger")).toBeTruthy();
    });

    it("toggles models and weapons from the keyboard", async () => {
        const { user, posted } = setup();
        await user.tab();
        expect(document.activeElement).toBe(
            screen.getByRole("checkbox", { name: "Vex" }),
        );
        await user.keyboard(" ");
        expect(posted().fighters).toEqual(["01SULL"]);
        // Vex's weapons are inert now, so Tab skips them to Sull.
        await user.tab();
        expect(document.activeElement).toBe(
            screen.getByRole("checkbox", { name: "Sull" }),
        );
        await user.tab();
        expect(document.activeElement).toBe(
            screen.getByRole("checkbox", { name: /Knife/ }),
        );
        await user.keyboard(" ");
        expect(posted()).toEqual({ fighters: ["01SULL"], weapons: [] });
    });

    it("gives a weaponless model no slot count and no weapon list", () => {
        setup({ models: [model("01NELL", "Nell", 30, [])] });
        const nell = card("Nell");
        expect(within(nell).queryByText(/slots/)).toBeNull();
        expect(nell.querySelector("[inert], input[name=weapons]")).toBeNull();
        expect(
            screen.getByText("Crew total", { exact: false }).textContent,
        ).toBe("Crew total 30¢");
    });

    it("still counts slots for a model whose weapons have no box", () => {
        const computed = {
            ...model("01NELL", "Nell", 30, []),
            hasWeapons: true,
        };
        setup({ models: [computed] });
        expect(within(card("Nell")).getByText("0/3 slots")).toBeTruthy();
    });

    it("draws an empty gang as no cards and a nothing total", () => {
        const { container, posted } = setup({ models: [] });
        expect(container.querySelectorAll("input[type=checkbox]")).toHaveLength(
            0,
        );
        expect(posted()).toEqual({ fighters: [], weapons: [] });
        expect(
            screen.getByText("Crew total", { exact: false }).textContent,
        ).toBe("Crew total 0¢");
    });

    it("posts the marker that says the boxes were sent", async () => {
        const { user, marker } = setup();
        expect(marker()).toEqual(["1"]);
        await user.click(screen.getByRole("checkbox", { name: "Vex" }));
        await user.click(screen.getByRole("checkbox", { name: "Sull" }));
        // Ticking nothing is still a choice the server should save.
        expect(marker()).toEqual(["1"]);
    });

    it("draws no marker when given none, as for a reader", () => {
        const { marker } = setup({ marker: "" });
        expect(marker()).toEqual([]);
    });

    it("posts the marker for a gang with no models", () => {
        const { marker } = setup({ models: [] });
        expect(marker()).toEqual(["1"]);
    });

    it("mounts over the server-drawn boxes keeping their ticks and focus", () => {
        const form = document.createElement("form");
        const host = document.createElement("div");
        form.append(host);
        document.body.append(form);
        // The server drew everything ticked; before the island loaded the
        // reader unticked Lasgun and Sull, and Lasgun's box still has focus.
        host.innerHTML = `
            <input type="hidden" name="picker" value="1">
            <input type="checkbox" name="fighters" value="01VEX" checked>
            <input type="checkbox" name="weapons" value="01LAS">
            <input type="checkbox" name="weapons" value="01STUB" checked>
            <input type="checkbox" name="fighters" value="01SULL">
            <input type="checkbox" name="weapons" value="01KNIFE" checked disabled>
        `;
        host.querySelector<HTMLInputElement>('[value="01LAS"]')!.focus();
        let unmount = () => {};
        act(() => {
            unmount = mount(host, {
                marker: "picker",
                slotBudget: 3,
                models: [vex(), sull()],
            });
        });

        const lasgun = screen.getByRole<HTMLInputElement>("checkbox", {
            name: /Lasgun/,
        });
        expect(lasgun.checked).toBe(false);
        expect(document.activeElement).toBe(lasgun);
        const knife = screen.getByRole<HTMLInputElement>("checkbox", {
            name: /Knife/,
        });
        // Sull stays unticked; the knife keeps its tick, out of the post.
        expect(knife.checked).toBe(true);
        expect(knife.disabled).toBe(true);
        const data = new FormData(form);
        expect(data.getAll("picker")).toEqual(["1"]);
        expect(data.getAll("fighters")).toEqual(["01VEX"]);
        expect(data.getAll("weapons")).toEqual(["01STUB"]);
        expect(
            screen.getByText("Crew total", { exact: false }).textContent,
        ).toBe("Crew total 90¢");
        act(() => unmount());
        form.remove();
    });

    it("focuses the model when the focused weapon's model is unticked", () => {
        const form = document.createElement("form");
        const host = document.createElement("div");
        form.append(host);
        document.body.append(form);
        // Sull unticked before the island loaded, then Tab to its knife,
        // which the server-drawn page leaves usable.
        host.innerHTML = `
            <input type="checkbox" name="fighters" value="01VEX" checked>
            <input type="checkbox" name="weapons" value="01LAS" checked>
            <input type="checkbox" name="weapons" value="01STUB" checked>
            <input type="checkbox" name="fighters" value="01SULL">
            <input type="checkbox" name="weapons" value="01KNIFE" checked>
        `;
        host.querySelector<HTMLInputElement>('[value="01KNIFE"]')!.focus();
        let unmount = () => {};
        act(() => {
            unmount = mount(host, {
                marker: "picker",
                slotBudget: 3,
                models: [vex(), sull()],
            });
        });

        const knife = screen.getByRole<HTMLInputElement>("checkbox", {
            name: /Knife/,
        });
        expect(knife.disabled).toBe(true);
        expect(document.activeElement).toBe(
            screen.getByRole("checkbox", { name: "Sull" }),
        );
        act(() => unmount());
        form.remove();
    });

    it("leaves no marker when the island fails and shows its error", () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        const form = document.createElement("form");
        const host = document.createElement("div");
        form.append(host);
        document.body.append(form);
        let unmount = () => {};
        act(() => {
            unmount = mount(host, {
                marker: "picker",
                slotBudget: 3,
                models: null as unknown as PrintModel[],
            });
        });
        expect(host.textContent).toContain("This section could not load.");
        expect(new FormData(form).getAll("picker")).toEqual([]);
        expect(new FormData(form).getAll("fighters")).toEqual([]);
        act(() => unmount());
        form.remove();
        vi.restoreAllMocks();
    });

    it("renders names as text, never as markup", () => {
        const hostile = '<img src=x onerror="alert(1)">';
        const { container } = setup({
            models: [model("01X", hostile, 0, [weapon("01Y", hostile, 0)])],
        });
        expect(container.querySelector("img")).toBeNull();
        expect(screen.getAllByText(hostile)).toHaveLength(2);
    });
});
