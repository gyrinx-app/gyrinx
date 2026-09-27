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
            <input id="first" data-credit-amount value="40">
            <input id="second" data-credit-amount value="">
            <span data-credit-total>+40¢</span>
            <input id="rep" data-counter-base="5" aria-describedby="rep-after" value="">
            <span id="rep-after">5</span>
            <input id="favour" data-counter-base="1" data-counter-limit="1000"
                   aria-describedby="favour-after" value="">
            <span id="favour-after">1</span>
            <button type="submit" id="favour-minus" name="intent"
                    value="counter-step:favour:-1"
                    data-counter-step="favour" data-step="-1">−1</button>
            <button type="submit" id="favour-plus" name="intent"
                    value="counter-step:favour:+1"
                    data-counter-step="favour" data-step="+1">+1</button>
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

function type(id, value) {
    const input = document.getElementById(id);
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("post-battle Mission results", () => {
    it("adds up the lines of credits as they are typed", () => {
        type("second", "15");
        expect(form.querySelector("[data-credit-total]").textContent).toBe(
            "+55¢",
        );
        type("second", "not yet");
        expect(form.querySelector("[data-credit-total]").textContent).toBe(
            "+40¢",
        );
    });

    it("leaves a negative or broken amount out of the total", () => {
        type("second", "-40");
        expect(form.querySelector("[data-credit-total]").textContent).toBe(
            "+40¢",
        );
        type("second", "1.5");
        expect(form.querySelector("[data-credit-total]").textContent).toBe(
            "+40¢",
        );
    });

    it("steps a counter in the page without a request", () => {
        const submitted = vi.fn((event) => event.preventDefault());
        form.addEventListener("submit", submitted);
        const plus = document.getElementById("favour-plus");

        plus.click();
        plus.click();

        expect(document.getElementById("favour").value).toBe("2");
        expect(document.getElementById("favour-after").textContent).toBe("3");
        expect(submitted).not.toHaveBeenCalled();
        expect(fetch).not.toHaveBeenCalled();
    });

    it("stops −1 where the counter would go below 0", () => {
        const minus = document.getElementById("favour-minus");

        minus.click();

        expect(document.getElementById("favour").value).toBe("-1");
        expect(document.getElementById("favour-after").textContent).toBe("0");
        expect(minus.disabled).toBe(true);
        minus.disabled = false;
        minus.click();
        expect(document.getElementById("favour").value).toBe("-1");
    });

    it("shows where a counter lands after a typed change", () => {
        type("rep", "-2");
        expect(document.getElementById("rep-after").textContent).toBe("3");
        type("rep", "");
        expect(document.getElementById("rep-after").textContent).toBe("5");
    });
});
