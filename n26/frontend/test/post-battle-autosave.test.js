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

function htmxEvent(type, detail) {
    const event = new CustomEvent(type, {
        bubbles: true,
        cancelable: true,
        detail,
    });
    form.elements.credits.dispatchEvent(event);
    return event;
}

describe("post-battle in-place updates", () => {
    it("waits for a running autosave before sending an update", async () => {
        let finish;
        fetch.mockReturnValueOnce(
            new Promise((resolve) => {
                finish = resolve;
            }),
        );
        form.elements.credits.value = "75";
        form.elements.credits.dispatchEvent(
            new Event("input", { bubbles: true }),
        );
        await vi.advanceTimersByTimeAsync(900);
        expect(fetch).toHaveBeenCalledTimes(1);

        const issueRequest = vi.fn();
        const confirm = htmxEvent("htmx:confirm", { issueRequest });
        expect(confirm.defaultPrevented).toBe(true);
        await vi.advanceTimersByTimeAsync(0);
        expect(issueRequest).not.toHaveBeenCalled();

        finish(
            new Response(
                JSON.stringify({
                    revision: 4,
                    generation: "4",
                    saved: "18:00:00",
                }),
                { status: 200 },
            ),
        );
        await vi.advanceTimersByTimeAsync(0);
        expect(issueRequest).toHaveBeenCalledWith(true);
    });

    it("saves input that arrives while an update is in flight", async () => {
        htmxEvent("htmx:beforeRequest", {});
        form.elements.credits.value = "75";
        form.elements.credits.dispatchEvent(
            new Event("input", { bubbles: true }),
        );
        await vi.advanceTimersByTimeAsync(5000);
        expect(fetch).not.toHaveBeenCalled();
        expect(unloadWarning()).toBe(true);

        // The out-of-band swap writes the server's line first.
        status.textContent = "Draft saved 18:00";
        fetch.mockResolvedValueOnce(
            new Response(
                JSON.stringify({
                    revision: 5,
                    generation: "4",
                    saved: "18:01:00",
                }),
                { status: 200 },
            ),
        );
        htmxEvent("htmx:afterRequest", { successful: true });
        expect(status.textContent).toBe("Unsaved changes");
        await vi.advanceTimersByTimeAsync(900);
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(fetch.mock.calls[0][1].body.get("credits")).toBe("75");
        expect(status.textContent).toBe("Draft saved 18:01:00");
    });

    it("keeps the server's saved line when nothing changed meanwhile", async () => {
        htmxEvent("htmx:beforeRequest", {});
        status.textContent = "Draft saved 18:00";
        htmxEvent("htmx:afterRequest", { successful: true });
        expect(status.textContent).toBe("Draft saved 18:00");
        await vi.advanceTimersByTimeAsync(5000);
        expect(fetch).not.toHaveBeenCalled();
    });

    it("shows the server's reason when an update is refused", async () => {
        htmxEvent("htmx:beforeRequest", {});
        htmxEvent("htmx:afterRequest", {
            successful: false,
            xhr: { responseText: "Someone else saved this draft." },
        });
        expect(status.textContent).toBe(
            "Someone else saved this draft. Your entries are still here. Use Save draft to retry.",
        );
    });
});

describe("live preview versions", () => {
    it("publishes a current preview and review hash after autosave", async () => {
        form.insertAdjacentHTML(
            "beforeend",
            '<input name="review" value="old">',
        );
        const updates = vi.fn();
        form.addEventListener("post-battle:preview", updates);
        const preview = {
            rows: [{ label: "Reputation", value: "5 → 8" }],
            models: [],
            territory: null,
        };
        await editAndAutosave(
            Response.json({
                revision: 5,
                generation: 6,
                review: "new",
                saved: "12:30",
                preview,
            }),
        );
        expect(form.elements.review.value).toBe("new");
        expect(updates.mock.calls.at(-1)[0].detail).toEqual({
            state: "ready",
            preview,
        });
    });

    it("does not display an older response while newer input awaits saving", async () => {
        let finish;
        fetch.mockReturnValueOnce(
            new Promise((resolve) => {
                finish = resolve;
            }),
        );
        const updates = vi.fn();
        form.addEventListener("post-battle:preview", updates);
        form.elements.credits.dispatchEvent(
            new Event("input", { bubbles: true }),
        );
        await vi.advanceTimersByTimeAsync(900);
        form.elements.credits.value = "80";
        form.elements.credits.dispatchEvent(
            new Event("input", { bubbles: true }),
        );
        finish(
            Response.json({
                revision: 5,
                generation: 4,
                saved: "12:30",
                preview: { rows: [{ value: "10" }] },
            }),
        );
        await vi.advanceTimersByTimeAsync(0);
        expect(updates.mock.calls.at(-1)[0].detail).toEqual({
            state: "updating",
        });
        fetch.mockResolvedValueOnce(
            Response.json({
                revision: 6,
                generation: 4,
                saved: "12:31",
                preview: { rows: [{ value: "80" }] },
            }),
        );
        await vi.advanceTimersByTimeAsync(900);
        expect(fetch.mock.calls[1][1].body.get("revision")).toBe("5");
        expect(fetch.mock.calls[1][1].body.get("credits")).toBe("80");
        expect(updates.mock.calls.at(-1)[0].detail).toEqual({
            state: "ready",
            preview: { rows: [{ value: "80" }] },
        });
    });

    it("waits for a dirty preview before applying and blocks failed saves", async () => {
        form.insertAdjacentHTML(
            "beforeend",
            '<button name="intent" value="apply">Apply</button>',
        );
        const apply = form.querySelector('[value="apply"]');
        const submit = vi
            .spyOn(form, "requestSubmit")
            .mockImplementation(() => {});
        fetch.mockResolvedValueOnce(
            Response.json({ revision: 5, generation: 4, saved: "12:30" }),
        );
        form.elements.credits.dispatchEvent(
            new Event("input", { bubbles: true }),
        );
        const event = new SubmitEvent("submit", {
            cancelable: true,
            submitter: apply,
        });
        form.dispatchEvent(event);
        expect(event.defaultPrevented).toBe(true);
        expect(submit).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(0);
        expect(submit).toHaveBeenCalledWith(apply);
        submit.mockClear();
        await editAndAutosave(
            Response.json({ error: "Refused" }, { status: 409 }),
        );
        const failed = new SubmitEvent("submit", {
            cancelable: true,
            submitter: apply,
        });
        form.dispatchEvent(failed);
        expect(failed.defaultPrevented).toBe(true);
        expect(submit).not.toHaveBeenCalled();
        expect(status.textContent).toContain("before applying results");
    });
});
