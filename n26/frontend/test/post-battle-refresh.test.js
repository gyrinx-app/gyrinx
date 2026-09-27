import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A model's section is redrawn in place by htmx. These tests play htmx's
// part: the events it sends, and the swap of the section for the server's
// copy.

let listeners;
let docListeners;
let form;

const SECTION = (xp = "1", note = "") => `
    <fieldset id="result-a" hx-target="this">
        <input type="checkbox" id="a-participated" checked>
        <input id="a-xp" name="a-xp" type="number" value="${xp}">
        <select id="a-status"><option value="">Set from results</option></select>
        <button type="submit" id="a-plus" name="intent" value="counter:+1">+1</button>
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
    docListeners = vi.spyOn(document, "addEventListener");
    document.body.innerHTML = `
        <form id="post-battle-form" action="/n26/post-battle/draft/">
            <input name="revision" value="3">
            <input name="generation" value="4">
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
    for (const [type, listener, options] of docListeners.mock.calls) {
        document.removeEventListener(type, listener, options);
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
        new CustomEvent("htmx:afterRequest", {
            bubbles: true,
            detail: { successful: true, target: section() },
        }),
    );
}

function type(element, value) {
    element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("redrawing a model's section", () => {
    it("locks only its buttons and selects while the update runs", () => {
        $("a-plus").focus();
        send($("a-plus"));

        expect($("a-plus").disabled).toBe(true);
        expect($("a-status").disabled).toBe(true);
        expect($("a-note").disabled).toBe(false);
        expect($("a-xp").disabled).toBe(false);
        expect($("save").disabled).toBe(false);
    });

    it("keeps a note typed during the update and focuses the note", () => {
        $("a-plus").focus();
        send($("a-plus"));
        $("a-note").focus();
        type($("a-note"), "Took the bridge");
        $("a-note").setSelectionRange(4, 4);

        swap(SECTION("1", ""));

        expect($("a-note").value).toBe("Took the bridge");
        expect(document.activeElement).toBe($("a-note"));
        expect($("a-note").selectionStart).toBe(4);
        expect(document.activeElement).not.toBe($("a-plus"));
        expect($("a-plus").disabled).toBe(false);
    });

    it("saves the carried note with the next autosave", async () => {
        fetch.mockResolvedValue(
            new Response(
                JSON.stringify({ revision: 4, generation: 5, saved: "12:00" }),
            ),
        );
        $("a-plus").focus();
        send($("a-plus"));
        $("a-note").focus();
        type($("a-note"), "Took the bridge");
        swap(SECTION());

        await vi.advanceTimersByTimeAsync(900);

        expect(fetch).toHaveBeenCalledTimes(1);
        expect(fetch.mock.calls[0][1].body.get("a-note")).toBe(
            "Took the bridge",
        );
    });

    it("gives focus back to the button only while the player stays on it", () => {
        $("a-plus").focus();
        send($("a-plus"));
        // Disabling the focused button drops focus to the page.
        $("a-plus").blur();

        swap(SECTION("2"));

        expect(document.activeElement).toBe($("a-plus"));
    });

    it("leaves focus on a field outside the section the player moved to", () => {
        $("a-plus").focus();
        send($("a-plus"));
        $("save").focus();

        swap(SECTION("2"));

        expect(document.activeElement).toBe($("save"));
    });

    it("takes the server's values for fields nobody typed into", () => {
        $("a-plus").focus();
        send($("a-plus"));

        swap(SECTION("2", "server note"));

        expect($("a-xp").value).toBe("2");
        expect($("a-note").value).toBe("server note");
    });

    it("unlocks the section when the update fails", () => {
        $("a-plus").focus();
        send($("a-plus"));
        section().dispatchEvent(
            new CustomEvent("htmx:afterRequest", {
                bubbles: true,
                detail: { successful: false, xhr: { responseText: "" } },
            }),
        );

        expect($("a-plus").disabled).toBe(false);
        expect($("a-status").disabled).toBe(false);
    });
});
