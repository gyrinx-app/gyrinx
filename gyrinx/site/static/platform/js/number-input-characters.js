/*
 * A number input accepts "e", "E" and "+" as well as digits, because the
 * browser reads 1e3 as a number. Nobody means that in a credits or count
 * field, and a bare "e" leaves the field looking broken, so those three
 * characters are cancelled as they arrive.
 *
 * A minus sign and a decimal point stay. Dropping them would quietly turn
 * -5 into 5 and 2.5 into 25; the browser already refuses those values with
 * a message that says why.
 *
 * Desktop typing is caught on keydown. Mobile keyboards and IMEs report
 * keydown as "Unidentified", so beforeinput catches those. Not every
 * browser puts pasted text in beforeinput, so a paste is checked as a
 * whole and cancelled if it contains any of the three.
 */
(function () {
    "use strict";

    const REFUSED = /[eE+]/;

    function isNumberField(target) {
        return target instanceof HTMLInputElement && target.type === "number";
    }

    document.addEventListener(
        "keydown",
        function (event) {
            if (!isNumberField(event.target)) return;
            if (event.ctrlKey || event.metaKey || event.altKey) return;
            // Chrome's autofill sends keydown events with no key.
            if (typeof event.key !== "string" || event.key.length !== 1) {
                return;
            }
            if (REFUSED.test(event.key)) event.preventDefault();
        },
        true,
    );

    document.addEventListener(
        "beforeinput",
        function (event) {
            if (!isNumberField(event.target)) return;
            if (!event.data) return;
            if (REFUSED.test(event.data)) event.preventDefault();
        },
        true,
    );

    document.addEventListener(
        "paste",
        function (event) {
            if (!isNumberField(event.target)) return;
            const text = event.clipboardData
                ? event.clipboardData.getData("text")
                : "";
            if (REFUSED.test(text)) event.preventDefault();
        },
        true,
    );
})();
