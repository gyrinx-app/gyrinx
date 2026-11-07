/*
 * Shrink content marked data-print-fit until it fits or reaches data-print-
 * fit-min, in millimetres. The default minimum applies when that attribute is
 * absent.
 *
 * Loaded by c-n26.print.sheet with fit enabled. Descendants must use em-based
 * sizes so changing the marked element's font size scales the whole card.
 */
(function () {
    "use strict";

    // CSS resolves physical units at 96dpi, independently of the device resolution.
    var PX_PER_MM = 96 / 25.4;

    var DEFAULT_MIN_MM = 1.5;

    var STEP_PX = 0.4;

    // Allow subpixel rounding differences between scrollHeight and clientHeight to avoid shrinking content that already fits.
    var TOLERANCE_PX = 0.5;

    // Bound work for content that cannot shrink, such as fixed-width images or unbreakable text.
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

    // Read the sheet's auto-print option from the script element.
    var auto =
        document.currentScript &&
        document.currentScript.hasAttribute("data-print-auto");

    if (auto) {
        // Wait for images to load before opening the print dialog.
        window.addEventListener("load", function () {
            fitAll();
            window.print();
        });
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", fitAll);
    } else {
        fitAll();
    }
})();
