import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PoolRoll, type PoolRollProps } from "./PoolRoll";
import { mount } from "./entry";

const props: PoolRollProps = {
    count: {
        label: "Number to roll",
        helpText:
            "Choose how many to add to the unclaimed pool, up to 100 at a time.",
        value: "9",
        errors: [],
    },
    rolled: {
        label: "Your own roll",
        helpText: "Optional. Enter a dice roll you have already made.",
        value: "",
        errors: [],
    },
    table: "territories",
    tableErrors: [],
    previewUrl: "",
    assetType: "territory",
    tables: [
        {
            value: "territories",
            label: "Territories",
            die: "D66",
            lowest: 11,
            highest: 66,
        },
    ],
};

function inputs() {
    return {
        count: screen.getByRole("spinbutton", {
            name: "Number to roll",
        }) as HTMLInputElement,
        rolled: screen.getByRole("spinbutton", {
            name: "Your own roll",
        }) as HTMLInputElement,
    };
}

describe("campaign pool roll", () => {
    it("describes a fixed table without labelling its hidden field and retains errors", () => {
        const view = render(
            <PoolRoll
                {...props}
                tableErrors={["This table is unavailable."]}
            />,
        );
        expect(screen.getByRole("term").textContent).toBe("Table");
        expect(screen.getByRole("definition").textContent).toContain(
            "Territories",
        );
        expect(screen.getByRole("definition").textContent).toContain("D66");
        expect(
            view.container.querySelector('label[for="pool-table"]'),
        ).toBeNull();
        expect(screen.getByRole("note").textContent).toBe(
            "This table is unavailable.",
        );
    });
    it("sets quantity to one as the manual roll is typed and submits both fields", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <PoolRoll {...props} />
            </form>,
        );
        const { count, rolled } = inputs();
        expect(count.value).toBe("9");
        await user.type(rolled, "3");
        expect(count.value).toBe("1");
        expect(count.readOnly).toBe(true);
        await user.type(rolled, "4");
        await user.type(count, "2");
        const data = new FormData(view.container.querySelector("form")!);
        expect(data.get("count")).toBe("1");
        expect(data.get("rolled")).toBe("34");
        expect(screen.getByText(/Clear ‘Your own roll’/)).toBeTruthy();
    });

    it("allows a larger quantity again after the manual roll is cleared", async () => {
        const user = userEvent.setup();
        render(<PoolRoll {...props} />);
        const { count, rolled } = inputs();
        await user.type(rolled, "34");
        await user.clear(rolled);
        expect(count.readOnly).toBe(false);
        expect(count.value).toBe("1");
        await user.clear(count);
        await user.type(count, "12");
        expect(count.value).toBe("12");
        expect(rolled.value).toBe("");
    });

    it("syncs pasted values and retains server errors and dice guidance", () => {
        render(
            <PoolRoll
                {...props}
                rolled={{
                    ...props.rolled,
                    errors: ["You cannot roll 7 on a D66."],
                }}
            />,
        );
        const { count, rolled } = inputs();
        fireEvent.input(rolled, { target: { value: "34" } });
        expect(count.value).toBe("1");
        expect(screen.getByText("You cannot roll 7 on a D66.")).toBeTruthy();
        expect(rolled.getAttribute("aria-invalid")).toBe("true");
        expect(
            screen.getByText("A D66 roll is 11 to 66.").parentElement?.id,
        ).toBeTruthy();
        expect(rolled.getAttribute("aria-describedby")).toContain(
            screen.getByText("A D66 roll is 11 to 66.").parentElement?.id,
        );
    });

    it("normalises a manual roll on a refused dialog without discarding its value", () => {
        render(
            <PoolRoll {...props} rolled={{ ...props.rolled, value: "7" }} />,
        );
        expect(inputs().count.value).toBe("1");
        expect(inputs().rolled.value).toBe("7");
    });

    it("preserves edits and focus made before the island mounts", async () => {
        const host = document.createElement("div");
        host.className = "space-y-5";
        host.innerHTML =
            '<input name="count" value="12"><input name="rolled" value="34">';
        document.body.append(host);
        const oldRoll =
            host.querySelector<HTMLInputElement>('[name="rolled"]')!;
        oldRoll.focus();
        let dispose: () => void;
        await act(async () => {
            dispose = mount(host, props);
        });
        await waitFor(() =>
            expect(
                host.querySelector<HTMLInputElement>('[name="count"]')?.value,
            ).toBe("1"),
        );
        expect(
            host.querySelector<HTMLInputElement>('[name="rolled"]')?.value,
        ).toBe("34");
        expect(document.activeElement).toBe(
            host.querySelector('[name="rolled"]'),
        );
        await act(async () => {
            dispose!();
        });
        host.remove();
    });
});

function previewFetch() {
    const fetcher = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "valid", message: "Corpse Farm" }),
    });
    vi.stubGlobal("fetch", fetcher);
    return fetcher;
}
afterEach(() => vi.unstubAllGlobals());

describe("manual territory preview", () => {
    it("looks up a manual roll without submitting the form and clears the preview", async () => {
        const fetcher = previewFetch();
        render(<PoolRoll {...props} previewUrl="/preview/" />);
        fireEvent.change(inputs().rolled, { target: { value: "34" } });
        expect(await screen.findByText("Preview: Corpse Farm.")).toBeTruthy();
        const url = fetcher.mock.calls[0][0] as URL;
        expect(url.searchParams.get("table")).toBe("territories");
        expect(url.searchParams.get("rolled")).toBe("34");
        fireEvent.change(inputs().rolled, { target: { value: "" } });
        expect(screen.queryByText("Preview: Corpse Farm.")).toBeNull();
    });

    it("rechecks a changed table and ignores an older response", async () => {
        let resolveOld: (value: unknown) => void = () => {};
        const fetcher = previewFetch();
        fetcher.mockImplementationOnce(
            () =>
                new Promise((resolve) => {
                    resolveOld = resolve;
                }),
        );
        render(
            <PoolRoll
                {...props}
                previewUrl="/preview/"
                tables={[
                    ...props.tables,
                    {
                        value: "other",
                        label: "Other table",
                        die: "D6",
                        lowest: 1,
                        highest: 6,
                    },
                ]}
            />,
        );
        fireEvent.change(inputs().rolled, { target: { value: "3" } });
        await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
        fireEvent.click(screen.getByRole("radio", { name: /Other table/ }));
        expect(await screen.findByText("Preview: Corpse Farm.")).toBeTruthy();
        await act(async () =>
            resolveOld({
                ok: true,
                json: async () => ({ status: "valid", message: "Old result" }),
            }),
        );
        expect(screen.queryByText(/Old result/)).toBeNull();
        const url = fetcher.mock.calls[1][0] as URL;
        expect(url.searchParams.get("table")).toBe("other");
    });

    it("shows invalid results and recovers when the preview request fails", async () => {
        const fetcher = previewFetch();
        fetcher.mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                status: "invalid",
                message: "You cannot roll 17 on a D66.",
            }),
        });
        render(<PoolRoll {...props} previewUrl="/preview/" />);
        fireEvent.change(inputs().rolled, { target: { value: "17" } });
        expect(
            await screen.findByText("You cannot roll 17 on a D66."),
        ).toBeTruthy();
        fetcher.mockRejectedValueOnce(new Error("offline"));
        fireEvent.change(inputs().rolled, { target: { value: "18" } });
        expect(
            await screen.findByText(
                "Preview unavailable. You can still submit your roll.",
            ),
        ).toBeTruthy();
    });
});
