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

    // −1 XP and +1 XP change the ticked models' XP here, like typing
    // would, and the autosave keeps it. Without scripts they post the form.
    form.addEventListener("click", (event) => {
        const button = event.target.closest?.("button[data-xp-step]");
        if (!button || !form.contains(button)) return;
        event.preventDefault();
        const step = button.dataset.xpStep === "-1" ? -1 : 1;
        for (const box of form.querySelectorAll(
            "input[data-xp-participant]:checked",
        )) {
            if ("xpBlocked" in box.dataset) continue;
            const input = document.getElementById(box.dataset.xpParticipant);
            if (!input) continue;
            const number = Number(String(input.value || "").trim() || 0);
            // A value that is not a whole number is left for the player.
            if (!Number.isInteger(number)) continue;
            input.value = String(Math.max(0, number + step));
            input.dispatchEvent(new Event("input", { bubbles: true }));
        }
    });

    // Mission results: the credits total and each counter's "After" follow
    // what is typed. The server's figures replace them on the next update.
    const whole = (value) => {
        const number = Number(String(value || "").trim() || 0);
        return Number.isInteger(number) ? number : 0;
    };
    // An amount of credits is a whole number from 0 up. Anything else is
    // refused on saving, so it adds nothing to the total meanwhile.
    const amount = (value) => {
        const text = String(value || "").trim();
        return /^\d+$/.test(text) && Number(text) <= 1000000 ? Number(text) : 0;
    };
    const redrawMission = () => {
        const total = form.querySelector("[data-credit-total]");
        if (total) {
            const sum = [
                ...form.querySelectorAll("input[data-credit-amount]"),
            ].reduce((running, input) => running + amount(input.value), 0);
            total.textContent = `+${sum}¢`;
        }
        for (const input of form.querySelectorAll("input[data-counter-base]")) {
            const change = whole(input.value);
            const landing = Number(input.dataset.counterBase) + change;
            const after = document.getElementById(
                input.getAttribute("aria-describedby"),
            );
            if (after) after.textContent = landing;
            const limit = Number(input.dataset.counterLimit || 1000);
            for (const button of form.querySelectorAll(
                `button[data-counter-step="${input.id}"]`,
            )) {
                button.disabled =
                    button.dataset.step === "-1"
                        ? landing <= 0 || change <= -limit
                        : change >= limit;
            }
        }
    };

    // A counter's −1 and +1 step its change here, like typing would; the
    // autosave keeps it. Without scripts they post the form.
    form.addEventListener("click", (event) => {
        const button = event.target.closest?.("button[data-counter-step]");
        if (!button || !form.contains(button)) return;
        event.preventDefault();
        const input = document.getElementById(button.dataset.counterStep);
        if (!input) return;
        const number = Number(String(input.value || "").trim() || 0);
        if (!Number.isInteger(number)) return;
        const next = number + (button.dataset.step === "-1" ? -1 : 1);
        const limit = Number(input.dataset.counterLimit || 1000);
        if (Math.abs(next) > limit) return;
        if (Number(input.dataset.counterBase) + next < 0) return;
        input.value = next ? String(next) : "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
    });

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
    // A section redrawn in place (a result picked, a status or equipment
    // chosen, a result added or removed) never locks a control or moves
    // focus. Whatever the player types into it while the update is in
    // flight is written into the redrawn copy, in place, and the focused
    // field keeps focus and its caret.
    const typed = (element) =>
        element.matches("textarea") ||
        (element.matches("input") &&
            ![
                "hidden",
                "button",
                "submit",
                "reset",
                "checkbox",
                "radio",
            ].includes(element.type));
    const reading = (element) =>
        element.type === "checkbox" || element.type === "radio"
            ? element.checked
            : element.value;
    const fields = (root) =>
        [...root.querySelectorAll("input, textarea")].filter(
            (element) =>
                element.id &&
                (typed(element) ||
                    element.type === "checkbox" ||
                    element.type === "radio"),
        );
    let section = "";
    let sent = new Map();
    let carried = new Map();
    let restore = null;
    form.addEventListener("htmx:beforeRequest", (event) => {
        window.clearTimeout(timer);
        dirty = false;
        const target = event.detail.target;
        section = target?.id || "";
        sent = new Map(
            target
                ? fields(target).map((element) => [
                      element.id,
                      reading(element),
                  ])
                : [],
        );
        carried = new Map();
        restore = null;
        status.textContent = "Saving draft…";
        refreshing = new Promise((resolve) => {
            refreshed = resolve;
        });
    });
    form.addEventListener("htmx:beforeSwap", (event) => {
        const target = event.detail.target;
        if (!section || target?.id !== section) return;
        for (const element of fields(target)) {
            if (reading(element) !== sent.get(element.id))
                carried.set(element.id, reading(element));
        }
        const active = document.activeElement;
        restore =
            active && active.id && target.contains(active)
                ? {
                      id: active.id,
                      start: typed(active) ? active.selectionStart : null,
                      end: typed(active) ? active.selectionEnd : null,
                      direction: typed(active)
                          ? active.selectionDirection
                          : null,
                  }
                : null;
    });
    // Runs once the new copy is in the page, before anything else reads it.
    form.addEventListener("htmx:afterSwap", (event) => {
        if (!section || event.target?.id !== section) return;
        for (const [id, value] of carried) {
            const element = document.getElementById(id);
            if (!element || !event.target.contains(element)) continue;
            if (element.type === "checkbox" || element.type === "radio")
                element.checked = value;
            else element.value = value;
            dirty = true;
        }
        carried = new Map();
        const next = restore && document.getElementById(restore.id);
        if (next && event.target.contains(next)) {
            if (document.activeElement !== next)
                next.focus({ preventScroll: true });
            if (restore.start !== null && restore.start !== undefined) {
                try {
                    next.setSelectionRange(
                        restore.start,
                        restore.end,
                        restore.direction || "none",
                    );
                } catch {
                    // Number inputs have no caret to put back.
                }
            }
        }
        restore = null;
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
        section = "";
        sent = new Map();
        redrawXpToolbar();
        redrawMission();
        // Entries typed elsewhere while the update was in flight were not
        // in it. The server's "Draft saved" line would be wrong about them.
        if (dirty && !failed) {
            status.textContent = "Unsaved changes";
            window.clearTimeout(timer);
            timer = window.setTimeout(save, 900);
        }
    });

    form.addEventListener("input", () => {
        redrawXpToolbar();
        redrawMission();
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
