import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let listeners;
let form;
let status;

beforeEach(async () => {
    vi.useFakeTimers();
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn());
    listeners = vi.spyOn(window, "addEventListener");
    document.body.innerHTML = `
        <form id="post-battle-form" action="/n26/post-battle/draft/">
            <input name="revision" value="3">
            <input name="generation" value="4">
            <input name="credits" value="10">
            <button type="submit" name="intent" value="save">Save draft</button>
        </form>
        <p id="draft-save-status"></p>
    `;
    form = document.getElementById("post-battle-form");
    status = document.getElementById("draft-save-status");
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

async function editAndAutosave(response) {
    fetch.mockResolvedValueOnce(response);
    form.elements.credits.value = "75";
    form.elements.credits.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(900);
}

function unloadWarning() {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
}

describe("post-battle draft autosave", () => {
    it.each([403, 500, 502, 200])(
        "shows a clear retry message for an HTML %s response without losing entries",
        async (code) => {
            await editAndAutosave(
                new Response("<!doctype html><title>Login or error</title>", {
                    status: code,
                    headers: { "Content-Type": "text/html" },
                }),
            );

            expect(status.textContent).toBe(
                "Draft could not be saved. Your entries are still here. Use Save draft to retry.",
            );
            expect(form.elements.credits.value).toBe("75");
            expect(form.elements.revision.value).toBe("3");
            expect(form.elements.generation.value).toBe("4");
            expect(unloadWarning()).toBe(true);

            await vi.advanceTimersByTimeAsync(5000);
            expect(fetch).toHaveBeenCalledTimes(1);

            const submit = new SubmitEvent("submit", {
                cancelable: true,
                submitter: form.querySelector("button"),
            });
            expect(form.dispatchEvent(submit)).toBe(true);
            expect(unloadWarning()).toBe(false);
        },
    );

    it.each(["", "null", "{}"])(
        "uses the fallback when an error response has no useful message (%j)",
        async (body) => {
            await editAndAutosave(new Response(body, { status: 500 }));
            expect(status.textContent).toBe(
                "Draft could not be saved. Your entries are still here. Use Save draft to retry.",
            );
            expect(unloadWarning()).toBe(true);
        },
    );

    it("retains the server's validation message and the unsaved entries", async () => {
        await editAndAutosave(
            Response.json(
                {
                    error: "This draft changed in another tab. Reload it first.",
                },
                { status: 409 },
            ),
        );
        expect(status.textContent).toBe(
            "This draft changed in another tab. Reload it first. Your entries are still here. Use Save draft to retry.",
        );
        expect(form.elements.credits.value).toBe("75");
        expect(form.elements.revision.value).toBe("3");
        expect(form.elements.generation.value).toBe("4");
        expect(unloadWarning()).toBe(true);
    });

    it("updates the saved revision and clears the warning after a JSON success", async () => {
        await editAndAutosave(
            Response.json({ revision: 5, generation: 6, saved: "12:30" }),
        );
        expect(status.textContent).toBe("Draft saved 12:30");
        expect(form.elements.revision.value).toBe("5");
        expect(form.elements.generation.value).toBe("6");
        expect(unloadWarning()).toBe(false);
        const [url, options] = fetch.mock.calls[0];
        expect(url).toBe(form.action);
        expect(options.credentials).toBe("same-origin");
        expect(options.body.get("intent")).toBe("autosave");
        expect(options.body.get("credits")).toBe("75");
    });
});
