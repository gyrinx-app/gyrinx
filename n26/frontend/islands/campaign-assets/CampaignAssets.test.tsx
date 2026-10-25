import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { CampaignAssets } from "./CampaignAssets";
import { mount as mountAssets } from "./entry";
import {
    assetGroups,
    type AssetEntry,
    type CampaignAssetsProps,
} from "./table";

function entry(
    id: string,
    name: string,
    income: number,
    holder = "",
    holderId = "",
): AssetEntry {
    return {
        id,
        name,
        assetName: "",
        boon: id === "b" ? "Armour" : "Income",
        held: Boolean(holder),
        holder,
        holderId,
        holderHref: `/gang/${holderId}/`,
        href: `/asset/${id}/`,
        income: {
            value: income,
            contributed: income,
            adjustment: 0,
            currency: true,
        },
        sortValues: {
            name: name.toLowerCase(),
            holder: holder.toLowerCase(),
            income,
        },
        actions: holder
            ? []
            : [
                  {
                      label: "Assign",
                      href: `/asset/${id}/assign/`,
                      dialog: true,
                      tone: "default",
                      separatorBefore: false,
                  },
              ],
    };
}
function props(): CampaignAssetsProps {
    return {
        label: "Territory",
        plural: "Territories",
        typeId: "territory",
        href: "/campaign/",
        sort: "name",
        group: "status",
        entries: [
            entry("b", "Ruins", 20, "Zulu", "z"),
            entry("c", "Workshop", 30),
            entry("a", "Ruins", 10, "Alpha", "a"),
            entry("d", "Cave", 5),
        ],
    };
}
beforeEach(() =>
    window.history.replaceState(null, "", "/campaign/?sort=-rating&group="),
);

test.each([
    ["name", ["d", "a", "b", "c"]],
    ["-name", ["c", "a", "b", "d"]],
    ["income", ["d", "a", "b", "c"]],
    ["-income", ["c", "b", "a", "d"]],
    ["holder", ["d", "c", "a", "b"]],
    ["-holder", ["d", "c", "b", "a"]],
])("%s sorting retains separate copies and their facts", (sort, expected) => {
    const data = props();
    const groups = assetGroups(data, { sort: sort as string, group: "" });
    expect(groups[0].rows.map((row) => row.id)).toEqual(expected);
    expect(groups[0].rows.find((row) => row.id === "b")?.boon).toBe("Armour");
    expect(data.entries.map((row) => row.id)).toEqual(["b", "c", "a", "d"]);
});

test("default and holder groups put unclaimed first without merging same-named gangs", () => {
    const data = props();
    expect(
        assetGroups(data, { sort: "name", group: "status" }).map((group) => [
            group.label,
            group.rows.map((row) => row.id),
        ]),
    ).toEqual([
        ["Unclaimed", ["d", "c"]],
        ["Held", ["a", "b"]],
    ]);
    for (const row of data.entries)
        if (row.held) {
            row.holder = "Same name";
            row.sortValues.holder = "same name";
        }
    const groups = assetGroups(data, { sort: "-income", group: "holder" });
    expect(groups.map((group) => group.label)).toEqual([
        "Unclaimed",
        "Same name",
        "Same name",
    ]);
    expect(groups.map((group) => group.rows.length)).toEqual([2, 1, 1]);
});

