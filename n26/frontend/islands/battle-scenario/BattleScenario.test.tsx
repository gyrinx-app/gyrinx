import {
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { BattleScenario, type BattleScenarioProps } from "./BattleScenario";
const props: BattleScenarioProps = {
    rollUrl: "/n26/scenario/",
    rolls: {},
    tables: [
        {
            key: "crew",
            name: "Crew",
            entries: [
                {
                    roll: 2,
                    name: "Hold Nothing Back",
                    text: "Both players use Custom (10).",
                    image: "",
                },
            ],
        },
        {
            key: "objective",
            name: "Objective",
            entries: [
                {
                    roll: 1,
                    name: "King of the Hive",
                    text: "Objective text.",
                    image: "",
                },
            ],
        },
    ],
};
beforeEach(() => window.history.replaceState(null, "", "/"));
afterEach(() => vi.unstubAllGlobals());
it("keeps each selected component with its own disclosure and generation choices separate", () => {
    render(<BattleScenario {...props} rolls={{ crew: "2", objective: "1" }} />);
    expect(screen.queryByText("Full details")).toBeNull();
    expect(screen.queryByText("Scenario options")).toBeNull();
    expect(
        screen.queryByRole("region", { name: "Scenario generation choices" }),
    ).toBeNull();
    const crew = screen.getByText("Crew").closest("details")!;
    const objective = screen.getByText("Objective").closest("details")!;
    expect(crew.open).toBe(false);
    fireEvent.click(crew.querySelector("summary")!);
    expect(crew.open).toBe(true);
    expect(objective.open).toBe(false);
    expect(
        within(crew).getByText("Both players use Custom (10)."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Change components" }));
    expect(
        screen.getByRole("region", { name: "Scenario generation choices" }),
    ).toBeTruthy();
    expect(screen.getByLabelText("Crew")).toBeTruthy();
});

it("generates an optional scenario without changing the battle name", async () => {
    const request = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ rolls: { crew: 2 } }),
    });
    vi.stubGlobal("fetch", request);
    const { container } = render(
        <>
            <input aria-label="Name" defaultValue="Sump clash" />
            <BattleScenario {...props} />
        </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    await screen.findByRole("button", { name: "Remove scenario" });
    expect(screen.getByLabelText("Name")).toHaveProperty("value", "Sump clash");
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("2");
    expect(
        screen
            .getByRole("link", { name: "View scenario" })
            .getAttribute("href"),
    ).toBe("/n26/scenario/?crew=2");
    fireEvent.click(screen.getByRole("button", { name: "Remove scenario" }));
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("");
});
it("sends component choices to the generator", async () => {
    const request = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ rolls: { crew: 2 } }),
    });
    vi.stubGlobal("fetch", request);
    render(<BattleScenario {...props} />);
    fireEvent.change(screen.getByLabelText("Crew"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Objective"), {
        target: { value: "leave" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    await waitFor(() => expect(request).toHaveBeenCalled());
    const url = new URL(request.mock.calls[0][0]);
    expect(url.searchParams.get("crew_pick")).toBe("2");
    expect(url.searchParams.get("objective_pick")).toBe("leave");
});
it("preserves the existing result after a failed generation", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error()));
    const { container } = render(
        <BattleScenario {...props} rolls={{ crew: "2" }} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate again" }));
    await screen.findByRole("alert");
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("2");
});
it("retains an invalid component until the reader generates or removes it", () => {
    const { container } = render(
        <BattleScenario {...props} rolls={{ crew: "9", objective: "1" }} />,
    );
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("9");
    expect(container.querySelector("dl")).toBeNull();
});

