import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { PostBattlePreview, type PreviewDisplay } from "./PostBattlePreview";
const initial: PreviewDisplay = {
    rows: [{ label: "Reputation", value: "5 → 5" }],
    models: [],
};
afterEach(() => document.body.replaceChildren());
describe("PostBattlePreview", () => {
    it("updates server-computed changes as entries change", () => {
        document.body.innerHTML = '<form id="post-battle-form"></form>';
        const form = document.getElementById("post-battle-form")!;
        render(<PostBattlePreview {...initial} />, { container: form });
        const status = screen.getByRole("status");
        expect(status.textContent).toBe("Preview up to date");
        expect(status.querySelector("svg")).toBeTruthy();
        expect(status.previousElementSibling?.textContent).toBe(
            "Check changes",
        );
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
        expect(
            status
                .querySelector("svg")
                ?.classList.contains("motion-safe:animate-spin"),
        ).toBe(true);
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
                                    lines: ["+1 Kill Count (2 → 3)"],
                                    error: "",
                                },
                            ],
                        },
                    },
                }),
            );
        });
        expect(
            status
                .querySelector("svg")
                ?.classList.contains("motion-safe:animate-spin"),
        ).toBe(false);
        expect(screen.getByText("5 → 8")).toBeTruthy();
        expect(screen.getByText("<Cinder>")).toBeTruthy();
        expect(form.querySelector("cinder")).toBeNull();
        expect(screen.getByText("+1 Kill Count (2 → 3)")).toBeTruthy();
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
