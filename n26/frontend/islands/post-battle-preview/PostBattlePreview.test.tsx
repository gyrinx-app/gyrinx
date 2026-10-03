import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { PostBattlePreview, type PreviewDisplay } from "./PostBattlePreview";
const initial: PreviewDisplay = {
    rows: [{ label: "Reputation", value: "5 → 5" }],
    models: [],
    territory: {
        name: "Sump Gate",
        heading: "Recorded with battle",
        outcome: "Moved from Ashen Choir to Rust Kings.",
        currentHolder: "Held by Ashen Choir.",
        note: "This outcome is already recorded.",
    },
};
afterEach(() => document.body.replaceChildren());
describe("PostBattlePreview", () => {
    it("updates server-computed changes while retaining the separate recorded outcome", () => {
        document.body.innerHTML = '<form id="post-battle-form"></form>';
        const form = document.getElementById("post-battle-form")!;
        render(<PostBattlePreview {...initial} />, { container: form });
        expect(
            screen.getByText("Moved from Ashen Choir to Rust Kings."),
        ).toBeTruthy();
        act(() => {
            form.dispatchEvent(
                new CustomEvent("post-battle:preview", {
                    detail: { state: "updating" },
                }),
            );
        });
        expect(screen.getByRole("status").textContent).toBe(
            "Updating preview…",
        );
        act(() => {
            form.dispatchEvent(
                new CustomEvent("post-battle:preview", {
                    detail: {
                        state: "ready",
                        preview: {
                            ...initial,
                            rows: [{ label: "Reputation", value: "5 → 8" }],
                            models: [
                                {
                                    id: "one",
                                    name: "<Cinder>",
                                    lines: ["Kill Count: 2 → 3"],
                                    error: "",
                                },
                            ],
                        },
                    },
                }),
            );
        });
        expect(screen.getByText("5 → 8")).toBeTruthy();
        expect(screen.getByText("<Cinder>")).toBeTruthy();
        expect(form.querySelector("cinder")).toBeNull();
        expect(screen.getByText("Kill Count: 2 → 3")).toBeTruthy();
        expect(screen.getByText("Held by Ashen Choir.")).toBeTruthy();
        act(() => {
            form.dispatchEvent(
                new CustomEvent("post-battle:preview", {
                    detail: { state: "failed" },
                }),
            );
        });
        expect(screen.getByRole("status").textContent).toContain("out of date");
    });
});