it("attaches generated results immediately and uses the updated revision on the next roll", async () => {
    const request = vi
        .fn()
        .mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ rolls: { crew: 2 }, revision: 4 }),
        })
        .mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ rolls: { objective: 1 }, revision: 5 }),
        });
    vi.stubGlobal("fetch", request);
    const { container } = render(
        <BattleScenario
            {...props}
            save={{
                action: "/connect/",
                csrfToken: "token",
                campaign: "campaign",
                battle: "battle",
                revision: 3,
                printUrl: "/print/",
            }}
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    await waitFor(() =>
        expect(
            container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
        ).toBe("2"),
    );
    expect(request).toHaveBeenCalledTimes(1);
    const first = request.mock.calls[0][1].body as FormData;
    expect(first.get("generate")).toBe("1");
    expect(first.get("battle")).toBe("battle");
    expect(first.get("revision")).toBe("3");
    expect(
        screen.queryByRole("button", { name: /Save scenario|Discard preview/ }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Generate again" }));
    await waitFor(() =>
        expect(
            container.querySelector<HTMLInputElement>('[name="objective"]')
                ?.value,
        ).toBe("1"),
    );
    expect(request).toHaveBeenCalledTimes(2);
    const second = request.mock.calls[1][1].body as FormData;
    expect(second.get("revision")).toBe("4");
    expect(second.has("crew")).toBe(false);
});
it("preserves the saved result when automatic attachment is refused", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce({
            ok: false,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
                errors: [
                    "This battle changed. Reload it before saving your changes.",
                ],
            }),
        }),
    );
    const { container } = render(
        <BattleScenario
            {...props}
            rolls={{ crew: "2" }}
            save={{
                action: "/connect/",
                csrfToken: "token",
                campaign: "campaign",
                battle: "battle",
                revision: 3,
                printUrl: "/print/",
            }}
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate again" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).toContain(
        "This battle changed.",
    );
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("2");
    expect(
        container.querySelector<HTMLInputElement>('[name="objective"]')?.value,
    ).toBe("");
});

it("blocks battle submission while generation is pending", async () => {
    let finish!: (value: unknown) => void;
    const request = vi.fn().mockReturnValue(
        new Promise((resolve) => {
            finish = resolve;
        }),
    );
    vi.stubGlobal("fetch", request);
    const { container } = render(
        <form>
            <BattleScenario {...props} />
        </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    expect(fireEvent.submit(container.querySelector("form")!)).toBe(false);
    expect(screen.getByLabelText("Crew")).toHaveProperty("disabled", true);
    finish({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ rolls: { crew: 2 } }),
    });
    await screen.findByRole("button", { name: "Generate again" });
    expect(fireEvent.submit(container.querySelector("form")!)).toBe(true);
    expect(request).toHaveBeenCalledTimes(1);
});

const withSideJobs: BattleScenarioProps = {
    ...props,
    sideJobKeys: ["side_job", "side_job_2", "side_job_3"],
    sideJobLimit: 3,
    sideJobSets: [
        {
            key: "general",
            name: "General",
            label: "General side jobs",
            entries: [
                { roll: 2, name: "The Package", text: "Carry it.", image: "" },
            ],
        },
        {
            key: "escher",
            name: "Escher",
            label: "Escher side jobs",
            entries: [
                {
                    roll: 5,
                    name: "Experimental Chem",
                    text: "Use the Administer Dose action.",
                    parts: [
                        ["Use the ", false],
                        ["Administer Dose", true],
                        [" action.", false],
                    ],
                    image: "",
                },
            ],
        },
    ],
};

