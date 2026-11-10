import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Dialog } from "./index";

test("a modal adds no child to the page spacing container and restores trigger focus", () => {
    HTMLDialogElement.prototype.showModal = vi.fn();
    HTMLDialogElement.prototype.close = vi.fn();
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();
    const view = render(
        <div className="space-y-4">
            <p>Timeline</p>
            <Dialog title="Edit cycle" onSubmit={vi.fn()} onDismiss={vi.fn()}>
                Dates
            </Dialog>
        </div>,
    );
    const dialog = screen.getByRole("dialog", { hidden: true });
    expect(dialog.parentElement).toBe(document.body);
    expect(view.container.querySelector(".space-y-4")?.childElementCount).toBe(
        1,
    );
    view.unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
});
