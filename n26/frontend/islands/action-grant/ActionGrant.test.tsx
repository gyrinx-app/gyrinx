import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ActionGrant, type GrantRow } from "./ActionGrant";

const rows: GrantRow[] = [
    { pk: "1", name: "Hunter one", gang: "Escher", granted: false },
    { pk: "2", name: "Hunter two", gang: "Spyrer", granted: false },
    { pk: "3", name: "Hunter three", gang: "Spyrer", granted: true },
];

describe("action grant selector", () => {
    it("searches, selects shown entries and keeps hidden selections in the form", async () => {
        const user = userEvent.setup();
        const { container } = render(
            <form>
                <ActionGrant rows={rows} />
            </form>,
        );
        const search = screen.getByRole("searchbox", {
            name: "Find fighter entries",
        });
        await user.type(search, "Escher");
        await user.click(screen.getByRole("button", { name: "Select shown" }));
        expect(
            new FormData(container.querySelector("form")!).getAll("profiles"),
        ).toEqual(["1"]);

        await user.clear(search);
        await user.type(search, "Spyrer");
        await user.click(screen.getByRole("button", { name: "Select shown" }));
        expect(
            new FormData(container.querySelector("form")!).getAll("profiles"),
        ).toEqual(["1", "2"]);
        expect(
            screen
                .getByRole("checkbox", { name: /Hunter three/ })
                .hasAttribute("disabled"),
        ).toBe(true);

        await user.click(
            screen.getByRole("button", { name: "Clear selection" }),
        );
        expect(
            new FormData(container.querySelector("form")!).getAll("profiles"),
        ).toEqual([]);
    });

    it("shows an empty search result", async () => {
        const user = userEvent.setup();
        render(<ActionGrant rows={rows} />);
        await user.type(
            screen.getByRole("searchbox", { name: "Find fighter entries" }),
            "missing",
        );
        expect(screen.getByText("No fighter entries match that.")).toBeTruthy();
    });
});
