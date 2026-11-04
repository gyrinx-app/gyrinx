import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StagedContent, type StagedContentProps } from "./StagedContent";

const row = {
    pk: "one",
    label: "Lasgun",
    qualifier: "House",
    url: "/weapon/one/",
    notes: ["Basic"],
    deleteUrl: "/weapon/one/delete/",
};
const props: StagedContentProps = {
    groups: [
        {
            label: "Weapons",
            model: "weapon",
            rows: [row, { ...row, pk: "two", qualifier: "Trading post" }],
        },
        {
            label: "Skills",
            model: "skill",
            rows: [
                {
                    ...row,
                    label: "Parry",
                    qualifier: "",
                    url: "",
                    deleteUrl: "",
                },
            ],
        },
    ],
    csrfToken: "token",
    action: "/staged/put-live/",
    singleAction: "/staged/",
    selected: [],
    errors: [],
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

it("starts with nothing selected and release disabled", () => {
    render(<StagedContent {...props} />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    expect(
        screen
            .getAllByRole<HTMLInputElement>("checkbox")
            .every((box) => !box.checked),
    ).toBe(true);
    expect(
        screen.getByRole<HTMLButtonElement>("button", {
            name: "Put selected live",
        }).disabled,
    ).toBe(true);
    expect(screen.queryByRole("checkbox", { name: /all/i })).toBeNull();
    expect(screen.queryByText("Put everything live")).toBeNull();
});

it("selects all loaded entries, allows exclusions and clears the selection", async () => {
    const user = userEvent.setup();
    render(<StagedContent {...props} />);
    await user.click(screen.getByRole("button", { name: "Select all" }));
    expect(
        screen
            .getAllByRole<HTMLInputElement>("checkbox")
            .every((box) => box.checked),
    ).toBe(true);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("3 selected");
    await user.click(screen.getByRole("checkbox", { name: "Select Parry" }));
    await user.click(screen.getByRole("button", { name: "Put selected live" }));
    expect(
        JSON.parse(
            new FormData(screen.getByRole("dialog").querySelector("form")!).get(
                "selection",
            ) as string,
        ),
    ).toEqual(["weapon:one", "weapon:two"]);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Select all" }));
    await user.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(
        screen
            .getAllByRole<HTMLInputElement>("checkbox")
            .every((box) => !box.checked),
    ).toBe(true);
    expect(
        screen.getByRole<HTMLButtonElement>("button", {
            name: "Put selected live",
        }).disabled,
    ).toBe(true);
});

it("confirms exact mixed-kind IDs and keeps duplicate names independent", async () => {
    const user = userEvent.setup();
    render(<StagedContent {...props} />);
    await user.click(
        screen.getByRole("checkbox", { name: "Select Lasgun — House" }),
    );
    await user.click(screen.getByRole("checkbox", { name: "Select Parry" }));
    await user.click(screen.getByRole("button", { name: "Put selected live" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Lasgun — House/)).toBeTruthy();
    expect(within(dialog).queryByText(/Trading post/)).toBeNull();
    const form = dialog.querySelector("form")!;
    expect(new FormData(form).getAll("selection")).toHaveLength(1);
    expect(JSON.parse(new FormData(form).get("selection") as string)).toEqual([
        "weapon:one",
        "skill:one",
    ]);
    expect(new FormData(form).get("csrfmiddlewaretoken")).toBe("token");
    form.addEventListener("submit", (event) => event.preventDefault());
    fireEvent.submit(form);
    expect(form.getAttribute("action")).toBe(props.action);
    expect(form.method).toBe("post");
    expect(
        within(dialog).getByRole<HTMLButtonElement>("button", {
            name: "Put 2 live",
        }).disabled,
    ).toBe(true);
    fireEvent(window, new PageTransitionEvent("pageshow", { persisted: true }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Put selected live" }));
    expect(
        screen.getByRole<HTMLButtonElement>("button", { name: "Put 2 live" })
            .disabled,
    ).toBe(false);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
});

it("cancels back to the same selection and supports deselection", async () => {
    const user = userEvent.setup();
    render(<StagedContent {...props} />);
    const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
        name: "Select Parry",
    });
    await user.click(checkbox);
    const open = screen.getByRole("button", { name: "Put selected live" });
    await user.click(open);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(open);
    expect(checkbox.checked).toBe(true);
    await user.click(checkbox);
    expect(screen.getByRole("status").textContent).toContain("0 selected");
});

it("retains available selections on refusal and preserves single-entry actions", () => {
    const { container } = render(
        <StagedContent
            {...props}
            selected={["weapon:two", "weapon:missing"]}
            errors={["Review your selection."]}
        />,
    );
    expect(screen.getByRole("alert").textContent).toBe(
        "Review your selection.",
    );
    expect(screen.getByRole("status").textContent).toContain("1 selected");
    const form = container.querySelector("form")!;
    expect(form.method).toBe("post");
    expect(form.getAttribute("action")).toBe(props.singleAction);
    expect(new FormData(form).get("model")).toBe("weapon");
    expect(new FormData(form).get("pk")).toBe("one");
    expect(
        screen
            .getAllByRole("link", { name: "Delete…" })[0]
            .getAttribute("href"),
    ).toBe(row.deleteUrl);
});

it("shows an empty state without release controls", () => {
    render(<StagedContent {...props} groups={[]} />);
    expect(screen.getByText(/Nothing is staged/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
});
