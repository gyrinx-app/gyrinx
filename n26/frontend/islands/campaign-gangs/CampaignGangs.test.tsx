import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { CampaignGangs } from "./CampaignGangs";
import {
    guardDialogSubmission,
    mount as mountCampaignGangs,
    openCampaignDialog,
} from "./entry";
import {
    readView,
    tableGroups,
    type CampaignGangsProps,
    type Gang,
} from "./table";

function gang(
    name: string,
    rating: number,
    credits: number | null,
    label: string,
    reputation: number | null,
): Gang {
    return {
        id: name,
        name,
        type: "Escher",
        artwork: "",
        owner: null,
        colour: "#00aa00",
        href: `/gang/${name}/`,
        rating,
        credits,
        wealth: rating,
        creditsHref: "",
        removeHref: `/remove/${name}/`,
        overBudget: name === "Beta",
        labels: [label],
        assets: [{ label: "Territories", text: "Settlement" }],
        rolls: [
            {
                label: "Roll starting territory",
                href: `/campaign/?starting=${name}&type=territory`,
            },
        ],
        counters: [
            reputation === null
                ? null
                : {
                      name: "Reputation",
                      id: name,
                      value: reputation,
                      adjustHref: `/tally/${name}/?back=old`,
                      income: null,
                  },
        ],
        sortValues: {
            name: name.toLowerCase(),
            type: "escher",
            owner: null,
            rating,
            credits,
            wealth: rating,
            "counter:rep": reputation,
            "label:division": label.toLowerCase() || null,
        },
    };
}
function props(): CampaignGangsProps {
    return {
        href: "/campaign/",
        sort: "name",
        group: "",
        defaultGroup: "label:division",
        counters: [{ token: "counter:rep", label: "Reputation" }],
        labels: [
            {
                token: "label:division",
                label: "Division",
                colours: { Upper: "#ee0000" },
            },
        ],
        gangs: [
            gang("Beta", 200, null, "Lower", null),
            gang("Alpha", 100, 10, "Upper", 3),
            gang("Gamma", 300, 20, "", 1),
        ],
        badges: {},
        artwork: {},
    };
}
function gangNames() {
    return screen
        .getAllByRole("link")
        .filter((link) => link.getAttribute("href")?.startsWith("/gang/"))
        .map((link) => link.textContent);
}
beforeEach(() => {
    window.history.replaceState(null, "", "/campaign/");
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

test("sorts in place, writes the URL and keeps keyboard focus on the same heading", async () => {
    const user = userEvent.setup();
    const push = vi.spyOn(window.history, "pushState");
    render(<CampaignGangs {...props()} onOpenDialog={vi.fn()} />);
    const heading = screen.getByRole("link", { name: "Rating" });
    heading.focus();
    await user.keyboard("{Enter}");
    expect(gangNames()).toEqual(["Alpha", "Beta", "Gamma"]);
    await user.keyboard("{Enter}");
    expect(gangNames()).toEqual(["Gamma", "Beta", "Alpha"]);
    expect(document.activeElement).toBe(heading);
    expect(window.location.search).toBe("?sort=-rating&group=");
    expect(push).toHaveBeenCalledTimes(2);
    expect(heading.closest("th")?.getAttribute("aria-sort")).toBe("descending");
    expect(screen.getByRole("status").textContent).toContain(
        "Sorted by Rating, descending.",
    );
});
test("picker changes apply immediately and Back/Forward restore the URL view", async () => {
    const user = userEvent.setup();
    render(<CampaignGangs {...props()} onOpenDialog={vi.fn()} />);
    await user.selectOptions(screen.getByLabelText("Sort by"), "-counter:rep");
    await user.selectOptions(
        screen.getByLabelText("View groups by"),
        "label:division",
    );
    expect(
        screen
            .getByRole("columnheader", { name: "Upper · 1 gang" })
            .getAttribute("style"),
    ).toContain("rgb(238, 0, 0)");
    expect(gangNames()).toEqual(["Beta", "Alpha", "Gamma"]);
    expect(
        screen.getByRole("columnheader", { name: "Not set · 1 gang" }),
    ).toBeTruthy();
    act(() => {
        window.history.replaceState(null, "", "/campaign/?sort=-rating&group=");
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(gangNames()).toEqual(["Gamma", "Beta", "Alpha"]);
    expect(
        screen.getByLabelText("View groups by").getAttribute("value"),
    ).toBeNull();
    expect(
        (screen.getByLabelText("View groups by") as HTMLSelectElement).value,
    ).toBe("");
    act(() => {
        window.history.replaceState(null, "", "/campaign/");
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(
        (screen.getByLabelText("View groups by") as HTMLSelectElement).value,
    ).toBe("label:division");
});
test("keeps absent counters and unlimited credits last in both directions", () => {
    const data = props();
    for (const sort of ["credits", "-credits", "counter:rep", "-counter:rep"]) {
        const groups = tableGroups(data, { sort, group: "" });
        expect(groups[0].gangs.at(-1)?.name).toBe("Beta");
    }
});
test("stable tokens survive columns being added or removed and missing selections fall back", () => {
    const data = props();
    const search = "?sort=-counter:rep&group=label:division";
    data.counters.unshift({ token: "counter:earlier", label: "Earlier" });
    data.labels.unshift({
        token: "label:earlier",
        label: "Earlier",
        colours: {},
    });
    expect(readView(data, search)).toEqual({
        sort: "-counter:rep",
        group: "label:division",
    });
    data.counters.shift();
    data.labels.shift();
    expect(readView(data, search)).toEqual({
        sort: "-counter:rep",
        group: "label:division",
    });
    data.counters = [];
    data.labels = [];
    expect(readView(data, search)).toEqual({ sort: "name", group: "" });
});
test("an explicit empty group overrides the arbitrator default and old tokens are recognised", () => {
    const data = props();
    expect(readView(data, "?group=").group).toBe("");
    expect(readView(data, "?sort=-counter-0&group=label-0")).toEqual({
        sort: "-counter:rep",
        group: "label:division",
    });
});

test("takes ownership of history after an HTMX dialog so Back restores the mounted table", async () => {
    window.history.replaceState({ htmx: true, other: 123 }, "", "/campaign/");
    const push = vi.spyOn(window.history, "pushState");
    const user = userEvent.setup();
    render(<CampaignGangs {...props()} onOpenDialog={vi.fn()} />);
    expect(window.history.state).toEqual({ htmx: false, other: 123 });
    await user.selectOptions(screen.getByLabelText("Sort by"), "-rating");
    expect(push.mock.calls[0][0]).toEqual({ htmx: false, other: 123 });
});
test("grouping hides only that label; over budget stays first and all assets remain visible", async () => {
    const user = userEvent.setup();
    render(<CampaignGangs {...props()} onOpenDialog={vi.fn()} />);
    const row = screen.getByRole("link", { name: "Beta" }).closest("tbody")!;
    expect(
        row.querySelector("tr:last-child td > div")?.firstElementChild
            ?.textContent,
    ).toBe("Over budget");
    expect(within(row).getByText("Lower")).toBeTruthy();
    await user.selectOptions(
        screen.getByLabelText("View groups by"),
        "label:division",
    );
    const grouped = screen
        .getByRole("link", { name: "Beta" })
        .closest("tbody")!;
    expect(within(grouped).queryByText("Lower")).toBeNull();
    expect(within(grouped).getByText("Settlement")).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("View groups by"), "");
    expect(screen.getByText("Lower")).toBeTruthy();
});
test("counter and roll links open outside dialogs with the latest view and native modified clicks remain links", async () => {
    const user = userEvent.setup();
    const open = vi.fn().mockResolvedValue(undefined);
    render(<CampaignGangs {...props()} onOpenDialog={open} />);
    await user.selectOptions(screen.getByLabelText("Sort by"), "-rating");
    const pencil = screen.getByRole("link", {
        name: "Edit Reputation for Alpha",
    });
    await user.click(pencil);
    expect(open).toHaveBeenCalledWith(
        "/tally/Alpha/?back=%2Fcampaign%2F%3Fsort%3D-rating%26group%3D%23gangs",
    );
    const roll = screen.getAllByRole("link", {
        name: "Roll starting territory",
    })[0];
    fireEvent.click(roll, { ctrlKey: true });
    expect(open).toHaveBeenCalledTimes(1);
    await user.click(roll);
    expect(open.mock.calls[1][0]).toContain("sort=-rating&group=");
});
test("reports dialog failures and disables duplicate requests while waiting", async () => {
    const user = userEvent.setup();
    let reject: (reason: Error) => void = () => {};
    const open = vi.fn().mockImplementation(
        () =>
            new Promise((_, fail) => {
                reject = fail;
            }),
    );
    render(<CampaignGangs {...props()} onOpenDialog={open} />);
    const pencil = screen.getByRole("link", {
        name: "Edit Reputation for Alpha",
    });
    await user.click(pencil);
    await user.click(pencil);
    expect(open).toHaveBeenCalledTimes(1);
    await act(async () => {
        reject(new Error("Offline"));
    });
    expect(screen.getByRole("alert").textContent).toContain(
        "The form could not load.",
    );
});
test("keeps the view fixed until a pending dialog response arrives", async () => {
    const user = userEvent.setup();
    let finish: () => void = () => {};
    const open = vi.fn(
        () =>
            new Promise<void>((resolve) => {
                finish = resolve;
            }),
    );
    render(<CampaignGangs {...props()} onOpenDialog={open} />);
    await user.click(
        screen.getByRole("link", { name: "Edit Reputation for Alpha" }),
    );
    expect(
        (screen.getByLabelText("Sort by") as HTMLSelectElement).disabled,
    ).toBe(true);
    expect(
        (screen.getByLabelText("View groups by") as HTMLSelectElement).disabled,
    ).toBe(true);
    await user.click(screen.getByRole("link", { name: "Rating" }));
    expect(window.location.search).toBe("");
    expect(gangNames()).toEqual(["Alpha", "Beta", "Gamma"]);
    await act(async () => finish());
    await user.click(screen.getByRole("link", { name: "Rating" }));
    expect(window.location.search).toBe("?sort=rating&group=");
});
test("headers associate each value with the gang, group and column", async () => {
    const user = userEvent.setup();
    render(<CampaignGangs {...props()} onOpenDialog={vi.fn()} />);
    await user.selectOptions(
        screen.getByLabelText("View groups by"),
        "label:division",
    );
    const row = screen.getByRole("link", { name: "Alpha" }).closest("tbody")!;
    const ids = row.querySelector("td")!.getAttribute("headers")!.split(" ");
    expect(ids.map((id) => document.getElementById(id)?.textContent)).toEqual([
        "AlphaEscher",
        "Rating",
        "Upper · 1 gang",
    ]);
});
test("a counter redraw returns keyboard focus to its pencil", () => {
    render(
        <CampaignGangs
            {...props()}
            focusCounter="Alpha"
            onOpenDialog={vi.fn()}
        />,
    );
    expect(document.activeElement).toBe(
        screen.getByRole("link", { name: "Edit Reputation for Alpha" }),
    );
});

test("history restoration dismisses outside dialogs without restoring their saved return URL", () => {
    const host = document.createElement("div");
    const outside = document.createElement("div");
    outside.id = "n26-campaign-state-dialog-host";
    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    dialog.close = vi.fn();
    outside.append(dialog);
    document.body.append(host, outside);
    let dispose: () => void = () => {};
    act(() => {
        dispose = mountCampaignGangs(host, props());
    });
    act(() => {
        window.history.replaceState(null, "", "/campaign/?sort=-rating&group=");
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(dialog.close).toHaveBeenCalledWith("n26-history");
    expect(gangNames()).toEqual(["Gamma", "Beta", "Alpha"]);
    act(() => dispose());
    dialog.close = vi.fn();
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(dialog.close).not.toHaveBeenCalled();
    host.remove();
    outside.remove();
});

test.each([false, true])(
    "a delayed submission refreshes completed writes at the current view only after navigation (%s)",
    (navigated) => {
        window.history.replaceState(null, "", "/tally/Alpha/?back=rating");
        const form = document.createElement("form");
        document.body.append(form);
        const refresh = vi.fn();
        guardDialogSubmission(form, refresh);
        if (navigated) {
            window.history.replaceState(
                null,
                "",
                "/campaign/?sort=name&group=",
            );
            form.remove();
        }
        const response = new CustomEvent("htmx:beforeOnLoad", {
            cancelable: true,
        });
        form.dispatchEvent(response);
        expect(response.defaultPrevented).toBe(navigated);
        expect(refresh).toHaveBeenCalledTimes(navigated ? 1 : 0);
        if (navigated) expect(window.location.search).toBe("?sort=name&group=");
        form.remove();
    },
);

test("the outside dialog bridge keeps all swaps out of the React children and rejects login responses", async () => {
    const source = document.createElement("div");
    source.id = "n26-campaign-gangs";
    document.body.append(source);
    const ajax = vi.fn().mockImplementation(async () => {
        source.dispatchEvent(
            new CustomEvent("htmx:beforeOnLoad", {
                detail: {
                    xhr: {
                        status: 200,
                        getResponseHeader: () => "/campaign/?starting=Alpha",
                    },
                },
            }),
        );
    });
    vi.stubGlobal("htmx", { ajax });
    await openCampaignDialog(source, "/campaign/?starting=Alpha");
    expect(ajax).toHaveBeenCalledWith("GET", "/campaign/?starting=Alpha", {
        source,
        swap: "none",
    });
    let stale: CustomEvent;
    ajax.mockImplementation(async () => {
        window.history.replaceState(null, "", "/campaign/?sort=-rating&group=");
        stale = new CustomEvent("htmx:beforeOnLoad", {
            cancelable: true,
            detail: {
                xhr: { status: 200, getResponseHeader: () => "/old-dialog/" },
            },
        });
        source.dispatchEvent(stale);
    });
    await expect(openCampaignDialog(source, "/tally/Alpha/")).rejects.toThrow(
        "Dialog unavailable",
    );
    expect(stale!.defaultPrevented).toBe(true);
    ajax.mockImplementation(async () => undefined);
    await expect(openCampaignDialog(source, "/tally/Alpha/")).rejects.toThrow(
        "Dialog unavailable",
    );
    source.remove();
});
