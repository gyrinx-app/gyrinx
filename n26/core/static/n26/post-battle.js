"use strict";

// Saving only persists the form. Field shape and gameplay validation stay on the server.
(() => {
    const form = document.getElementById("post-battle-form");
    if (!form) return;
    // An in-place update replaces this line, so look it up each time.
    const status = {
        set textContent(text) {
            document.getElementById("draft-save-status").textContent = text;
        },
    };
    let timer;
    let saving = null;
    let dirty = false;
    let waiting = false;
    let submitting = false;
    let failed = false;
    // An in-place update of one model's section saves the whole form too.
    // Autosave waits for it, and it waits for an autosave already running,
    // so two saves never race on the same draft version.
    let refreshing = null;
    let refreshed = null;

    const save = async () => {
        if (saving || waiting || submitting || failed || !dirty) return;
        if (refreshing) return;
        dirty = false;
        status.textContent = "Saving draft…";
        const body = new FormData(form);
        body.set("intent", "autosave");
        saving = fetch(form.action, {
            method: "POST",
            body,
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        })
            .then(async (response) => {
                const result = await response.json().catch(() => null);
                if (!response.ok || !result)
                    throw new Error(
                        result?.error || "Draft could not be saved.",
                    );
                form.elements.revision.value = result.revision;
                form.elements.generation.value = result.generation;
                status.textContent = dirty
                    ? "Unsaved changes"
                    : `Draft saved ${result.saved}`;
            })
            .catch((error) => {
                failed = true;
                dirty = true;
                status.textContent = `${error.message} Your entries are still here. Use Save draft to retry.`;
            })
            .finally(() => {
                saving = null;
                if (dirty && !waiting && !submitting && !failed)
                    timer = window.setTimeout(save, 900);
            });
        await saving;
    };

    // The server renders the XP toolbar. This redraws it from the same
    // templates while models are ticked, so it never waits for a save.
    const plural = (element, count) =>
        (count === 1 ? element.dataset.one : element.dataset.many).replace(
            "{n}",
            count,
        );
    const redrawXpToolbar = () => {
        const toolbar = form.querySelector("[data-xp-toolbar]");
        if (!toolbar) return;
        const selected = [
            ...form.querySelectorAll("input[data-xp-participant]:checked"),
        ];
        const entered = selected
            .filter((box) => !("xpBlocked" in box.dataset))
            .map((box) => {
                const value = document.getElementById(
                    box.dataset.xpParticipant,
                )?.value;
                const number = Number(value || 0);
                return Number.isInteger(number) ? number : 1;
            });
        const count = toolbar.querySelector("[data-xp-count]");
        count.textContent = plural(count, selected.length);
        for (const button of toolbar.querySelectorAll("[data-xp-step]")) {
            button.setAttribute("aria-label", plural(button, selected.length));
            button.disabled =
                button.dataset.xpStep === "+1"
                    ? !entered.length
                    : entered.every((value) => value <= 0);
        }
    };

    form.addEventListener("htmx:confirm", (event) => {
        event.preventDefault();
        window.clearTimeout(timer);
        const issue = async () => {
            if (saving) await saving;
            if (failed || submitting) return;
            event.detail.issueRequest(true);
        };
        issue();
    });
    form.addEventListener("htmx:beforeRequest", () => {
        window.clearTimeout(timer);
        dirty = false;
        status.textContent = "Saving draft…";
        refreshing = new Promise((resolve) => {
            refreshed = resolve;
        });
    });
    form.addEventListener("htmx:afterRequest", (event) => {
        if (!event.detail.successful) {
            failed = true;
            dirty = true;
            const message =
                event.detail.xhr?.responseText || "Draft could not be saved.";
            status.textContent = `${message} Your entries are still here. Use Save draft to retry.`;
        }
        refreshed?.();
        refreshing = null;
        redrawXpToolbar();
    });

    form.addEventListener("input", () => {
        redrawXpToolbar();
        dirty = true;
        window.clearTimeout(timer);
        if (!failed) {
            status.textContent = "Unsaved changes";
            timer = window.setTimeout(save, 900);
        }
    });
    form.addEventListener("submit", async (event) => {
        if (waiting || submitting) {
            event.preventDefault();
            event.stopImmediatePropagation();
            return;
        }
        window.clearTimeout(timer);
        if (saving || refreshing) {
            event.preventDefault();
            event.stopImmediatePropagation();
            waiting = true;
            const button = event.submitter;
            await saving;
            await refreshing;
            waiting = false;
            form.requestSubmit(button);
        } else {
            submitting = true;
        }
    });
    window.addEventListener("beforeunload", (event) => {
        if ((dirty || saving || refreshing || waiting) && !submitting) {
            event.preventDefault();
            event.returnValue = "";
        }
    });
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            waiting = false;
            submitting = false;
        }
    });
    document.getElementById("report-errors")?.focus();
})();
