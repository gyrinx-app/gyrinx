import { act, render, screen } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { QUERY_CHANGE, useQueryHref } from "./useQueryHref";

const keys = ["crew_pick", "side_job_pick", "side_job_2_pick", "side_jobs"];
function Link() {
    return (
        <a
            href={useQueryHref(
                "/n26/scenario/?crew=2&side_job=escher-3&side_job_pick=escher&reroll=side_job#scenario",
                keys,
            )}
        >
            Reroll
        </a>
    );
}
beforeEach(() =>
    window.history.replaceState(
        null,
        "",
        "/n26/scenario/?crew=2&side_job=escher-3&side_job_pick=escher",
    ),
);

it("updates action links with current choices while keeping results and action parameters", () => {
    render(<Link />);
    act(() => {
        window.history.pushState(
            null,
            "",
            "/n26/scenario/?crew=2&side_job=escher-3&crew_pick=leave&side_job_pick=orlock&side_job_2_pick=general&side_jobs=2",
        );
        window.dispatchEvent(new Event(QUERY_CHANGE));
    });
    const url = new URL(screen.getByRole<HTMLAnchorElement>("link").href);
    expect(url.searchParams.get("crew_pick")).toBe("leave");
    expect(url.searchParams.get("side_job_pick")).toBe("orlock");
    expect(url.searchParams.get("side_job_2_pick")).toBe("general");
    expect(url.searchParams.get("crew")).toBe("2");
    expect(url.searchParams.get("reroll")).toBe("side_job");
    expect(url.hash).toBe("#scenario");
});

it("removes cleared choices from links on history navigation", () => {
    render(<Link />);
    act(() => {
        window.history.replaceState(null, "", "/n26/scenario/?side_jobs=1");
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole<HTMLAnchorElement>("link").href).not.toContain(
        "side_job_pick",
    );
});
