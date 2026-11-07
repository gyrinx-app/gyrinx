import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { EditHolding, type EditHoldingProps } from "./EditHolding";

const props: EditHoldingProps = {
    heading: "Edit Old Ruins",
    holdingName: "Old Ruins",
    campaignName: "Dust Falls",
    campaignHref: "/campaign/",
    campaignsHref: "/campaigns/",
    detailHref: "/asset/?asset_sort=income",
    catalogueName: "Old Ruins",
    catalogueIncome: 30,
    values: { name: "", income: "", snapshot: "signed-original" },
    fields: {
        name: {
            label: "Name in this campaign",
            help: "Leave blank to use the catalogue name.",
        },
        income: {
            label: "Income override",
            help: "Leave blank to use catalogue income. Enter 0 for no base income. Boon contributions still apply.",
        },
    },
    errors: {},
    conflict: null,
    back: "/campaign/?asset_sort=income#assets",
    action: "/asset/edit/?from=detail",
    commandHref: "/asset/edit/change/?from=detail",
    csrfToken: "csrf",
    recoveryKey: "holding:actor:asset",
};
const json = (data: unknown, status = 200) => ({
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
});
afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
});

test.each(["", "0"])(
    "preserves the income value %j and the signed snapshot on save",
    async (income) => {
        const fetch = vi
            .fn()
            .mockResolvedValue(json({ nextUrl: props.detailHref }));
        vi.stubGlobal("fetch", fetch);
        const navigate = vi.fn();
        render(
            <EditHolding
                {...props}
                values={{ ...props.values, income }}
                onNavigate={navigate}
            />,
        );
        await userEvent.type(
            screen.getByRole("textbox", { name: props.fields.name.label }),
            "Sump ruins",
        );
        await userEvent.click(screen.getByRole("button", { name: "Save" }));
        expect(fetch.mock.calls[0][1].body.get("income")).toBe(income);
        expect(fetch.mock.calls[0][1].body.get("snapshot")).toBe(
            "signed-original",
        );
        expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("csrf");
        expect(navigate).toHaveBeenCalledWith(props.detailHref);
        expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    },
);

test("keeps the draft and focuses accessible server errors", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(
                json(
                    { errors: { income: ["Income must be at least 0."] } },
                    422,
                ),
            ),
    );
    render(
        <EditHolding
            {...props}
            values={{ ...props.values, name: "Sump ruins", income: "40" }}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
        expect(document.activeElement).toBe(screen.getByRole("alert")),
    );
    const income = screen.getByRole("spinbutton");
    expect(income.getAttribute("aria-invalid")).toBe("true");
    expect(
        document.getElementById(
            income.getAttribute("aria-describedby")!.split(" ").at(-1)!,
        )?.textContent,
    ).toBe("Income must be at least 0.");
    expect((income as HTMLInputElement).value).toBe("40");
    expect(income.matches(":disabled")).toBe(false);
});

test("freezes a conflicting draft and reviews current details only through an explicit action", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            json(
                {
                    code: "revision_conflict",
                    errors: {
                        __all__: [
                            "This asset changed while you were editing. Review its current details before saving.",
                        ],
                    },
                    current: { name: "Newer edit", income: 60 },
                },
                409,
            ),
        ),
    );
    const navigate = vi.fn();
    render(
        <EditHolding
            {...props}
            values={{ ...props.values, name: "Old draft", income: "0" }}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("region", { name: "Current asset details" });
    expect(screen.getByText("Current name: Newer edit.")).not.toBeNull();
    expect(screen.getByText("Current income override: 60¢.")).not.toBeNull();
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(
        "Old draft",
    );
    expect(screen.getByRole("spinbutton").matches(":disabled")).toBe(true);
    expect(screen.queryByRole("button", { name: /^Save$/ })).toBeNull();
    expect(sessionStorage.getItem(props.recoveryKey)).toContain(
        "signed-original",
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Review current asset" }),
    );
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    expect(navigate).toHaveBeenCalledWith(props.action);
});

test("restores an uncertain draft with its original snapshot and a fresh CSRF token", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error())
        .mockResolvedValueOnce(json({ nextUrl: props.detailHref }));
    vi.stubGlobal("fetch", fetch);
    const first = render(
        <EditHolding {...props} values={{ ...props.values, income: "0" }} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("button", { name: "Retry save" });
    first.unmount();
    const navigate = vi.fn();
    render(
        <EditHolding
            {...props}
            csrfToken="fresh"
            values={{ ...props.values, snapshot: "new-snapshot" }}
            onNavigate={navigate}
        />,
    );
    expect(screen.getByRole("spinbutton").matches(":disabled")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[1][1].body.get("snapshot")).toBe("signed-original");
    expect(fetch.mock.calls[1][1].body.get("income")).toBe("0");
    expect(fetch.mock.calls[1][1].body.get("csrfmiddlewaretoken")).toBe(
        "fresh",
    );
    expect(navigate).toHaveBeenCalledWith(props.detailHref);
});

test("a refused retry retains uncertainty unless the server confirms a revision conflict", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockRejectedValueOnce(new Error())
            .mockResolvedValueOnce(
                json(
                    {
                        errors: {
                            __all__: ["Only the arbitrator can edit an asset."],
                        },
                    },
                    422,
                ),
            ),
    );
    render(<EditHolding {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(
        await screen.findByRole("button", { name: "Retry save" }),
    );
    await screen.findByText(/The earlier save is still unconfirmed/);
    expect(screen.getByRole("spinbutton").matches(":disabled")).toBe(true);
    expect(sessionStorage.getItem(props.recoveryKey)).not.toBeNull();
});

test("resolves the retained command before applying conflict facts from an older native POST", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            name: "Retained draft",
            income: "0",
            snapshot: "retained-snapshot",
        }).toString(),
    );
    const fetch = vi
        .fn()
        .mockResolvedValue(json({ nextUrl: props.detailHref }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <EditHolding
            {...props}
            values={{
                name: "Older draft",
                income: "50",
                snapshot: "older-snapshot",
            }}
            conflict={{ name: "Old conflict", income: 60 }}
            errors={{ __all__: ["Conflict for the older draft."] }}
            onNavigate={navigate}
        />,
    );
    expect(
        screen.queryByRole("button", { name: "Review current asset" }),
    ).toBeNull();
    expect(screen.queryByText("Conflict for the older draft.")).toBeNull();
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(
        "Retained draft",
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[0][1].body.get("snapshot")).toBe(
        "retained-snapshot",
    );
    expect(navigate).toHaveBeenCalledWith(props.detailHref);
});
