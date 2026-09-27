import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let listeners;
let form;

beforeEach(async () => {
    vi.useFakeTimers();
    vi.resetModules();
    vi.stubGlobal(
        "fetch",
        vi.fn(() => new Promise(() => {})),
    );
    listeners = vi.spyOn(window, "addEventListener");
    document.body.innerHTML = `
        <form id="post-battle-form" action="/n26/post-battle/draft/">
            <input name="revision" value="3">
            <input name="generation" value="4">
            <div data-xp-toolbar>
                <p data-xp-count data-one="{n} selected" data-many="{n} selected">0 selected</p>
                <button type="submit" data-xp-step="-1" disabled
                        data-one="Remove 1 XP from the selected model"
                        data-many="Remove 1 XP from the {n} selected models">−1 XP</button>
                <button type="submit" data-xp-step="+1" disabled
                        data-one="Add 1 XP to the selected model"
                        data-many="Add 1 XP to the {n} selected models">+1 XP</button>
            </div>
            <input type="checkbox" id="a" data-xp-participant="a-xp">
            <input id="a-xp" value="">
            <input type="checkbox" id="b" data-xp-participant="b-xp">
            <input id="b-xp" value="2">
            <input type="checkbox" id="c" data-xp-participant="c-xp" data-xp-blocked>
            <input id="c-xp" value="" disabled>
        </form>
        <p id="draft-save-status"></p>
    `;
    form = document.getElementById("post-battle-form");
    await import("../../core/static/n26/post-battle.js");
});

afterEach(() => {
    for (const [type, listener, options] of listeners.mock.calls) {
        window.removeEventListener(type, listener, options);
    }
    document.body.replaceChildren();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

function tick(id) {
    const box = document.getElementById(id);
    box.checked = true;
    box.dispatchEvent(new Event("input", { bubbles: true }));
}

const button = (step) => form.querySelector(`[data-xp-step="${step}"]`);

describe("post-battle XP toolbar", () => {
    it("counts every selected model, including ones that cannot take XP", () => {
        tick("a");
        tick("c");

        expect(form.querySelector("[data-xp-count]").textContent).toBe(
            "2 selected",
        );
        expect(button("+1").getAttribute("aria-label")).toBe(
            "Add 1 XP to the 2 selected models",
        );
        expect(button("+1").disabled).toBe(false);
        expect(button("-1").disabled).toBe(true);
    });

    it("offers −1 XP once a selected model has XP entered", () => {
        tick("b");

        expect(button("-1").disabled).toBe(false);
        expect(button("-1").getAttribute("aria-label")).toBe(
            "Remove 1 XP from the selected model",
        );
    });

    it("keeps both steps off when only blocked models are selected", () => {
        tick("c");

        expect(button("+1").disabled).toBe(true);
        expect(button("-1").disabled).toBe(true);
    });
});
