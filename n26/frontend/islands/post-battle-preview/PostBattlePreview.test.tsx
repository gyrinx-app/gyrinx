import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PostBattlePreview, type PreviewDisplay } from "./PostBattlePreview";
const initial: PreviewDisplay = {
    rows: [{ id: "reputation", label: "Reputation", value: "5 → 5" }],
    models: [],
};
afterEach(() => document.body.replaceChildren());
describe("PostBattlePreview", () => {
    it("reads autosave snapshots completed before a slow island mounts", () => {
        document.body.innerHTML = '<form id="post-battle-form"></form>';
        const form = document.getElementById("post-battle-form")!;
        form.dataset.previewState = "ready";
        form.dataset.previewSnapshot = JSON.stringify({
            ...initial,
            rows: [{ id: "reputation", label: "Reputation", value: "5 → 8" }],
        });
        render(<PostBattlePreview {...initial} />, { container: form });
        expect(screen.getByText("5 → 8")).toBeTruthy();
        expect(screen.queryByText("5 → 5")).toBeNull();
        expect(screen.getByRole("status").textContent).toBe(
            "Preview up to date.",
        );
    });

    it("keeps same-named counters separate while conditional credit rows change", () => {
        document.body.innerHTML = '<form id="post-battle-form"></form>';
        const form = document.getElementById("post-battle-form")!;
        const errors = vi.spyOn(console, "error").mockImplementation(() => {});
        const rows = [
            { id: "one", label: "+1 Reputation", value: "0 → 1" },
            { id: "two", label: "+1 Reputation", value: "3 → 4" },
        ];
        render(<PostBattlePreview rows={rows} models={[]} />, {
            container: form,
        });
        act(() =>
            form.dispatchEvent(
                new CustomEvent("post-battle:preview", {
                    detail: {
                        state: "ready",
                        preview: {
                            rows: [
                                {
                                    id: "credits-change",
                                    label: "Change from the last version",
                                    value: "+5¢",
                                },
                                ...rows,
                            ],
                            models: [],
                        },
                    },
                }),
            ),
        );
        expect(screen.getAllByText("+1 Reputation")).toHaveLength(2);
        expect(screen.getByText("0 → 1")).toBeTruthy();
        expect(screen.getByText("3 → 4")).toBeTruthy();
        expect(
            errors.mock.calls.some((call) => String(call).includes("same key")),
        ).toBe(false);
        errors.mockRestore();
    });

    it("updates server-computed changes as entries change", () => {
        document.body.innerHTML = '<form id="post-battle-form"></form>';
        const form = document.getElementById("post-battle-form")!;
        render(<PostBattlePreview {...initial} />, { container: form });
        const status = screen.getByRole("status");
        expect(status.textContent).toBe("Preview up to date.");
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
                            rows: [
                                {
                                    id: "reputation",
                                    label: "Reputation",
                                    value: "5 → 8",
                                },
                            ],
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
