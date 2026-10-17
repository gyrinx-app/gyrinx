import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import { SortableTable, type TableView } from "./SortableTable";

const columns = [
    { token: "name", label: "Name" },
    { token: "income", label: "Income" },
    { token: "actions", label: "Actions", sortable: false, hiddenLabel: true },
];
function Example({ disabled = false }: { disabled?: boolean }) {
    const [view, setView] = useState<TableView>({
        sort: "name",
        group: "status",
    });
    return (
        <SortableTable
            id="example"
            label="Example table"
            view={view}
            columns={columns}
            groupOptions={[{ token: "status", label: "Status" }]}
            groups={[
                {
                    id: "held",
                    label: "Held",
                    colour: "#123456",
                    countLabel: "2 territories",
                    rows: ["One", "Two"],
                },
            ]}
            onViewChange={setView}
            disabled={disabled}
            viewHref={(next) => `/table/?sort=${next.sort}`}
            renderRows={(rows, groupId) => (
                <tbody>
                    {rows.map((row) => (
                        <tr key={row}>
                            <th scope="row" headers={groupId}>
                                {row}
                            </th>
                            <td>20</td>
                            <td />
                        </tr>
                    ))}
                </tbody>
            )}
        />
    );
}

test("clickable headers toggle sort direction and preserve native modified links", async () => {
    const user = userEvent.setup();
    render(<Example />);
    const income = screen.getByRole("columnheader", { name: "Income" });
    expect(income.getAttribute("aria-sort")).toBe("none");
    await user.click(screen.getByRole("link", { name: "Income" }));
    expect(income.getAttribute("aria-sort")).toBe("ascending");
    await user.click(screen.getByRole("link", { name: "Income" }));
    expect(income.getAttribute("aria-sort")).toBe("descending");
    fireEvent.click(screen.getByRole("link", { name: "Name" }), {
        ctrlKey: true,
    });
    expect(income.getAttribute("aria-sort")).toBe("descending");
    expect(
        screen.getByRole("rowheader", { name: "Held · 2 territories" }).id,
    ).toBe("example-group-held");
    expect(screen.getByRole("status").textContent).toContain(
        "Sorted by Income, descending.",
    );
});

test("busy tables pause both selectors and header changes", async () => {
    const user = userEvent.setup();
    render(<Example disabled />);
    expect(
        (screen.getByRole("combobox", { name: "Sort by" }) as HTMLSelectElement)
            .disabled,
    ).toBe(true);
    await user.click(screen.getByRole("link", { name: "Income" }));
    expect(
        screen
            .getByRole("columnheader", { name: "Name" })
            .getAttribute("aria-sort"),
    ).toBe("ascending");
});

test("empty and error states remain visible and labelled", () => {
    render(
        <SortableTable
            id="empty"
            label="Inventory"
            view={{ sort: "name", group: "" }}
            columns={columns}
            groups={[]}
            onViewChange={vi.fn()}
            viewHref={() => "#"}
            renderRows={() => null}
            empty="No territories yet."
            error="The form could not load."
        />,
    );
    expect(screen.getByRole("region", { name: "Inventory" })).toBeTruthy();
    expect(screen.getByText("No territories yet.")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe(
        "The form could not load.",
    );
});
