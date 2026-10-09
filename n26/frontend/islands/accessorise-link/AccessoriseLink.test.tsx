import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import cotton from "../../generated/cotton.json";
import { AccessoriseLink, type AccessoriseLinkProps } from "./AccessoriseLink";

const props: AccessoriseLinkProps = {
    href: "/n26/g/1/equip/?list=guns&accessorise=gun-1",
    dialogId: "n26-accessorise-gun-1",
    label: "Add accessory",
    name: "Autogun",
};

function prevented(link: HTMLElement, init: MouseEventInit = {}) {
    let defaultPrevented = false;
    document.addEventListener(
        "click",
        (event) => {
            defaultPrevented = event.defaultPrevented;
        },
        { once: true },
    );
    fireEvent.click(link, init);
    return defaultPrevented;
}

describe("AccessoriseLink", () => {
    const heard = vi.fn();

    afterEach(() => {
        window.removeEventListener("n26-dialog-open", heard);
        heard.mockReset();
    });

    it("draws the extra-small text link beside the weapon's name", () => {
        render(<AccessoriseLink {...props} />);
        const link = screen.getByRole("link", {
            name: "Add accessory to Autogun",
        });
        expect(link.getAttribute("href")).toBe(props.href);
        expect(link.className).toContain(cotton.buttonLinkBySize.xs.text);
        expect(link.className).toContain("ms-0.5 py-0!");
        expect(link.querySelector(".n26-icon-inline svg")).not.toBeNull();
        // .n26-icon-inline sizes the icon to the text; a size class would win.
        expect(link.querySelector("svg")?.getAttribute("class") ?? "").not.toMatch(
            /\bsize-/,
        );
        expect(link.querySelector("svg")?.getAttribute("stroke-width")).toBe(
            "2.5",
        );
        expect(link.textContent).toContain("Add accessory");
    });

    it("opens the panel the page is already holding", () => {
        window.addEventListener("n26-dialog-open", heard);
        render(<AccessoriseLink {...props} />);
        const link = screen.getByRole("link", {
            name: "Add accessory to Autogun",
        });

        expect(prevented(link)).toBe(true);
        expect(heard).toHaveBeenCalledOnce();
        const event = heard.mock.calls[0][0] as CustomEvent;
        expect(event.bubbles).toBe(true);
        expect(event.composed).toBe(true);
        expect(event.detail).toEqual({ id: props.dialogId, url: props.href });
    });

    it("leaves a modified click or a new-window link to the browser", () => {
        window.addEventListener("n26-dialog-open", heard);
        render(<AccessoriseLink {...props} />);
        const link = screen.getByRole("link", {
            name: "Add accessory to Autogun",
        });

        expect(prevented(link, { metaKey: true })).toBe(false);
        expect(prevented(link, { ctrlKey: true })).toBe(false);
        expect(prevented(link, { shiftKey: true })).toBe(false);
        expect(prevented(link, { button: 1 })).toBe(false);
        link.setAttribute("target", "_blank");
        expect(prevented(link)).toBe(false);
        expect(heard).not.toHaveBeenCalled();
    });
});
