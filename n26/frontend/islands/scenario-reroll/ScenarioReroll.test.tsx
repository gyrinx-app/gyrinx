import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
    ScenarioReroll,
    rerollNavigation,
    type ScenarioRerollProps,
} from "./ScenarioReroll";

const props: ScenarioRerollProps = {
    title: "Reroll side job 1",
    action: "/n26/scenario/",
    cancelUrl: "/n26/scenario/?side_job=escher-3#scenario",
    fields: [
        ["side_job", "escher-3"],
        ["reroll", "side_job"],
    ],
    sets: [
        { value: "general", label: "General side jobs" },
        { value: "escher", label: "Escher side jobs" },
    ],
    set: "escher",
};
beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn(function (
        this: HTMLDialogElement,
    ) {
        this.setAttribute("open", "");
    });
    HTMLDialogElement.prototype.close = vi.fn(function (
        this: HTMLDialogElement,
    ) {
        this.removeAttribute("open");
    });
});
afterEach(() => vi.restoreAllMocks());

it("asks which set to roll on, starting with the side job's own", () => {
    const { container } = render(<ScenarioReroll {...props} />);
    screen.getByRole("dialog", { name: "Reroll side job 1" });
    const menu = screen.getByLabelText("Side job set");
    expect(menu).toHaveProperty("value", "escher");
    fireEvent.change(menu, { target: { value: "general" } });
    const form = container.ownerDocument.querySelector("dialog form")!;
    const data = new FormData(form as HTMLFormElement);
    expect(data.get("side_job")).toBe("escher-3");
    expect(data.get("reroll")).toBe("side_job");
    expect(data.get("reroll_set")).toBe("general");
    expect(
        screen.getByRole("link", { name: "Cancel" }).getAttribute("href"),
    ).toBe(props.cancelUrl);
});

it("goes back to the scenario when dismissed", () => {
    const go = vi
        .spyOn(rerollNavigation, "assign")
        .mockImplementation(() => {});
    render(<ScenarioReroll {...props} />);
    fireEvent(screen.getByRole("dialog"), new Event("cancel"));
    expect(go).toHaveBeenCalledWith(props.cancelUrl);
});
