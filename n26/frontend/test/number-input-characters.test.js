import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The browser inserts what a cancelled event would have typed only when the
// event goes through, so these tests assert the cancel.

let listeners;

beforeEach(async () => {
    vi.resetModules();
    listeners = vi.spyOn(document, "addEventListener");
    await import("../../../gyrinx/site/static/platform/js/number-input-characters.js");
});

afterEach(() => {
    for (const [type, listener, options] of listeners.mock.calls) {
        document.removeEventListener(type, listener, options);
    }
    document.body.replaceChildren();
    vi.restoreAllMocks();
});

function field(attributes = {}, type = "number") {
    const input = document.createElement("input");
    input.type = type;
    for (const [name, value] of Object.entries(attributes)) {
        input.setAttribute(name, value);
    }
    document.body.append(input);
    return input;
}

function press(target, key, init = {}) {
    const event = new KeyboardEvent("keydown", {
        key,
        bubbles: true,
        cancelable: true,
        ...init,
    });
    target.dispatchEvent(event);
    return event.defaultPrevented;
}

function insert(target, data) {
    const event = new InputEvent("beforeinput", {
        data,
        inputType: "insertText",
        bubbles: true,
        cancelable: true,
    });
    target.dispatchEvent(event);
    return event.defaultPrevented;
}

function paste(target, text) {
    const event = new Event("paste", { bubbles: true, cancelable: true });
    event.clipboardData = { getData: () => text };
    target.dispatchEvent(event);
    return event.defaultPrevented;
}

describe("number input characters", () => {
    it("refuses e, E and + in a number field", () => {
        const input = field({ min: "0" });

        for (const key of ["e", "E", "+"]) {
            expect(press(input, key), key).toBe(true);
            expect(insert(input, key), key).toBe(true);
        }
    });

    it("takes digits", () => {
        const input = field({ min: "0" });

        for (const key of "0123456789") {
            expect(press(input, key), key).toBe(false);
            expect(insert(input, key), key).toBe(false);
        }
    });

    it("leaves editing and shortcut keys alone", () => {
        const input = field({ min: "0" });

        for (const key of ["Backspace", "Delete", "ArrowUp", "Tab", "Enter"]) {
            expect(press(input, key), key).toBe(false);
        }
        expect(press(input, "a", { ctrlKey: true })).toBe(false);
        expect(press(input, "v", { metaKey: true })).toBe(false);
    });

    it("ignores a keydown that carries no key", () => {
        // Chrome's autofill sends keydown events like this.
        const input = field({ min: "0" });
        const errors = [];
        const onError = (event) => errors.push(event.error);
        const event = new Event("keydown", { bubbles: true, cancelable: true });

        window.addEventListener("error", onError);
        input.dispatchEvent(event);
        window.removeEventListener("error", onError);

        expect(errors).toEqual([]);
        expect(event.defaultPrevented).toBe(false);
    });

    it("keeps a minus sign and a decimal point, even where the field has no use for them", () => {
        // Dropping them would turn -5 into 5 and 2.5 into 25 without a word.
        const input = field({ min: "0" });

        for (const key of ["-", "."]) {
            expect(press(input, key), key).toBe(false);
            expect(insert(input, key), key).toBe(false);
        }
    });

    it("cancels a paste with e, E or + in it", () => {
        const input = field({ min: "0" });

        expect(paste(input, "25")).toBe(false);
        expect(paste(input, "-25")).toBe(false);
        expect(paste(input, "1e3")).toBe(true);
        expect(paste(input, "1E3")).toBe(true);
        expect(paste(input, "+25")).toBe(true);
    });

    it("leaves deletions alone", () => {
        const input = field({ min: "0" });
        const event = new InputEvent("beforeinput", {
            inputType: "deleteContentBackward",
            bubbles: true,
            cancelable: true,
        });

        input.dispatchEvent(event);

        expect(event.defaultPrevented).toBe(false);
    });

    it("leaves other fields alone", () => {
        const input = field({}, "text");

        expect(press(input, "e")).toBe(false);
        expect(insert(input, "e")).toBe(false);
        expect(paste(input, "1e3")).toBe(false);
    });
});
