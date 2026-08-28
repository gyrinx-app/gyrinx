/*
 * Busy controls.
 *
 * A click that starts work — a form that posts, a link to a page the server
 * has to build, an htmx request — leaves the control that started it looking
 * busy and refuses further clicks until the work ends. On a slow post that is
 * the difference between a page that looks broken and one that is plainly
 * working, and it is what stops a second click buying a second of something.
 *
 * Nothing here calls preventDefault: every form still submits and every link
 * still navigates exactly as it would with this file missing, so a failure to
 * load costs the affordance and nothing else.
 *
 * The state is one attribute, `data-busy="on"`, written here and drawn by the
 * design library's stylesheet (n26/designsystem/assets/app.css) — this file
 * holds no styling and reads none. A control that must never go busy carries
 * `data-busy="off"` from its call site; so does a form, which opts out
 * everything inside it.
 *
 * What is deliberately left alone: a button that only moves something on
 * screen — a tab, a filter, a disclosure — starts no work and never goes
 * busy. The rules below reach a control through a submit, an htmx request or
 * a navigation, so those buttons are missed by construction rather than by a
 * list this file would have to keep.
 */
(function () {
    "use strict";

    /* An htmx control asks for its own page fragment: nothing navigates, so
     * the busy state has to be taken off again when the request settles. */
    var HTMX_VERBS =
        "[hx-get],[hx-post],[hx-put],[hx-patch],[hx-delete]," +
        "[data-hx-get],[data-hx-post],[data-hx-put],[data-hx-patch],[data-hx-delete]";

    /* Every control a form sends itself with. A <button> in a form with no
     * type at all is a submit — HTML's default, and easy to forget. */
    var SUBMITS =
        'button[type="submit"], input[type="submit"], button:not([type])';

    function isHtmx(element) {
        return !!element && !!element.closest && !!element.closest(HTMX_VERBS);
    }

    function optedOut(element) {
        return !!element.closest('[data-busy="off"]');
    }

    function markBusy(element) {
        if (!element || optedOut(element)) return;
        /* The spinner is a pseudo-element, and a replaced element has none:
         * an <input type="submit"> marked busy would lose its label and show
         * nothing in its place. It is still disabled, just not painted. */
        if (!element.matches("button, a")) return;
        if (element.getAttribute("data-busy") === "on") return;

        element.setAttribute("data-busy", "on");
        element.setAttribute("aria-busy", "true");
        /* What the script put on is what the script takes off. A page can
         * carry the state in its own markup — the gallery's demo does — and a
         * sweep that could not tell the two apart would quietly undo it. */
        element.setAttribute("data-busy-applied", "");
    }

    function disable(element) {
        /* A control disabled before the click is not ours to hand back. */
        if (element.disabled) return;

        /* After the current task, so the clicked button's name and value are
         * still part of what the form sends: a disabled control is not
         * submitted, and the equip screens tell buy from sell by exactly
         * that pair. */
        element.dataset.busyDisabled = "pending";
        window.setTimeout(function () {
            /* A request that settled inside the tick has already given the
             * button back; disabling it now would strand it. */
            if (element.dataset.busyDisabled !== "pending") return;
            element.dataset.busyDisabled = "yes";
            element.disabled = true;
        }, 0);
    }

    function release(element) {
        if (element.hasAttribute("data-busy-applied")) {
            element.removeAttribute("data-busy-applied");
            element.removeAttribute("data-busy");
            element.removeAttribute("aria-busy");
        }
        if (element.dataset.busyDisabled) {
            delete element.dataset.busyDisabled;
            element.disabled = false;
        }
    }

    /* Undo every busy control at or inside `root`. Scoped rather than
     * document-wide: one settled request must not hand back the buttons of a
     * form that is still posting somewhere else on the page. */
    function releaseWithin(root) {
        if (!root) return;
        if (root.nodeType === 1) release(root);
        root.querySelectorAll(
            "[data-busy-applied], [data-busy-disabled]",
        ).forEach(release);
    }

    /*
     * A form that posts.
     *
     * The submitter is the button that goes busy; every control that could
     * send the form is disabled, so a second click lands on nothing whichever
     * button it lands on.
     *
     * A submit something else has already handled (`defaultPrevented`) is left
     * alone — a script that stopped the submission owns what happens next, and
     * a control marked busy for a request nobody sent would spin for ever. The
     * exception is htmx, which prevents the default *because* it is sending
     * the form; those clear on the settle events below.
     */
    document.addEventListener("submit", function (event) {
        var form = event.target;
        var submitter = event.submitter;
        var handledByHtmx = isHtmx(form) || isHtmx(submitter);

        if (event.defaultPrevented && !handledByHtmx) return;
        if (optedOut(form)) return;

        markBusy(submitter);
        form.querySelectorAll(SUBMITS).forEach(function (control) {
            /* An opted-out control is out of all of it: a button left alive on
             * purpose is one the reader is meant to still be able to click. */
            if (!optedOut(control)) disable(control);
        });
    });

    /*
     * A link to a page the server draws.
     *
     * Only link *buttons*: `rounded-button` is what the library puts on both
     * shapes of <c-ui.button>, and app.css already reads it as "this is a
     * button". A plain link in a sentence stays a plain link.
     *
     * Everything that is not a plain navigation of this tab is passed over —
     * a modified click opens elsewhere, a fragment goes nowhere the server is
     * involved in, and a download leaves the page exactly where it is, which
     * would strand the button spinning.
     */
    document.addEventListener("click", function (event) {
        if (event.defaultPrevented || event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
            return;

        var link = event.target.closest("a[href].rounded-button");
        if (!link || link.hasAttribute("download")) return;
        if (link.target && link.target !== "_self") return;

        var href = link.getAttribute("href");
        if (!href || href.charAt(0) === "#") return;

        var destination;
        try {
            destination = new URL(link.href);
        } catch (error) {
            return;
        }
        if (
            destination.protocol !== "http:" &&
            destination.protocol !== "https:"
        )
            return;
        /* A fragment on the page already open: the browser scrolls, it does
         * not fetch. A link to the same address with no fragment is a
         * reload, which does. */
        if (
            destination.hash &&
            destination.href.split("#")[0] ===
                window.location.href.split("#")[0]
        )
            return;

        markBusy(link);
    });

    /*
     * htmx.
     *
     * A control that fetches its own fragment is marked when the request goes
     * out and released when it settles, in whatever way it settles. What sends
     * the request is not always a button: a form sends its own, and a request
     * made from script has no source element at all, so the element here is
     * offered as it comes and markBusy keeps the ones it can paint. A form's
     * button is already busy from the submit above, which is the control the
     * reader is watching.
     *
     * The scope released is the whole form where there is one: the submit
     * above disabled every control in it, not just the one that went busy.
     */
    document.addEventListener("htmx:beforeRequest", function (event) {
        markBusy(event.detail && event.detail.elt);
    });

    [
        "htmx:afterRequest",
        "htmx:responseError",
        "htmx:sendError",
        "htmx:timeout",
        "htmx:abort",
    ].forEach(function (name) {
        document.addEventListener(name, function (event) {
            var element = (event.detail && event.detail.elt) || document.body;
            releaseWithin(
                (element.closest && element.closest("form")) || element,
            );
        });
    });

    /*
     * Back.
     *
     * A page restored from the back/forward cache comes back exactly as it was
     * left — mid-submission, with its buttons disabled and spinning. Nothing
     * else undoes that, so the whole document is handed back here.
     */
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) releaseWithin(document);
    });
})();
