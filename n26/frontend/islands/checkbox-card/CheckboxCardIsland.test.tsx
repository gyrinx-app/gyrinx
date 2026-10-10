import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import cotton from "../../generated/cotton.json";
import {
    CheckboxCardIsland,
    type CheckboxCardIslandProps,
} from "./CheckboxCardIsland";
import { mount } from "./entry";

const props: CheckboxCardIslandProps = {
    name: "open",
    value: "table-1",
    checked: false,
    label: "Goliath Territories",
    description: "D6 · 6 territories",
    className: "h-full",
    meta: "",
    items: [],
};

const withItems: CheckboxCardIslandProps = {
    ...props,
    name: "fighters",
    value: "vex",
    label: "Vex",
    description: "Escher Ganger",
    meta: "85¢",
    items: [
        {
            name: "weapons",
            value: "lasgun",
            label: "Lasgun",
            checked: true,
            meta: "15¢",
        },
        {
            name: "weapons",
            value: "stiletto",
            label: "Stiletto knife",
            checked: false,
            meta: "20¢",
        },
    ],
};

const fallback = `
<div data-checkbox-card class="rounded-box">
  <label>
    <input type="checkbox" name="open" value="table-1">
    <span>Goliath Territories</span>
  </label>
</div>`;

const fallbackWithItems = `
<div data-checkbox-card class="rounded-box">
  <label>
    <input type="checkbox" name="fighters" value="vex">
    <span>Vex</span>
  </label>
  <div data-checkbox-body>
    <label><input type="checkbox" name="weapons" value="lasgun" checked> Lasgun</label>
    <label><input type="checkbox" name="weapons" value="stiletto"> Stiletto knife</label>
  </div>
</div>`;

function mountedHost(html: string) {
    const form = document.createElement("form");
    const host = document.createElement("div");
    host.innerHTML = html;
    form.appendChild(host);
    document.body.appendChild(form);
    return { form, host };
}

afterEach(() => {
    document.body.innerHTML = "";
});

describe("CheckboxCardIsland", () => {
    it("posts name and value and draws the cotton card", async () => {
        const user = userEvent.setup();
        const { container } = render(
            <form>
                <CheckboxCardIsland {...props} />
            </form>,
        );
        const form = container.querySelector("form")!;
        const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Goliath Territories",
        });
        const root = checkbox.closest(
            `.${cotton.checkboxCard.root.split(" ")[0]}`,
        )!;

        expect(checkbox.name).toBe("open");
        expect(checkbox.value).toBe("table-1");
        expect(root.className).toContain(
            cotton.checkboxCard.selection.unchecked,
        );
        expect(root.className).toContain("h-full");
        expect(new FormData(form).getAll("open")).toEqual([]);
        expect(
            document.getElementById(checkbox.getAttribute("aria-describedby")!)
                ?.textContent,
        ).toBe("D6 · 6 territories");

        await user.click(checkbox);
        expect(checkbox.checked).toBe(true);
        expect(root.className).toContain(cotton.checkboxCard.selection.checked);
        expect(new FormData(form).getAll("open")).toEqual(["table-1"]);
    });

    it("draws a label as text", () => {
        const label = '<img src=x onerror="alert(1)">';
        render(<CheckboxCardIsland {...props} label={label} description="" />);
        expect(screen.getByText(label)).toBeTruthy();
        expect(document.querySelector("img")).toBeNull();
    });

    it("makes the nested ticks inert while the card is clear, and still posts them", async () => {
        const user = userEvent.setup();
        const { container } = render(
            <form>
                <CheckboxCardIsland {...withItems} />
            </form>,
        );
        const form = container.querySelector("form")!;
        const card = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Vex",
        });
        const stiletto = screen.getByRole<HTMLInputElement>("checkbox", {
            name: /Stiletto knife/,
            hidden: true,
        });

        expect(form.textContent).toContain("85¢");
        expect(form.textContent).toContain("20¢");
        expect(stiletto.closest("[inert]")).not.toBeNull();
        expect(new FormData(form).getAll("weapons")).toEqual(["lasgun"]);

        await user.click(card);
        expect(stiletto.closest("[inert]")).toBeNull();
        await user.click(stiletto);
        expect(new FormData(form).getAll("weapons")).toEqual([
            "lasgun",
            "stiletto",
        ]);

        await user.click(card);
        expect(stiletto.closest("[inert]")).not.toBeNull();
        expect(stiletto.checked).toBe(true);
    });
});

describe("focus on a nested tick before mounting", () => {
    it.each([
        [true, "Lasgun"],
        [false, "Vex"],
    ])("card ticked %s puts focus on %s", (ticked, focused) => {
        const { host } = mountedHost(fallbackWithItems);
        host.querySelector<HTMLInputElement>(
            "input[name='fighters']",
        )!.checked = ticked;
        host.querySelector<HTMLInputElement>("input[value='lasgun']")!.focus();

        let unmount = () => {};
        act(() => {
            unmount = mount(host, withItems);
        });

        const expected = screen.getByRole("checkbox", {
            name: new RegExp(focused),
            hidden: true,
        });
        expect(document.activeElement).toBe(expected);
        act(() => unmount());
    });
});

describe("mounting over the server-drawn card", () => {
    it("replaces the server-drawn box and posts it once", async () => {
        const user = userEvent.setup();
        const { form, host } = mountedHost(fallback);
        let unmount = () => {};
        act(() => {
            unmount = mount(host, props);
        });
        const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Goliath Territories",
        });

        expect(form.querySelectorAll("input[name='open']")).toHaveLength(1);
        expect(form.querySelector("[data-checkbox-card]")).toBeNull();
        expect(new FormData(form).getAll("open")).toEqual([]);

        await user.click(checkbox);
        expect(checkbox.checked).toBe(true);
        expect(new FormData(form).getAll("open")).toEqual(["table-1"]);
        act(() => unmount());
    });

    it("reads the fallback ticks when they differ from the props", () => {
        const { form, host } = mountedHost(fallbackWithItems);
        const card = host.querySelector<HTMLInputElement>(
            "input[name='fighters']",
        )!;
        card.checked = true;
        card.focus();
        host.querySelector<HTMLInputElement>("input[value='lasgun']")!.checked =
            false;
        host.querySelector<HTMLInputElement>(
            "input[value='stiletto']",
        )!.checked = true;

        let unmount = () => {};
        act(() => {
            unmount = mount(host, withItems);
        });

        const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Vex",
        });
        expect(checkbox.checked).toBe(true);
        expect(document.activeElement).toBe(checkbox);
        expect(new FormData(form).getAll("weapons")).toEqual(["stiletto"]);
        expect(form.querySelectorAll("input[name='weapons']")).toHaveLength(2);
        act(() => unmount());
    });
});
