import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AuthoringList, type AuthoringRow } from "./AuthoringList";

const rows: AuthoringRow[] = [
    {
        pk: "1",
        label: "Lasgun",
        qualifier: "House",
        url: "/weapons/1/",
        notes: ["Basic", "15¢"],
        help: "A rifle",
        staged: false,
        search: "lasgun house basic 15¢ a rifle",
    },
    {
        pk: "2",
        label: "Lasgun",
        qualifier: "Trading post",
        url: "/weapons/2/",
        notes: [],
        help: "",
        staged: true,
        search: "lasgun trading post staged",
    },
    {
        pk: "3",
        label: "Autopistol",
        qualifier: "",
        url: "/weapons/3/",
        notes: ["Pistol"],
        help: "",
        staged: false,
        search: "autopistol pistol",
    },
];

function setup(bulkActionUrl: string | null = "/attach/") {
    const user = userEvent.setup();
    const view = render(
        <AuthoringList
            rows={rows}
            pluralLabel="weapons"
            bulkActionUrl={bulkActionUrl}
        />,
    );
    return {
        user,
        ...view,
        search: screen.getByRole("searchbox", { name: "Search weapons" }),
    };
}

describe("authoring list", () => {
    it("filters the server's full search text and clears with keyboard focus", async () => {
        const { user, search } = setup();
        await user.type(search, "  RIFLE  ");
        expect(screen.getAllByRole("row")).toHaveLength(1);
        expect(screen.getByRole("status").textContent).toBe("1 of 3 weapons");
        await user.click(screen.getByRole("button", { name: "Clear search" }));
        expect(document.activeElement).toBe(search);
        expect(screen.getAllByRole("row")).toHaveLength(3);
        await user.type(search, "staged");
        expect(screen.getAllByRole("row")).toHaveLength(1);
        expect(
            screen.getByRole("link", { name: "Lasgun" }).getAttribute("href"),
        ).toBe("/weapons/2/");
    });

    it("submits selected IDs even after a filter hides those rows", async () => {
        const { user, search, container } = setup();
        await user.click(
            screen.getByRole("checkbox", { name: "Select Autopistol" }),
        );
        await user.type(search, "house");
        await user.click(
            screen.getByRole("checkbox", { name: "Select all shown" }),
        );
        const form = container.querySelector("form")!;
        expect(form.method).toBe("get");
        expect(new FormData(form).getAll("pk")).toEqual(["3", "1"]);
        await user.click(
            screen.getByRole("checkbox", { name: "Select all shown" }),
        );
        expect(new FormData(form).getAll("pk")).toEqual(["3"]);
    });

    it("keeps duplicate names independent and reports partial selection", async () => {
        const { user, container } = setup();
        await user.click(
            screen.getByRole("checkbox", {
                name: "Select Lasgun — Trading post",
            }),
        );
        expect(
            (
                screen.getByRole("checkbox", {
                    name: "Select all shown",
                }) as HTMLInputElement
            ).indeterminate,
        ).toBe(true);
        expect(
            new FormData(container.querySelector("form")!).getAll("pk"),
        ).toEqual(["2"]);
    });

    it("has an empty result and exposes no bulk controls without the capability", async () => {
        const { user, search } = setup(null);
        expect(screen.queryByRole("checkbox")).toBeNull();
        expect(
            screen.queryByRole("button", { name: "Attach a modifier" }),
        ).toBeNull();
        await user.type(search, "missing");
        expect(screen.getByText("No weapons match that.")).toBeTruthy();
    });

    it("treats labels as text and keeps the qualifier outside the link", () => {
        const label = '<img src=x onerror="alert(1)">';
        const { container } = render(
            <AuthoringList
                rows={[{ ...rows[0], label }]}
                pluralLabel="weapons"
                bulkActionUrl={null}
            />,
        );
        expect(screen.getByRole("link", { name: label }).textContent).toBe(
            label,
        );
        expect(container.querySelector("img")).toBeNull();
        expect(screen.getByRole("link").textContent).not.toContain("House");
    });
});
