import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A model's section is redrawn in place by htmx. These tests play htmx's
// part: the events it sends, and the swap of the section for the server's
// copy.

let listeners;
let form;

const SECTION = (xp = "1", note = "") => `
    <fieldset id="result-a" hx-target="this">
        <input type="checkbox" id="a-participated" name="a-participated"
               data-xp-participant="a-xp" checked>
        <input id="a-xp" name="a-xp" type="number" value="${xp}">
        <select id="a-status" name="a-status"><option value="">Set from results</option></select>
        <button type="submit" id="a-add" name="intent" value="add-effect:a">Add</button>
        <textarea id="a-note" name="a-note">${note}</textarea>
    </fieldset>
`;

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
                <p data-xp-count data-one="{n} selected" data-many="{n} selected"></p>
                <button type="submit" id="xp-minus" name="intent" value="xp-step:-1"
                        data-xp-step="-1" data-one="-" data-many="-">−1 XP</button>
                <button type="submit" id="xp-plus" name="intent" value="xp-step:+1"
                        data-xp-step="+1" data-one="+" data-many="+">+1 XP</button>
            </div>
            <button type="submit" id="save" name="intent" value="save">Save draft</button>
            ${SECTION()}
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

const section = () => document.getElementById("result-a");
const $ = (id) => document.getElementById(id);

function send(elt) {
    elt.dispatchEvent(
        new CustomEvent("htmx:beforeRequest", {
            bubbles: true,
            detail: { elt, target: section() },
        }),
    );
}

// What htmx does with the response: beforeSwap on the old copy, the swap,
// afterSwap on the new copy, then afterRequest.
function swap(html) {
    const old = section();
    old.dispatchEvent(
        new CustomEvent("htmx:beforeSwap", {
            bubbles: true,
            detail: { target: old },
        }),
    );
    old.outerHTML = html;
    section().dispatchEvent(
        new CustomEvent("htmx:afterSwap", { bubbles: true, detail: {} }),
    );
    form.dispatchEvent(
        new CustomEvent("htmx:afterRequest", {
            bubbles: true,
            detail: { successful: true },
        }),
    );
}

// Type at the caret, as a keyboard does.
function typeAtCaret(element, text) {
    for (const character of text) {
        const at = element.selectionStart;
        element.value =
            element.value.slice(0, at) +
            character +
            element.value.slice(element.selectionEnd);
        element.setSelectionRange(at + 1, at + 1);
        element.dispatchEvent(new Event("input", { bubbles: true }));
    }
}

describe("redrawing a model's section", () => {
    it("never disables a control or moves focus while the update runs", () => {
        $("a-status").focus();
        send($("a-status"));

        for (const element of section().querySelectorAll(
            "input, select, button, textarea",
        )) {
            expect(element.disabled).toBe(false);
        }
        expect(document.activeElement).toBe($("a-status"));
    });

    it("keeps a note typed mid-redraw, in order, with the caret after it", () => {
        const focusedButtons = [];
        form.addEventListener("focusin", (event) => {
            if (event.target.matches("button"))
                focusedButtons.push(event.target);
        });
        const clicked = vi.fn();
        form.addEventListener("click", (event) => {
            if (event.target.matches("button")) clicked(event.target);
        });
        $("a-status").focus();
        send($("a-status"));
        $("a-note").focus();
        $("a-note").setSelectionRange(0, 0);
        typeAtCaret($("a-note"), "Took the ");

        swap(SECTION("1", ""));
        typeAtCaret(document.activeElement, "bridge");

        expect($("a-note").value).toBe("Took the bridge");
        expect(document.activeElement).toBe($("a-note"));
        expect($("a-note").selectionStart).toBe(15);
        expect(focusedButtons).toEqual([]);
        expect(clicked).not.toHaveBeenCalled();
    });

    it("puts the caret back inside the text, not at its end", () => {
        $("a-note").value = "Held bridge";
        send($("a-status"));
        $("a-note").focus();
        $("a-note").setSelectionRange(5, 5);
        typeAtCaret($("a-note"), "the ");

        swap(SECTION("1", ""));
        typeAtCaret(document.activeElement, "old ");

        expect($("a-note").value).toBe("Held the old bridge");
        expect($("a-note").selectionStart).toBe(13);
    });

    it("saves the carried note with the next autosave", async () => {
        fetch.mockResolvedValue(
            new Response(
                JSON.stringify({ revision: 4, generation: 5, saved: "12:00" }),
            ),
        );
        send($("a-status"));
        $("a-note").focus();
        typeAtCaret($("a-note"), "Took the bridge");
        swap(SECTION());

        await vi.advanceTimersByTimeAsync(900);

        expect(fetch).toHaveBeenCalledTimes(1);
        expect(fetch.mock.calls[0][1].body.get("a-note")).toBe(
            "Took the bridge",
        );
    });

    it("leaves focus outside the section where the player put it", () => {
        send($("a-status"));
        $("save").focus();

        swap(SECTION("2"));

        expect(document.activeElement).toBe($("save"));
    });

    it("takes the server's values for fields nobody typed into", () => {
        send($("a-status"));

        swap(SECTION("2", "server note"));

        expect($("a-xp").value).toBe("2");
        expect($("a-note").value).toBe("server note");
    });
});

describe("the XP steps", () => {
    it("change the ticked models' XP here, without a request", () => {
        const submitted = vi.fn((event) => event.preventDefault());
        form.addEventListener("submit", submitted);

        $("xp-plus").click();
        $("xp-plus").click();
        $("xp-minus").click();

        expect($("a-xp").value).toBe("2");
        expect(submitted).not.toHaveBeenCalled();
    });

    it("never take XP below 0", () => {
        $("a-xp").value = "0";

        $("xp-minus").click();

        expect($("a-xp").value).toBe("0");
    });
});