it("picks a set, then a job from it, for each side job", async () => {
    const request = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
            rolls: { side_job: "escher-5", side_job_2: "general-2" },
        }),
    });
    vi.stubGlobal("fetch", request);
    const { container } = render(<BattleScenario {...withSideJobs} />);
    fireEvent.change(screen.getByLabelText("Side job 1 set"), {
        target: { value: "escher" },
    });
    const escher = screen.getByLabelText("Side job 1");
    expect(
        [...(escher as HTMLSelectElement).options].map((option) => option.text),
    ).toEqual(["Roll a D6", "5. Experimental Chem"]);
    fireEvent.click(screen.getByRole("button", { name: "+ Add side job" }));
    fireEvent.change(screen.getByLabelText("Side job 2 set"), {
        target: { value: "general" },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Add side job" }));
    expect(screen.queryByRole("button", { name: "+ Add side job" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove side job 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    await screen.findAllByText("Side job 2 (General)");
    const url = new URL(request.mock.calls[0][0]);
    expect(url.searchParams.get("side_job_pick")).toBe("escher");
    expect(url.searchParams.get("side_job_2_pick")).toBe("general");
    expect(url.searchParams.get("side_job_3_pick")).toBeNull();
    expect(url.searchParams.get("side_jobs")).toBe("2");
    expect(screen.getAllByText("Side job 1 (Escher)").length).toBeGreaterThan(
        0,
    );
    expect(screen.getByText("Administer Dose").tagName).toBe("STRONG");
    expect(
        container.querySelector<HTMLInputElement>('[name="side_job_2"]')?.value,
    ).toBe("general-2");
});

it("reads a battle's side job saved before there were sets as General", () => {
    render(<BattleScenario {...withSideJobs} rolls={{ side_job: "2" }} />);
    expect(screen.getAllByText("Side job 1 (General)").length).toBeGreaterThan(
        0,
    );
    expect(screen.getAllByText("The Package").length).toBeGreaterThan(0);
});

it.each(["escher-5-extra", "escher-5-", "general-2-extra"])(
    "retains the malformed side job %s without showing a valid preview",
    (value) => {
        const { container } = render(
            <BattleScenario
                {...withSideJobs}
                rolls={{ crew: "2", side_job: value }}
            />,
        );
        expect(
            container.querySelector<HTMLInputElement>('[name="side_job"]')
                ?.value,
        ).toBe(value);
        expect(container.querySelector("dl")).toBeNull();
        expect(screen.queryByRole("button", { name: /^Reroll / })).toBeNull();
    },
);

it("rerolls one side job on the set chosen and keeps the rest", async () => {
    HTMLDialogElement.prototype.showModal = vi.fn(function (
        this: HTMLDialogElement,
    ) {
        this.setAttribute("open", "");
    });
    HTMLDialogElement.prototype.close = vi.fn(function (
        this: HTMLDialogElement,
    ) {
        this.removeAttribute("open");
    });
    const request = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
            rolls: { crew: 2, side_job: "escher-5", side_job_2: "escher-5" },
        }),
    });
    vi.stubGlobal("fetch", request);
    render(
        <BattleScenario
            {...withSideJobs}
            rolls={{ crew: "2", side_job: "escher-5", side_job_2: "general-2" }}
        />,
    );
    expect(screen.queryByRole("button", { name: "Reroll Crew" })).toBeNull();
    fireEvent.click(
        screen.getByText("Side job 2 (General)").closest("summary")!,
    );
    fireEvent.click(
        screen.getByRole("button", { name: "Reroll Side job 2 (General)" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Reroll side job 2" });
    const menu = within(dialog).getByLabelText("Side job set");
    expect(menu).toHaveProperty("value", "general");
    expect(dialog.closest("section")).toBeNull();
    fireEvent.change(menu, { target: { value: "escher" } });
    fireEvent.click(screen.getByRole("button", { name: "Reroll" }));
    await waitFor(() => expect(request).toHaveBeenCalled());
    const url = new URL(request.mock.calls[0][0]);
    expect(url.searchParams.get("reroll")).toBe("side_job_2");
    expect(url.searchParams.get("reroll_set")).toBe("escher");
    expect(url.searchParams.get("crew")).toBe("2");
    expect(url.searchParams.get("side_job")).toBe("escher-5");
    expect(url.searchParams.get("side_job_2")).toBe("general-2");
    expect(url.searchParams.get("generate")).toBeNull();
    // The menu that gave that side job now rolls on its new set.
    fireEvent.click(screen.getByRole("button", { name: "Change components" }));
    expect(screen.getByLabelText("Side job 2 set")).toHaveProperty(
        "value",
        "escher",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    await screen.findAllByText("Side job 2 (Escher)");
});

it("keeps a saved battle's side jobs when generating again", async () => {
    const request = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
            rolls: { side_job: "escher-5", side_job_2: "general-2" },
        }),
    });
    vi.stubGlobal("fetch", request);
    render(
        <BattleScenario
            {...withSideJobs}
            rolls={{ side_job: "escher-5", side_job_2: "2" }}
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Change components" }));
    expect(screen.getByLabelText("Side job 1 set")).toHaveProperty(
        "value",
        "escher",
    );
    expect(screen.getByLabelText("Side job 2 set")).toHaveProperty(
        "value",
        "general",
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate again" }));
    await waitFor(() => expect(request).toHaveBeenCalled());
    const url = new URL(request.mock.calls[0][0]);
    expect(url.searchParams.get("side_job_pick")).toBe("escher");
    expect(url.searchParams.get("side_job_2_pick")).toBe("general");
    expect(url.searchParams.get("side_jobs")).toBe("2");
});

it("keeps a retained side job visible when its set is unavailable for new selection", () => {
    const archived = {
        key: "retired-set",
        name: "Retired",
        label: "Retired side jobs",
        entries: [
            {
                roll: 3,
                name: "Retained result",
                text: "An original retained result.",
                image: "",
            },
        ],
    };
    const offered = {
        ...archived,
        key: "available",
        name: "Available",
        label: "Available side jobs",
    };
    render(
        <BattleScenario
            {...props}
            rolls={{ crew: "2", side_job: "retired-set-3" }}
            sideJobKeys={["side_job"]}
            sideJobSets={[offered]}
            referencedSideJobSets={[archived]}
        />,
    );
    expect(screen.getAllByText("Retained result").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Hold Nothing Back").length).toBeGreaterThan(0);
    fireEvent.click(
        screen.getByText("Side job 1 (Retired)").closest("summary")!,
    );
    fireEvent.click(
        screen.getByRole("button", { name: "Reroll Side job 1 (Retired)" }),
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole<HTMLSelectElement>("combobox").value).toBe(
        "available",
    );
    expect(
        within(dialog).queryByRole("option", { name: "Retired side jobs" }),
    ).toBeNull();
});

it("keeps the selected replacement set on Generate again after rerolling a retired result", async () => {
    const archived = {
        key: "retired-set",
        name: "Retired",
        label: "Retired side jobs",
        entries: [
            {
                roll: 3,
                name: "Retained result",
                text: "An original retained result.",
                image: "",
            },
        ],
    };
    const offered = {
        ...archived,
        key: "available",
        name: "Available",
        label: "Available side jobs",
    };
    const request = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
            rolls: { side_job: "available-3" },
            revision: 1,
        }),
    });
    vi.stubGlobal("fetch", request);
    render(
        <BattleScenario
            {...props}
            save={{
                action: "/save/",
                csrfToken: "csrf",
                campaign: "campaign",
                battle: "battle",
                revision: 0,
                printUrl: "/print/",
            }}
            rolls={{ side_job: "retired-set-3" }}
            sideJobKeys={["side_job"]}
            sideJobSets={[offered]}
            referencedSideJobSets={[archived]}
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Change components" }));
    expect(
        screen.getByLabelText<HTMLSelectElement>("Side job 1 set").value,
    ).toBe("retired-set");
    fireEvent.click(
        screen.getByText("Side job 1 (Retired)").closest("summary")!,
    );
    fireEvent.click(
        screen.getByRole("button", { name: "Reroll Side job 1 (Retired)" }),
    );
    fireEvent.submit(screen.getByRole("dialog").querySelector("form")!);
    await waitFor(() =>
        expect(
            screen.getByLabelText<HTMLSelectElement>("Side job 1 set").value,
        ).toBe("available"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate again" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(
        (request.mock.calls[1][1].body as FormData).get("side_job_pick"),
    ).toBe("available");
});
