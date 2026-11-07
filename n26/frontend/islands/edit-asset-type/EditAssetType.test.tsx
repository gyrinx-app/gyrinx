import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { EditAssetType, type EditAssetTypeProps } from "./EditAssetType";

const props: EditAssetTypeProps = {
    heading: "Edit Rakit",
    campaignName: "Dust Falls",
    campaignHref: "/campaign/",
    campaignsHref: "/campaigns/",
    owner: { name: "arbitrator", href: "/owner/" },
    back: "/settings/?tab=asset-types",
    action: "/type/edit/",
    commandHref: "/type/edit/change/",
    csrfToken: "csrf",
    recoveryKey: "type:actor:subject",
    values: {
        label_singular: "Rakit",
        label_plural: "Rakits",
        display_group: "",
        ownership: "pooled",
        snapshot: "signed-original",
    },
    fields: {
        label_singular: { label: "Label", help: "The name for one asset." },
        label_plural: {
            label: "Plural label",
            help: "Leave blank to add an s.",
        },
        display_group: {
            label: "Display group",
            help: "Leave blank for a separate line.",
        },
        ownership: { label: "Ownership", help: "" },
    },
    ownershipNote: "",
    ownerships: [
        {
            value: "pooled",
            label: "Transferable",
            description: "One gang holds it at a time.",
        },
        {
            value: "held-one-each",
            label: "Inherent",
            description: "Each gang has its own.",
        },
    ],
    errors: {},
    conflict: null,
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

test("saves labels, blank plural, display group and the selected ownership", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<EditAssetType {...props} onNavigate={navigate} />);
    const user = userEvent.setup();
    await user.clear(screen.getByRole("textbox", { name: "Label *" }));
    await user.type(screen.getByRole("textbox", { name: "Label *" }), "Racket");
    await user.clear(screen.getByRole("textbox", { name: "Plural label" }));
    await user.type(
        screen.getByRole("textbox", { name: "Display group" }),
        "Supply sites",
    );
    await user.click(screen.getByRole("radio", { name: /Inherent/ }));
    await user.click(screen.getByRole("button", { name: "Save asset type" }));
    const body = fetch.mock.calls[0][1].body;
    expect(body.get("label_singular")).toBe("Racket");
    expect(body.get("label_plural")).toBe("");
    expect(body.get("display_group")).toBe("Supply sites");
    expect(body.get("ownership")).toBe("held-one-each");
    expect(body.get("snapshot")).toBe("signed-original");
    expect(navigate).toHaveBeenCalledWith(props.back);
});

test("states fixed ownership and posts its existing value while labels remain editable", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    render(
        <EditAssetType
            {...props}
            ownershipNote="Transferable. You cannot change ownership. Dust Falls already has rakits."
            ownerships={[]}
            onNavigate={() => {}}
        />,
    );
    expect(screen.queryByRole("radio")).toBeNull();
    expect(
        screen.getByRole("textbox", { name: "Label *" }).matches(":disabled"),
    ).toBe(false);
    await userEvent.click(
        screen.getByRole("button", { name: "Save asset type" }),
    );
    expect(fetch.mock.calls[0][1].body.get("ownership")).toBe("pooled");
});

test("focuses server errors and preserves the draft", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            json(
                {
                    errors: {
                        label_singular: [
                            "Dust Falls already has that asset type.",
                        ],
                    },
                },
                422,
            ),
        ),
    );
    render(<EditAssetType {...props} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Save asset type" }),
    );
    await waitFor(() =>
        expect(document.activeElement).toBe(screen.getByRole("alert")),
    );
    const label = screen.getByRole("textbox", { name: "Label *" });
    expect(label.getAttribute("aria-invalid")).toBe("true");
    expect((label as HTMLInputElement).value).toBe("Rakit");
    expect(label.matches(":disabled")).toBe(false);
});

test("shows a new ownership constraint and requires explicit review of the current type", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            json(
                {
                    code: "revision_conflict",
                    errors: {
                        __all__: [
                            "This asset type changed while you were editing. Review its current details before saving.",
                        ],
                    },
                    current: {
                        label_singular: "Rakit",
                        label_plural: "Rakits",
                        display_group: "",
                        ownership: "pooled",
                        ownershipLabel: "Transferable",
                        fixedReason: "Dust Falls already has rakits.",
                    },
                },
                409,
            ),
        ),
    );
    const navigate = vi.fn();
    render(<EditAssetType {...props} onNavigate={navigate} />);
    await userEvent.click(screen.getByRole("radio", { name: /Inherent/ }));
    await userEvent.click(
        screen.getByRole("button", { name: "Save asset type" }),
    );
    await screen.findByRole("region", { name: "Current asset type details" });
    expect(screen.getByText(/Current ownership: Transferable/)).not.toBeNull();
    expect(
        screen.getByRole("textbox", { name: "Label *" }).matches(":disabled"),
    ).toBe(true);
    expect(
        screen.queryByRole("button", { name: "Save asset type" }),
    ).toBeNull();
    expect(sessionStorage.getItem(props.recoveryKey)).not.toBeNull();
    await userEvent.click(
        screen.getByRole("button", { name: "Review current asset type" }),
    );
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    expect(navigate).toHaveBeenCalledWith(props.action);
});

test("restores an uncertain selection with its original snapshot and fresh credentials", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error())
        .mockResolvedValueOnce(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    const first = render(<EditAssetType {...props} />);
    await userEvent.click(screen.getByRole("radio", { name: /Inherent/ }));
    await userEvent.click(
        screen.getByRole("button", { name: "Save asset type" }),
    );
    await screen.findByRole("button", { name: "Retry save" });
    first.unmount();
    render(
        <EditAssetType
            {...props}
            csrfToken="fresh"
            values={{ ...props.values, snapshot: "new" }}
            onNavigate={() => {}}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[1][1].body.get("snapshot")).toBe("signed-original");
    expect(fetch.mock.calls[1][1].body.get("ownership")).toBe("held-one-each");
    expect(fetch.mock.calls[1][1].body.get("csrfmiddlewaretoken")).toBe(
        "fresh",
    );
});