test("headers and grouping change in place, preserve gang state and restore on Back", async () => {
    const user = userEvent.setup();
    render(<CampaignAssets {...props()} onOpenDialog={vi.fn()} />);
    const region = screen.getByRole("region", {
        name: "Territories inventory",
    });
    await user.selectOptions(
        within(region).getByRole("combobox", { name: "View groups by" }),
        "",
    );
    await user.click(within(region).getByRole("link", { name: "Income" }));
    await user.click(within(region).getByRole("link", { name: "Income" }));
    expect(window.location.search).toBe(
        "?sort=-rating&group=&asset_sort=-income&asset_group=",
    );
    expect(
        within(region)
            .getByRole("columnheader", { name: "Income" })
            .getAttribute("aria-sort"),
    ).toBe("descending");
    expect(
        within(region)
            .getAllByRole("rowheader")
            .map((node) => node.textContent),
    ).toEqual(["Workshop", "Ruins", "Ruins", "Cave"]);
    act(() => {
        window.history.replaceState(
            null,
            "",
            "/campaign/?sort=-wealth&group=&asset_sort=name&asset_group=holder",
        );
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(
        within(region).getByRole("rowheader", {
            name: "Unclaimed · 2 territories",
        }),
    ).toBeTruthy();
    expect(
        within(region).getByRole("rowheader", { name: "Alpha · 1 territory" }),
    ).toBeTruthy();
    expect(
        within(region)
            .getByRole("link", { name: "Workshop" })
            .getAttribute("href"),
    ).toContain("sort=-wealth");
});

test("dialog actions keep the view, pause sorting and show failures", async () => {
    const user = userEvent.setup();
    let reject!: (reason: Error) => void;
    const opening = new Promise<void>((_, fail) => {
        reject = fail;
    });
    const open = vi.fn().mockReturnValue(opening);
    render(<CampaignAssets {...props()} onOpenDialog={open} />);
    await user.click(
        screen.getByRole("button", { name: "Actions for Workshop" }),
    );
    const assign = screen.getByRole("menuitem", { name: "Assign" });
    fireEvent.click(assign, { ctrlKey: true });
    expect(open).not.toHaveBeenCalled();
    await user.click(
        screen.getByRole("button", { name: "Actions for Workshop" }),
    );
    await user.click(screen.getByRole("menuitem", { name: "Assign" }));
    expect(open).toHaveBeenCalledWith(
        "/asset/c/assign/?sort=-rating&group=&asset_sort=name&asset_group=status",
    );
    expect(
        (screen.getByRole("combobox", { name: "Sort by" }) as HTMLSelectElement)
            .disabled,
    ).toBe(true);
    await act(async () => reject(new Error("offline")));
    expect(screen.getByRole("alert").textContent).toContain(
        "The form could not load.",
    );
    expect(
        (screen.getByRole("combobox", { name: "Sort by" }) as HTMLSelectElement)
            .disabled,
    ).toBe(false);
});

test("external gang views refresh every inventory action link and pending dialogs pause headers", async () => {
    const user = userEvent.setup();
    render(<CampaignAssets {...props()} onOpenDialog={vi.fn()} />);
    const request = {};
    act(() => {
        window.history.replaceState(
            null,
            "",
            "/campaign/?sort=-wealth&group=&asset_sort=name&asset_group=status",
        );
        window.dispatchEvent(new Event("n26:location-changed"));
        window.dispatchEvent(
            new CustomEvent("n26:campaign-dialog-request", {
                detail: { request, pending: true },
            }),
        );
    });
    expect(
        screen.getByRole("link", { name: "Workshop" }).getAttribute("href"),
    ).toContain("sort=-wealth");
    await user.click(screen.getByRole("link", { name: "Income" }));
    expect(
        screen
            .getByRole("columnheader", { name: "Territory" })
            .getAttribute("aria-sort"),
    ).toBe("ascending");
    act(() =>
        window.dispatchEvent(
            new CustomEvent("n26:campaign-dialog-request", {
                detail: { request, pending: false },
            }),
        ),
    );
    await user.click(screen.getByRole("link", { name: "Income" }));
    expect(
        screen
            .getByRole("columnheader", { name: "Income" })
            .getAttribute("aria-sort"),
    ).toBe("ascending");
});

test("Back dismisses a roll dialog and restores inventory preferences with no gang island", async () => {
    const user = userEvent.setup();
    const host = document.createElement("div");
    host.id = "n26-campaign-assets";
    const root = document.createElement("div");
    host.append(root);
    const outside = document.createElement("div");
    outside.id = "n26-roll-dialog-host";
    document.body.append(host, outside);
    const initialUrl = window.location.pathname + window.location.search;
    let dispose = () => {};
    act(() => {
        dispose = mountAssets(root, props());
    });
    try {
        await user.selectOptions(screen.getByLabelText("Sort by"), "-income");
        const dialogUrl = window.location.pathname + window.location.search;
        const dialog = document.createElement("dialog");
        dialog.setAttribute("open", "");
        dialog.close = vi.fn((reason?: string) => {
            dialog.removeAttribute("open");
            if (reason !== "n26-history")
                window.history.replaceState({}, "", dialogUrl);
        });
        outside.append(dialog);
        act(() => {
            window.history.replaceState({ htmx: false }, "", initialUrl);
            window.dispatchEvent(new PopStateEvent("popstate"));
        });
        expect(dialog.close).toHaveBeenCalledWith("n26-history");
        expect(dialog.hasAttribute("open")).toBe(false);
        expect(
            (screen.getByLabelText("Sort by") as HTMLSelectElement).value,
        ).toBe("name");
        expect(window.location.pathname + window.location.search).toBe(
            initialUrl,
        );
    } finally {
        act(() => dispose());
        host.remove();
        outside.remove();
    }
});

test("cancelled dialogs keep modified header navigation on the campaign", async () => {
    const user = userEvent.setup();
    const returnUrl = window.location.pathname + window.location.search;
    const open = vi.fn(async (href: string) => {
        window.history.replaceState({}, "", href);
    });
    render(<CampaignAssets {...props()} onOpenDialog={open} />);
    await user.click(
        screen.getByRole("button", { name: "Actions for Workshop" }),
    );
    await user.click(screen.getByRole("menuitem", { name: "Assign" }));
    window.history.replaceState({}, "", returnUrl);
    const header = screen.getByRole("link", { name: "Income" });
    expect(header.getAttribute("href")).toBe(
        "/campaign/?sort=-rating&group=&asset_sort=income&asset_group=status",
    );
    fireEvent.click(header, { ctrlKey: true });
    expect(window.location.pathname + window.location.search).toBe(returnUrl);
});

test("keyboard dialog requests retain the actions button as their focus return target", async () => {
    const user = userEvent.setup();
    let focusAtRequest: Element | null = null;
    const open = vi.fn(async () => {
        focusAtRequest = document.activeElement;
        throw new Error("offline");
    });
    render(<CampaignAssets {...props()} onOpenDialog={open} />);
    const button = screen.getByRole("button", { name: "Actions for Workshop" });
    button.focus();
    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(
        screen.getByRole("menuitem", { name: "Assign" }),
    );
    await user.keyboard("{Enter}");
    expect(open).toHaveBeenCalledOnce();
    expect(focusAtRequest).toBe(button);
    expect(document.activeElement).toBe(button);
    expect(screen.getByRole("alert").textContent).toContain(
        "The form could not load.",
    );
});
