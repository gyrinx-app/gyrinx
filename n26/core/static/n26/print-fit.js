/* Shrink-to-fit for print.
 *
 * A fixed-size card is a promise about physical dimensions, so when the content
 * is too long for it something has to give, and the only two candidates are the
 * type size and the content. Clipping the content is the default and it is the
 * wrong one: it removes information silently, and on paper there is no scrollbar
 * to hint that it happened. So the type shrinks instead, down to a floor, and
 * past that floor it clips — because text too small to read is not a rescue.
 *
 * Opt in per element with data-print-fit, and per element again for the floor:
 *
 *     <div class="n26-print-card-body" data-print-fit data-print-fit-min="1.5">
 *
 * Loaded by <c-n26.print.sheet fit>. Progressive enhancement throughout: with no
 * JavaScript the page renders at its authored size and long content clips, which
 * is where it started. Nothing else depends on this running.
 *
 * Shrink the *anchor*, not the text. This walks one element per marked box and
 * sets a font-size on it; everything inside is expected to be sized in em, so a
 * single change carries the whole block down together and the proportions hold.
 * Sizing descendants in mm and then shrinking the parent does nothing at all,
 * which is a quiet way to spend an afternoon.
 */
(function () {
    "use strict";

    // Physical units are resolved against 96dpi in CSS, whatever the real
    // device. This is the conversion the browser itself is using.
    var PX_PER_MM = 96 / 25.4;

    // The floor, in millimetres, if an element does not name its own.
    var DEFAULT_MIN_MM = 1.5;

    // How much to take off per pass. Small enough not to overshoot a fit by
    // something a reader would notice, large enough to converge quickly.
    var STEP_PX = 0.4;

    // Subpixel noise means scrollHeight can exceed clientHeight by a fraction on
    // content that fits perfectly well. Without a tolerance the loop shrinks
    // text that had no problem.
    var TOLERANCE_PX = 0.5;

    // A bound on the loop rather than a trust in the exit condition. A box with
    // an unshrinkable child — a wide image, a long unbreakable word — never
    // stops overflowing, and would otherwise spin until it hit the floor one
    // 0.4px at a time on every element on the page.
    var MAX_PASSES = 80;

    function overflows(el) {
        return (
            el.scrollHeight > el.clientHeight + TOLERANCE_PX ||
            el.scrollWidth > el.clientWidth + TOLERANCE_PX
        );
    }

    function fit(el) {
        var minMm = parseFloat(el.dataset.printFitMin);
        var minPx = (isNaN(minMm) ? DEFAULT_MIN_MM : minMm) * PX_PER_MM;
        var size = parseFloat(window.getComputedStyle(el).fontSize);
        var passes = MAX_PASSES;

        while (passes-- > 0 && size > minPx && overflows(el)) {
            size -= STEP_PX;
            el.style.fontSize = size + "px";
        }
    }

    function fitAll() {
        document.querySelectorAll("[data-print-fit]").forEach(fit);
    }

    // The script tag carries the flag, so the sheet component can ask for
    // auto-print without a second script or an inline one.
    var auto =
        document.currentScript &&
        document.currentScript.hasAttribute("data-print-auto");

    if (auto) {
        // `load`, not DOMContentLoaded: printing before the images have painted
        // captures a page with holes in it, and a print dialog is not something
        // you can quietly retry.
        window.addEventListener("load", function () {
            fitAll();
            window.print();
        });
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", fitAll);
    } else {
        // `defer` usually means the document is already parsed by now.
        fitAll();
    }
})();
