import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
    ReorderScope,
    ReorderItem,
    ReorderDropLine,
    type ReorderMove,
} from "./Reorder";

const targets = [
    { id: "start", label: "Start of first group" },
    { id: "after-a", label: "After Alpha" },
    { id: "after-b", label: "After Bravo" },
    { id: "empty", label: "Start of empty group" },
];
function Example({
    disabled = false,
    onMove = vi.fn(),
    revision = 0,
}: {
    disabled?: boolean;
    onMove?: (move: ReorderMove) => void;
    revision?: number;
}) {
    const [order, setOrder] = useState(["a", "b"]);
    return (
        <ReorderScope
            disabled={disabled}
            targets={targets}
            sources={[
                {
                    id: "a",
                    label: `Alpha ${revision}`,
                    origin: "start",
                    targets: ["after-b", "empty"],
                },
                {
                    id: "b",
                    label: "Bravo",
                    origin: "after-a",
                    targets: ["start", "empty"],
                },
                { id: "locked", label: "Locked", origin: "start", targets: [] },
            ]}
            onMove={(move) => {
                onMove(move);
                setOrder([...order].reverse());
            }}
        >
            {order.map((id) => (
                <ReorderItem id={id} key={id}>
                    {({ ref, handle }) => (
                        <div ref={ref} data-testid={id}>
                            {handle}
                            <input aria-label={`Name ${id}`} />
                            <a href="#details">Details {id}</a>
                        </div>
                    )}
                </ReorderItem>
            ))}
            <ReorderItem id="locked">
                {({ ref, handle }) => <div ref={ref}>{handle}Locked</div>}
            </ReorderItem>
            {targets.map((target) => (
                <ReorderDropLine id={target.id} key={target.id} />
            ))}
        </ReorderScope>
    );
}
function key(
    key: string,
    handle = screen.getByRole("button", { name: "Move Alpha 0" }),
) {
    fireEvent.keyDown(handle, { key });
}

describe("controlled reordering", () => {
    Element.prototype.scrollIntoView = vi.fn();
    it("uses stable insertion IDs and never changes order before drop", () => {
        const onMove = vi.fn();
        render(<Example onMove={onMove} />);
        const handle = screen.getByRole("button", { name: "Move Alpha 0" });
        handle.focus();
        key(" ");
        key("ArrowDown");
        expect(screen.getByRole("status").textContent).toBe("After Bravo");
        expect(
            screen.getAllByTestId(/a|b/).map((node) => node.dataset.testid),
        ).toEqual(["a", "b"]);
        expect(onMove).not.toHaveBeenCalled();
        key(" ");
        expect(onMove).toHaveBeenCalledExactlyOnceWith({
            itemId: "a",
            targetId: "after-b",
        });
        expect(document.activeElement).toBe(handle);
    });
    it("skips forbidden/no-op gaps and supports an empty destination", () => {
        const onMove = vi.fn();
        render(<Example onMove={onMove} />);
        key("Enter");
        key("End");
        expect(screen.getByRole("status").textContent).toBe(
            "Start of empty group",
        );
        key("Enter");
        expect(onMove).toHaveBeenCalledExactlyOnceWith({
            itemId: "a",
            targetId: "empty",
        });
    });
    it.each(["Escape", "Tab"])(
        "cancels with %s without committing",
        (cancel) => {
            const onMove = vi.fn();
            render(<Example onMove={onMove} />);
            key(" ");
            key("ArrowDown");
            key(cancel);
            expect(onMove).not.toHaveBeenCalled();
            expect(screen.getByRole("status").textContent).toContain(
                "cancelled",
            );
        },
    );
    it("lets Tab leave a cancelled keyboard move", async () => {
        const user = userEvent.setup();
        const onMove = vi.fn();
        render(<Example onMove={onMove} />);
        const handle = screen.getByRole("button", { name: "Move Alpha 0" });
        handle.focus();
        await user.keyboard(" {ArrowDown}");
        await user.tab();
        await new Promise((resolve) => setTimeout(resolve, 30));
        expect(document.activeElement).toBe(screen.getByLabelText("Name a"));
        expect(onMove).not.toHaveBeenCalled();
    });
    it("lets clicking a field leave a cancelled keyboard move", async () => {
        const user = userEvent.setup();
        render(<Example />);
        screen.getByRole("button", { name: "Move Alpha 0" }).focus();
        await user.keyboard(" {ArrowDown}");
        const input = screen.getByLabelText("Name b");
        await user.click(input);
        await new Promise((resolve) => setTimeout(resolve, 30));
        expect(document.activeElement).toBe(input);
    });
    it("does not submit when picked up and dropped in place", () => {
        const onMove = vi.fn();
        render(<Example onMove={onMove} />);
        key(" ");
        key(" ");
        expect(onMove).not.toHaveBeenCalled();
    });
    it("cancels when the owner disables or replaces the current baseline", () => {
        const onMove = vi.fn();
        const view = render(<Example onMove={onMove} />);
        key(" ");
        key("ArrowDown");
        view.rerender(<Example onMove={onMove} revision={1} />);
        expect(screen.getByRole("status").textContent).toContain("cancelled");
        const handle = screen.getByRole("button", { name: "Move Alpha 1" });
        key(" ", handle);
        key("ArrowDown", handle);
        view.rerender(<Example onMove={onMove} revision={1} disabled />);
        expect(onMove).not.toHaveBeenCalled();
        expect(handle.hasAttribute("disabled")).toBe(true);
    });
    it("keeps input, links and locked rows out of drag activation", () => {
        render(<Example />);
        expect(
            screen.queryByRole("button", { name: "Move Locked" }),
        ).toBeNull();
        fireEvent.keyDown(screen.getByLabelText("Name a"), { key: " " });
        expect(screen.getByRole("status").textContent).toBe("");
        expect(
            screen
                .getByRole("link", { name: "Details a" })
                .getAttribute("href"),
        ).toBe("#details");
    });
});
