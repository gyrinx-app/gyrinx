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
};

const fallback = `
<div data-checkbox-card class="rounded-box">
  <label>
    <input type="checkbox" name="open" value="table-1">
    <span>Goliath Territories</span>
  </label>
</div>`;

function mountedHost(
    html = fallback,
    initial?: Partial<CheckboxCardIslandProps>,
) {
    const form = document.createElement("form");
    const host = document.createElement("div");
    host.innerHTML = html;
    form.appendChild(host);
    document.body.appendChild(form);
    let unmount = () => {};
    act(() => {
        unmount = mount(host, { ...props, ...initial });
    });
    return {
        form,
        host,
        cleanup() {
            act(() => unmount());
            form.remove();
        },
    };
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
});

describe("mounting over the server-drawn card", () => {
    it("replaces the server-drawn box and posts it once", async () => {
        const user = userEvent.setup();
        const { form, cleanup } = mountedHost();
        const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Goliath Territories",
        });

        expect(form.querySelectorAll("input[name='open']")).toHaveLength(1);
        expect(form.querySelector("[data-checkbox-card]")).toBeNull();
        expect(new FormData(form).getAll("open")).toEqual([]);

        await user.click(checkbox);
        expect(checkbox.checked).toBe(true);
        expect(new FormData(form).getAll("open")).toEqual(["table-1"]);
        cleanup();
    });

    it("reads the fallback tick when it differs from the props", () => {
        const form = document.createElement("form");
        const host = document.createElement("div");
        host.innerHTML = fallback;
        form.appendChild(host);
        document.body.appendChild(form);
        const original =
            host.querySelector<HTMLInputElement>("input[name='open']")!;
        original.checked = true;
        original.focus();

        let unmount = () => {};
        act(() => {
            unmount = mount(host, props);
        });

        const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Goliath Territories",
        });
        expect(checkbox.checked).toBe(true);
        expect(document.activeElement).toBe(checkbox);
        expect(checkbox.closest("div")?.className).toContain(
            cotton.checkboxCard.selection.checked,
        );
        act(() => unmount());
        form.remove();
    });
});
