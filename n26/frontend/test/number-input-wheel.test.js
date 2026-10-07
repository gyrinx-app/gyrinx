import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Chrome changes a focused number input on wheel. jsdom does not, so these
// tests assert the event is cancelled — that is what stops the browser.

let listeners;

beforeEach(async () => {
    vi.resetModules();
    listeners = vi.spyOn(document, "addEventListener");
    await import("../../../gyrinx/site/static/platform/js/number-input-wheel.js");
});

afterEach(() => {
    for (const [type, listener, options] of listeners.mock.calls) {
        document.removeEventListener(type, listener, options);
    }
    document.body.replaceChildren();
    vi.restoreAllMocks();
});

function field(type, value = "4") {
    const input = document.createElement("input");
    input.type = type;
    input.value = value;
    document.body.append(input);
    return input;
}

function wheelOn(target, init = {}) {
    const event = new WheelEvent("wheel", {
        bubbles: true,
        cancelable: true,
        deltaY: 100,
        ...init,
    });
    target.dispatchEvent(event);
    return event;
}

describe("number input wheel", () => {
    it("cancels the wheel on a focused number field and leaves the value", () => {
        const input = field("number");
        input.focus();

        const event = wheelOn(input);

        expect(event.defaultPrevented).toBe(true);
        expect(input.value).toBe("4");
    });

    it("lets the page scroll across an unfocused number field", () => {
        const input = field("number");

        expect(wheelOn(input).defaultPrevented).toBe(false);
    });

    it("lets the page scroll while a number field is focused but the pointer is elsewhere", () => {
        const input = field("number");
        input.focus();

        expect(wheelOn(document.body).defaultPrevented).toBe(false);
    });

    it("leaves other focused fields alone", () => {
        const input = field("text", "kept");
        input.focus();

        expect(wheelOn(input).defaultPrevented).toBe(false);
    });

    it("does not cancel a pinch-zoom", () => {
        const input = field("number");
        input.focus();

        expect(wheelOn(input, { ctrlKey: true }).defaultPrevented).toBe(false);
    });

    it("registers a non-passive capturing listener", () => {
        const wheelCalls = listeners.mock.calls.filter(
            (call) => call[0] === "wheel",
        );

        expect(wheelCalls).toHaveLength(1);
        expect(wheelCalls[0][2]).toMatchObject({
            capture: true,
            passive: false,
        });
    });
});
