import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { CycleRewards, type CycleRewardsProps } from "./CycleRewards";

function props(): CycleRewardsProps {
    return {
        label: "Cycle 1",
        token: "snapshot",
        csrf: "csrf",
        receipts: {},
        gangs: [
            {
                gang_id: "iron",
                name: "Iron keepers",
                credits: 100,
                receipt_id: "",
                lines: [
                    {
                        key: "income",
                        source: "territory",
                        name: "Workshop",
                        kind: "income",
                        amount: 15,
                        quantity: 0,
                        parts: [],
                        options: [],
                        blocked: "",
                        claimed: "",
                    },
                ],
            },
            {
                gang_id: "rust",
                name: "Rust keepers",
                credits: 100,
                receipt_id: "",
                lines: [],
            },
        ],
    };
}

it("excludes a skipped reward immediately and submits a comment per gang", () => {
    const { container } = render(<CycleRewards {...props()} />);
    expect(screen.getByText(/Credits after 115¢/)).toBeTruthy();
    fireEvent.click(
        screen.getByRole("checkbox", { name: "Skip Workshop income" }),
    );
    expect(screen.queryByText(/Credits after 115¢/)).toBeNull();
    fireEvent.change(screen.getAllByLabelText("Comment")[0], {
        target: { value: "Already paid manually" },
    });
    const payload = JSON.parse(
        (container.querySelector('[name="selections"]') as HTMLInputElement)
            .value,
    );
    expect(payload.iron.lines.income.skip).toBe(true);
    expect(payload.iron.comment).toBe("Already paid manually");
    expect(payload.rust.comment).toBe("");
});

it("leaves unselected gangs out of the submission", () => {
    const { container } = render(<CycleRewards {...props()} />);
    fireEvent.click(
        screen.getByRole("checkbox", { name: "Apply boons for Rust keepers" }),
    );
    const payload = JSON.parse(
        (container.querySelector('[name="selections"]') as HTMLInputElement)
            .value,
    );
    expect(Object.keys(payload)).toEqual(["iron"]);
    fireEvent.click(
        screen.getByRole("checkbox", { name: "Apply boons for Iron keepers" }),
    );
    expect(
        (
            screen.getByRole("button", {
                name: "Apply boons for 0 gangs",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
});

it("shows a receipt for an already applied gang", () => {
    const data = props();
    data.gangs[0].receipt_id = "receipt";
    data.receipts.iron = "/receipt/";
    render(<CycleRewards {...data} />);
    expect(
        screen.getByRole("link", { name: "View receipt" }).getAttribute("href"),
    ).toBe("/receipt/");
    expect(
        screen.queryByRole("checkbox", {
            name: "Apply boons for Iron keepers",
        }),
    ).toBeNull();
});

it("skips unavailable recruitment and requires a name for eligible recruitment", () => {
    const data = props();
    data.gangs[0].lines[0] = {
        ...data.gangs[0].lines[0],
        kind: "recruitment",
        options: [
            {
                key: "ganger",
                name: "Ganger",
                list_price: 50,
                discount: 25,
                payment: 25,
            },
        ],
    };
    render(<CycleRewards {...data} />);
    expect(screen.getByText(/payment 25¢/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Model name"), {
        target: { value: "" },
    });
    expect(
        (
            screen.getByRole("button", {
                name: "Apply boons for 2 gangs",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    fireEvent.click(
        screen.getByRole("checkbox", { name: "Skip Workshop recruitment" }),
    );
    expect(
        (
            screen.getByRole("button", {
                name: "Apply boons for 2 gangs",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(false);
});

it("requires an explicit skip for unavailable recruitment", () => {
    const data = props();
    data.gangs[0].lines[0] = {
        ...data.gangs[0].lines[0],
        kind: "recruitment",
        blocked: "The gang already has the maximum eligible fighters.",
    };
    render(<CycleRewards {...data} />);
    const skip = screen.getByRole("checkbox", {
        name: "Skip Workshop recruitment",
    }) as HTMLInputElement;
    const apply = screen.getByRole("button", {
        name: "Apply boons for 2 gangs",
    }) as HTMLButtonElement;
    expect(skip.checked).toBe(false);
    expect(apply.disabled).toBe(true);
    expect(screen.getByText(data.gangs[0].lines[0].blocked)).toBeTruthy();
    expect(screen.queryByLabelText("Model name")).toBeNull();
    fireEvent.click(skip);
    expect(apply.disabled).toBe(false);
});

it("keeps the reviewed gang selection, skips and comment after a refused preview", () => {
    const data = props();
    data.problem = "The rewards changed. Review the refreshed preview.";
    data.submitted = {
        iron: { comment: "Paid manually", lines: { income: { skip: true } } },
    };
    const { container } = render(<CycleRewards {...data} />);
    expect(
        (
            screen.getByRole("checkbox", {
                name: "Apply boons for Rust keepers",
            }) as HTMLInputElement
        ).checked,
    ).toBe(false);
    expect(
        (
            screen.getByRole("checkbox", {
                name: "Skip Workshop income",
            }) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect(
        (screen.getAllByLabelText("Comment")[0] as HTMLInputElement).value,
    ).toBe("Paid manually");
    const payload = JSON.parse(
        (container.querySelector('[name="selections"]') as HTMLInputElement)
            .value,
    );
    expect(payload).toMatchObject(data.submitted);
    expect(Object.keys(payload)).toEqual(["iron"]);
});

it("lets players view pending rewards without application controls", () => {
    const data = props();
    data.readOnly = true;
    render(<CycleRewards {...data} />);
    expect(screen.getByText(/Credits after 115¢/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: /Apply boons/ })).toBeNull();
    expect(screen.queryByLabelText("Comment")).toBeNull();
    expect(
        screen.getByText(
            "Only the campaign arbitrator can apply these rewards.",
        ),
    ).toBeTruthy();
});
