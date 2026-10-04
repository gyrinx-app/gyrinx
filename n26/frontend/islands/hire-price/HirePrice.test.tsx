import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mount } from "./entry";
import { HirePrice, type HirePriceProps } from "./HirePrice";

const props: HirePriceProps = {
    field: "paid",
    quoted: 55,
    label: "Ganger",
    min: 0,
    max: 100000,
    id: "hire-paid",
};

describe("HirePrice", () => {
    it("starts at the quote and names the box", () => {
        render(<HirePrice {...props} />);
        const box = screen.getByRole("spinbutton", {
            name: "Price for Ganger",
        });
        expect(box.getAttribute("name")).toBe("paid");
        expect(box.getAttribute("value")).toBe("55");
        expect(box.getAttribute("min")).toBe("0");
        expect(box.getAttribute("max")).toBe("100000");
        expect(document.querySelector("[title]")).toBeNull();
    });

    it("shows how far a higher price sits from the quote", () => {
        render(<HirePrice {...props} />);
        fireEvent.change(screen.getByRole("spinbutton"), {
            target: { value: "80" },
        });
        const delta = document.querySelector("[title]");
        expect(delta?.textContent).toBe("+25¢");
        expect(delta?.getAttribute("title")).toBe("Listed at 55¢");
    });

    it("shows how far a lower price sits from the quote", () => {
        render(<HirePrice {...props} />);
        fireEvent.change(screen.getByRole("spinbutton"), {
            target: { value: "30" },
        });
        expect(document.querySelector("[title]")?.textContent).toBe("−25¢");
    });

    it("says nothing when the box is cleared or returned to the quote", () => {
        render(<HirePrice {...props} />);
        const box = screen.getByRole("spinbutton");
        fireEvent.change(box, { target: { value: "" } });
        expect(document.querySelector("[title]")).toBeNull();
        fireEvent.change(box, { target: { value: "55" } });
        expect(document.querySelector("[title]")).toBeNull();
    });
});

describe("mounting over the server-drawn box", () => {
    it("keeps a figure typed before the module loaded", () => {
        const host = document.createElement("div");
        host.id = "hire-host";
        host.innerHTML = '<input type="number" name="paid" value="55">';
        document.body.appendChild(host);
        (host.querySelector("input") as HTMLInputElement).value = "30";

        let unmount: () => void = () => {};
        act(() => {
            unmount = mount(host, props);
        });

        const box = host.querySelector<HTMLInputElement>('input[name="paid"]');
        expect(box?.value).toBe("30");
        expect(host.textContent).toContain("−25¢");
        act(() => unmount());
        host.remove();
    });

    it("keeps an emptied box empty", () => {
        render(<HirePrice {...props} initial="" />);
        expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe(
            "",
        );
    });
});
