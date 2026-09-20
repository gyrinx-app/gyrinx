"use strict";

// Saving only persists the form. Field shape and gameplay validation stay on the server.
(() => {
    const form = document.getElementById("post-battle-form");
    if (!form) return;
    const status = document.getElementById("draft-save-status");
    let timer;
    let saving = null;
    let dirty = false;
    let waiting = false;
    let submitting = false;
    let failed = false;

    const save = async () => {
        if (saving || waiting || submitting || failed || !dirty) return;
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

    form.addEventListener("input", () => {
        const count = form.querySelector("[data-participant-count]");
        if (count) {
            count.textContent = form.querySelectorAll(
                'input[name$="-participated"]:checked',
            ).length;
        }
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
        if (saving) {
            event.preventDefault();
            event.stopImmediatePropagation();
            waiting = true;
            const button = event.submitter;
            await saving;
            waiting = false;
            form.requestSubmit(button);
        } else {
            submitting = true;
        }
    });
    window.addEventListener("beforeunload", (event) => {
        if ((dirty || saving || waiting) && !submitting) {
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
