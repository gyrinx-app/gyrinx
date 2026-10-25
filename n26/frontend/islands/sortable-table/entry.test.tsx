import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { PlainSortableTable } from "./entry";

test("the library wrapper sorts numeric cells and groups locally", async () => {
    const user = userEvent.setup();
    render(
        <PlainSortableTable
            label="Example"
            columns={[
                { token: "name", label: "Name" },
                { token: "income", label: "Income" },
            ]}
            rows={[
                {
                    id: "a",
                    values: { name: "One", income: 100 },
                    groups: { status: "Held" },
                },
                {
                    id: "b",
                    values: { name: "Two", income: 20 },
                    groups: { status: "Unclaimed" },
                },
            ]}
            groupOptions={[{ token: "status", label: "Status" }]}
            sort="name"
            group=""
        />,
    );
    await user.click(screen.getByRole("link", { name: "Income" }));
    expect(screen.getAllByRole("cell").map((node) => node.textContent)).toEqual(
        ["Two", "20", "One", "100"],
    );
    await user.selectOptions(
        screen.getByRole("combobox", { name: "View groups by" }),
        "status",
    );
    expect(screen.getByRole("rowheader", { name: "Held · 1" })).toBeTruthy();
    expect(
        screen.getByRole("rowheader", { name: "Unclaimed · 1" }),
    ).toBeTruthy();
});
