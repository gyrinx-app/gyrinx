/*
 * Prevent repeated activation while a form, navigation or htmx request is
 * pending.
 *
 * The stylesheet in n26/designsystem/assets/app.css renders data-busy="on".
 * Use data-busy="off" on a control or ancestor to opt out, and data-
 * busy="link"
 * to opt a plain link in. data-busy-replaces points to content to hide while a
 * navigation loads; its container supplies a template[data-busy-wait] spinner.
 *
 * Only repeated activations are cancelled. Buttons that change local UI state
 * are unaffected because they do not submit, navigate or send htmx requests.
 */
(function () {
    "use strict";

    /*
     * htmx updates keep the page open, so their busy state must clear when the
     * request finishes.
     */
    var HTMX_VERBS =
        "[hx-get],[hx-post],[hx-put],[hx-patch],[hx-delete]," +
        "[data-hx-get],[data-hx-post],[data-hx-put],[data-hx-patch],[data-hx-delete]";

    /* A button without a type submits its form by default. */
    var SUBMITS =
        'button[type="submit"], input[type="submit"], input[type="image"], ' +
        "button:not([type])";

    /* Event targets can be non-element nodes. */
    function element(candidate) {
        return candidate && candidate.closest && candidate.matches
            ? candidate
            : null;
    }

    function isHtmx(candidate) {
        var el = element(candidate);
        return !!el && !!el.closest(HTMX_VERBS);
    }

    function optedOut(candidate) {
        var el = element(candidate);
        return !!el && !!el.closest('[data-busy="off"]');
    }

    function markBusy(candidate) {
        var el = element(candidate);
        if (!el || optedOut(el)) return;
        /*
         * Inputs cannot display the pseudo-element spinner. They are disabled
         * separately.
         */
        if (!el.matches("button, a")) return;
        if (el.getAttribute("data-busy") === "on") return;

        /*
         * Record the previous attribute so cleanup preserves server-rendered
         * state and link opt-ins.
         */
        el.setAttribute(
            "data-busy-applied",
            el.getAttribute("data-busy") || "",
        );
        el.setAttribute("data-busy", "on");
        el.setAttribute("aria-busy", "true");
    }

    function disable(element) {
        /* Preserve controls that were already disabled. */
        if (element.disabled) return;

        /*
         * Delay disabling until the form includes the submitter's name and
         * value, which distinguish actions such as buying and selling.
         */
        element.dataset.busyDisabled = "pending";
        window.setTimeout(function () {
            /* The request may finish before this callback runs. */
            if (element.dataset.busyDisabled !== "pending") return;
            element.dataset.busyDisabled = "yes";
            element.disabled = true;
        }, 0);
    }

    function release(element) {
        if (element.hasAttribute("data-busy-applied")) {
            var before = element.getAttribute("data-busy-applied");
            element.removeAttribute("data-busy-applied");
            if (before) element.setAttribute("data-busy", before);
            else element.removeAttribute("data-busy");
            element.removeAttribute("aria-busy");
        }
        if (element.dataset.busyDisabled) {
            delete element.dataset.busyDisabled;
            element.disabled = false;
        }
    }

    /*
     * Release only a form's submit controls: other controls inside it may have
     * independent requests still pending.
     */
    function releaseRequest(root) {
        var el = element(root);
        if (!el) return;
        release(el);
        if (el.tagName === "FORM")
            el.querySelectorAll(SUBMITS).forEach(release);
    }

    function releaseEverything() {
        document
            .querySelectorAll("[data-busy-applied], [data-busy-disabled]")
            .forEach(release);
        restoreReplaced();
    }

    /*
     * Show the container's loading template in the destination area. Keep
     * hidden content for restoration from the back/forward cache.
     */
    function replaceBody(link) {
        if (optedOut(link)) return;
        var container = link.closest("[data-busy-replaces]");
        if (!container) return;

        /* Keep the visual selection and its accessible state consistent. */
        container.querySelectorAll("a.is-current").forEach(function (was) {
            was.classList.remove("is-current");
            was.removeAttribute("aria-current");
            was.setAttribute("data-busy-was-current", "");
        });
        link.classList.add("is-current");
        link.setAttribute("aria-current", "page");
        link.setAttribute("data-busy-took-current", "");

        var body = document.querySelector(
            container.getAttribute("data-busy-replaces"),
        );
        var wait = container.querySelector("template[data-busy-wait]");
        if (!body || !wait || !wait.content.firstElementChild) return;
        if (body.hasAttribute("data-busy-replaced")) return;
        Array.prototype.forEach.call(body.children, function (child) {
            child.style.setProperty("display", "none");
        });
        var shown = wait.content.firstElementChild.cloneNode(true);
        shown.setAttribute("data-busy-shown", "");
        body.setAttribute("aria-busy", "true");
        body.setAttribute("data-busy-replaced", "");
        body.appendChild(shown);
    }

    function restoreReplaced() {
        document
            .querySelectorAll("[data-busy-replaced]")
            .forEach(function (body) {
                var shown = body.querySelector("[data-busy-shown]");
                if (shown) shown.remove();
                Array.prototype.forEach.call(body.children, function (child) {
                    child.style.removeProperty("display");
                });
                body.removeAttribute("aria-busy");
                body.removeAttribute("data-busy-replaced");
            });
        document
            .querySelectorAll("[data-busy-took-current]")
            .forEach(function (link) {
                link.classList.remove("is-current");
                link.removeAttribute("aria-current");
                link.removeAttribute("data-busy-took-current");
            });
        document
            .querySelectorAll("[data-busy-was-current]")
            .forEach(function (link) {
                link.classList.add("is-current");
                link.setAttribute("aria-current", "page");
                link.removeAttribute("data-busy-was-current");
            });
    }

    /*
     * Capture repeated clicks before htmx handles them. Links remain keyboard-
     * activatable even when pointer-events is disabled.
     */
    document.addEventListener(
        "click",
        function (event) {
            var target = element(event.target);
            if (!target || !target.closest('[data-busy="on"]')) return;
            event.preventDefault();
            event.stopPropagation();
        },
        true,
    );

    /*
     * Ignore cancelled submissions unless htmx is handling them; otherwise no
     * request would clear the busy state.
     */
    document.addEventListener("submit", function (event) {
        var form = event.target;
        var submitter = event.submitter;
        var handledByHtmx = isHtmx(form) || isHtmx(submitter);

        if (event.defaultPrevented && !handledByHtmx) return;
        if (optedOut(form)) return;

        /*
         * Programmatic submissions may have no submitter; show progress on the
         * first submit control.
         */
        markBusy(submitter || form.querySelector(SUBMITS));
        form.querySelectorAll(SUBMITS).forEach(function (control) {
            if (!optedOut(control)) disable(control);
        });
    });

    /*
     * Mark button-styled and explicitly opted-in links only when they navigate
     * this tab. Downloads and modified clicks leave this page open.
     */
    document.addEventListener("click", function (event) {
        if (event.defaultPrevented || event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
            return;

        var link = event.target.closest(
            'a[href].rounded-button, a[href][data-busy="link"]',
        );
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
        /*
         * Same-page fragments scroll without loading a page; the same URL
         * without a fragment reloads.
         */
        if (
            destination.hash &&
            destination.href.split("#")[0] ===
                window.location.href.split("#")[0]
        )
            return;

        markBusy(link);
        replaceBody(link);
    });

    /* Clear busy state on both successful and failed htmx requests. */
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
            var source = event.detail && event.detail.elt;
            /*
             * htmx uses the body when no source is supplied. Releasing it
             * would also release unrelated requests.
             */
            if (!source || source === document.body) return;
            releaseRequest(source);
        });
    });

    /*
     * The back/forward cache can restore a page with pending controls still
     * disabled.
     */
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) releaseEverything();
    });
})();
