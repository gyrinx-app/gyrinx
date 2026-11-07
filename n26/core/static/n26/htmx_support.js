/* Browser support for the partial-response contract in n26/core/views/htmx.py. */

/*
 * Alpine can insert links after htmx has scanned the page. Handle their clicks
 * by delegation, skipping events htmx already prevented.
 *
 * Pass the link as the request source so request listeners, including busy-
 * state cleanup, can identify its control.
 */
document.body.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
        return;
    var link = event.target.closest("a[hx-get]");
    if (!link || !window.htmx) return;
    event.preventDefault();
    window.htmx.ajax("GET", link.getAttribute("hx-get"), {
        source: link,
        swap: "none",
    });
});

/*
 * Read page-declared n26-carry parameters from the current URL for each
 * request; rendered control URLs may predate tab or selection changes.
 *
 * Preserve values already supplied by the form or request URL to avoid
 * duplicate parameters.
 */
document.body.addEventListener("htmx:configRequest", function (event) {
    var meta = document.querySelector('meta[name="n26-carry"]');
    if (!meta) return;
    var path = event.detail.path || "";
    var asked = new URLSearchParams(
        path.indexOf("?") === -1 ? "" : path.slice(path.indexOf("?") + 1),
    );
    meta.content
        .split(/\s+/)
        .filter(Boolean)
        .forEach(function (name) {
            if (event.detail.parameters[name] || asked.has(name)) return;
            var value = new URLSearchParams(location.search).get(name);
            if (value) event.detail.parameters[name] = value;
        });
});

/*
 * htmx parses fragments with scripting disabled, so noscript contents can
 * become active elements. Empty them to match normal scripted page rendering.
 */
function n26EmptyNoscript(event) {
    var swapped = event.target;
    if (!swapped || !swapped.querySelectorAll) return;
    if (swapped.tagName === "NOSCRIPT") swapped.replaceChildren();
    var found = swapped.querySelectorAll("noscript");
    for (var index = 0; index < found.length; index++) {
        found[index].replaceChildren();
    }
}
document.body.addEventListener("htmx:afterSwap", n26EmptyNoscript);
document.body.addEventListener("htmx:oobAfterSwap", n26EmptyNoscript);

/*
 * htmx wraps array trigger payloads in detail.value. Forward each n26-toasts
 * entry separately to the toast container.
 */
document.body.addEventListener("n26-toasts", function (event) {
    var detail = event.detail || {};
    var toasts = Array.isArray(detail) ? detail : detail.value || [];
    toasts.forEach(function (toast) {
        window.dispatchEvent(new CustomEvent("toast", { detail: toast }));
    });
});
