import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ScenarioPicks, type ScenarioPicksProps } from "./ScenarioPicks";

const props: ScenarioPicksProps = {
    tables: [
        {
            key: "crew",
            label: "Crew",
            choices: [
                ["roll", "Roll a D6"],
                ["leave", "Leave out"],
                ["2", "2. Patrol"],
            ],
        },
    ],
    sideJobKeys: ["side_job", "side_job_2", "side_job_3"],
    sideJobLimit: 3,
    sidePicks: [""],
    sideJobSets: [
        {
            key: "general",
            name: "General",
            label: "General side jobs",
            entries: [{ roll: 2, name: "The Package" }],
        },
        {
            key: "escher",
            name: "Escher",
            label: "Escher side jobs",
            entries: [{ roll: 3, name: "Hunt Together" }],
        },
    ],
    errors: {},
};
beforeEach(() =>
    window.history.replaceState(null, "", "/n26/scenario/?crew=2"),
);

it("uses an empty selection for legacy leave-out links without offering that option", () => {
    window.history.replaceState(
        null,
        "",
        "/n26/scenario/?side_job_pick=leave&side_jobs=1",
    );
    render(<ScenarioPicks {...props} />);
    const set = screen.getByLabelText<HTMLSelectElement>("Side job 1 set");
    expect(set.value).toBe("");
    expect([...set.options].some((option) => option.value === "leave")).toBe(
        false,
    );
    expect(screen.getByLabelText("Side job 1")).toHaveProperty(
        "disabled",
        true,
    );
});

it("keeps the set dropdown beside its dependent job dropdown without submitting", () => {
    const submit = vi.fn((event) => event.preventDefault());
    render(
        <form onSubmit={submit}>
            <ScenarioPicks {...props} />
        </form>,
    );
    expect(screen.getByLabelText("Side job 1")).toHaveProperty(
        "disabled",
        true,
    );
    fireEvent.change(screen.getByLabelText("Side job 1 set"), {
        target: { value: "general" },
    });
    fireEvent.change(screen.getByLabelText("Side job 1"), {
        target: { value: "general-2" },
    });
    expect(new URLSearchParams(location.search).get("side_job_pick")).toBe(
        "general-2",
    );
    fireEvent.change(screen.getByLabelText("Side job 1 set"), {
        target: { value: "escher" },
    });
    expect(screen.getByLabelText("Side job 1 set")).toHaveProperty(
        "value",
        "escher",
    );
    expect(screen.getByLabelText("Side job 1")).toHaveProperty(
        "value",
        "escher",
    );
    expect(screen.queryByRole("option", { name: "2. The Package" })).toBeNull();
    expect(
        screen.getByRole("option", { name: "3. Hunt Together" }),
    ).toBeTruthy();
    expect(new URLSearchParams(location.search).get("side_job_pick")).toBe(
        "escher",
    );
    expect(new URLSearchParams(location.search).get("crew")).toBe("2");
    expect(submit).not.toHaveBeenCalled();
});

it("restores both controls from the URL on reload and history navigation", () => {
    window.history.replaceState(
        null,
        "",
        "/n26/scenario/?side_job_pick=escher-3&side_jobs=1&crew_pick=leave",
    );
    const { unmount } = render(<ScenarioPicks {...props} />);
    expect(screen.getByLabelText("Side job 1 set")).toHaveProperty(
        "value",
        "escher",
    );
    expect(screen.getByLabelText("Side job 1")).toHaveProperty(
        "value",
        "escher-3",
    );
    expect(screen.getByLabelText("Crew")).toHaveProperty("value", "leave");
    fireEvent.change(screen.getByLabelText("Side job 1 set"), {
        target: { value: "general" },
    });
    const changed = location.href;
    act(() => {
        window.history.replaceState(
            null,
            "",
            "/n26/scenario/?side_job_pick=escher-3&side_jobs=1&crew_pick=leave",
        );
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByLabelText("Side job 1")).toHaveProperty(
        "value",
        "escher-3",
    );
    act(() => {
        window.history.replaceState(null, "", changed);
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByLabelText("Side job 1 set")).toHaveProperty(
        "value",
        "general",
    );
    unmount();
    render(<ScenarioPicks {...props} />);
    expect(screen.getByLabelText("Side job 1 set")).toHaveProperty(
        "value",
        "general",
    );
});

it("adds and removes side jobs locally and compacts their URL choices", () => {
    render(<ScenarioPicks {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "+ Add side job" }));
    fireEvent.change(screen.getByLabelText("Side job 2 set"), {
        target: { value: "general" },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Add side job" }));
    fireEvent.change(screen.getByLabelText("Side job 3 set"), {
        target: { value: "escher" },
    });
    expect(screen.queryByRole("button", { name: "+ Add side job" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove side job 2" }));
    expect(screen.getByLabelText("Side job 2 set")).toHaveProperty(
        "value",
        "escher",
    );
    const query = new URLSearchParams(location.search);
    expect(query.get("side_jobs")).toBe("2");
    expect(query.get("side_job_2_pick")).toBe("escher");
    expect(query.has("side_job_3_pick")).toBe(false);
});

it("keeps an explicitly empty set empty even when the scenario has a side job", () => {
    render(<ScenarioPicks {...props} sidePicks={["escher"]} />);
    fireEvent.change(screen.getByLabelText("Side job 1 set"), {
        target: { value: "" },
    });
    expect(new URLSearchParams(location.search).get("side_jobs")).toBe("1");
    expect(screen.getByLabelText("Side job 1")).toHaveProperty(
        "disabled",
        true,
    );
    act(() => window.dispatchEvent(new PopStateEvent("popstate")));
    expect(screen.getByLabelText("Side job 1 set")).toHaveProperty("value", "");
});

it("submits the selected set and named job through the native GET form", () => {
    const { container } = render(
        <form>
            <ScenarioPicks {...props} />
        </form>,
    );
    fireEvent.change(screen.getByLabelText("Side job 1 set"), {
        target: { value: "escher" },
    });
    fireEvent.change(screen.getByLabelText("Side job 1"), {
        target: { value: "escher-3" },
    });
    const data = new FormData(container.querySelector("form")!);
    expect(data.get("side_job_set")).toBe("escher");
    expect(data.get("side_job_pick")).toBe("escher-3");
});

it("shows a held unavailable set and lets the reader replace it for generation", () => {
    const retired = {
        key: "retired",
        name: "Retired",
        label: "Retired side jobs",
        entries: [],
    };
    const { container } = render(
        <form>
            <ScenarioPicks
                {...props}
                sidePicks={["retired", "escher"]}
                referencedSideJobSets={[retired]}
            />
        </form>,
    );
    expect(
        new FormData(container.querySelector("form")!).get("side_job_pick"),
    ).toBe("retired");
    expect(screen.getByLabelText("Side job 1 set")).toHaveProperty(
        "value",
        "retired",
    );
    expect(
        screen.getByRole("option", { name: "Retired side jobs (unavailable)" }),
    ).toHaveProperty("disabled", true);
    expect(screen.getByLabelText("Side job 2 set")).toHaveProperty(
        "value",
        "escher",
    );
    fireEvent.change(screen.getByLabelText("Side job 1 set"), {
        target: { value: "general" },
    });
    expect(screen.getByLabelText("Side job 1")).toHaveProperty(
        "disabled",
        false,
    );
    expect(new URLSearchParams(location.search).get("side_job_pick")).toBe(
        "general",
    );
    expect(screen.getByLabelText("Side job 2 set")).toHaveProperty(
        "value",
        "escher",
    );
});
