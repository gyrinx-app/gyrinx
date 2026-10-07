/*
 * Chrome changes a focused number input when the pointer wheels over it, so a
 * scroll through a form overwrites what was typed. The event has to be
 * cancelled: a passive listener cannot cancel, and a wheel listener on an
 * ancestor is itself enough for Chrome to start changing descendant number
 * inputs.
 *
 * An unfocused field is left alone, so the page still scrolls when the
 * pointer merely passes over one. A pinch-zoom arrives as a wheel with
 * ctrlKey, and cancelling that would trap the page.
 */
(function () {
    "use strict";

    document.addEventListener(
        "wheel",
        function (event) {
            const target = event.target;
            if (event.ctrlKey) return;
            if (!(target instanceof HTMLInputElement)) return;
            if (target.type !== "number") return;
            if (document.activeElement !== target) return;
            event.preventDefault();
        },
        { capture: true, passive: false },
    );
})();
