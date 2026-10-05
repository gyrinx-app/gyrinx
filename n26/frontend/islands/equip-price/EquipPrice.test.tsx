import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mount } from "./entry";
import { EquipPrice, type EquipPriceProps } from "./EquipPrice";

const props: EquipPriceProps = {
    field: "sword:price",
    quoted: 35,
    label: "Sword",
    min: 0,
    max: 100000,
};

describe("EquipPrice", () => {
    it("starts at the quote and names the box", () => {
        render(<EquipPrice {...props} />);
        const box = screen.getByRole("spinbutton", { name: "Price for Sword" });
        expect(box.getAttribute("name")).toBe("sword:price");
        expect(box.getAttribute("value")).toBe("35");
        expect(box.getAttribute("min")).toBe("0");
        expect(box.getAttribute("max")).toBe("100000");
        expect(document.querySelector("[title]")).toBeNull();
    });

    it("shows a higher price to the left of the box", () => {
        render(<EquipPrice {...props} />);
        fireEvent.change(screen.getByRole("spinbutton"), {
            target: { value: "50" },
        });
        const box = screen.getByRole("spinbutton");
        const delta = document.querySelector("[title]");
        expect(delta?.textContent).toBe("+15¢");
        expect(delta?.getAttribute("title")).toBe("Listed at 35¢");
        expect(
            delta!.compareDocumentPosition(box) &
                Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
    });

    it("shows a lower price to the left of the box", () => {
        render(<EquipPrice {...props} />);
        fireEvent.change(screen.getByRole("spinbutton"), {
            target: { value: "8" },
        });
        expect(document.querySelector("[title]")?.textContent).toBe("−27¢");
    });

    it("says nothing when the box is cleared or returned to the quote", () => {
        render(<EquipPrice {...props} />);
        const box = screen.getByRole("spinbutton");
        fireEvent.change(box, { target: { value: "" } });
        expect(document.querySelector("[title]")).toBeNull();
        fireEvent.change(box, { target: { value: "35" } });
        expect(document.querySelector("[title]")).toBeNull();
    });

    it("lets gear priced below nothing open at that price", () => {
        render(
            <EquipPrice
                {...props}
                field="brittle:price"
                quoted={-10}
                label="Reduced bone density"
                min={-10}
            />,
        );
        const box = screen.getByRole("spinbutton", {
            name: "Price for Reduced bone density",
        });
        expect(box.getAttribute("value")).toBe("-10");
        expect(box.getAttribute("min")).toBe("-10");
        expect(document.querySelector("[title]")).toBeNull();
        fireEvent.change(box, { target: { value: "-5" } });
        expect(document.querySelector("[title]")?.textContent).toBe("+5¢");
    });
});

describe("mounting over the server-drawn box", () => {
    it("keeps a figure typed before the module loaded", () => {
        const host = document.createElement("div");
        host.innerHTML = '<input type="number" name="sword:price" value="35">';
        document.body.appendChild(host);
        (host.querySelector("input") as HTMLInputElement).value = "8";

        let unmount: () => void = () => {};
        act(() => {
            unmount = mount(host, props);
        });

        const box = host.querySelector<HTMLInputElement>(
            'input[name="sword:price"]',
        );
        expect(box?.value).toBe("8");
        expect(host.textContent).toContain("−27¢");
        expect(host.textContent?.indexOf("−27¢")).toBeLessThan(
            host.innerHTML.indexOf("sword:price"),
        );
        act(() => unmount());
        host.remove();
    });

    it("keeps an emptied box empty", () => {
        render(<EquipPrice {...props} initial="" />);
        expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe(
            "",
        );
    });
});
