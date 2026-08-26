/*
 * Client glue for htmx partial updates. The server side of the pattern is
 * documented in n26/core/views/htmx.py; this file holds the three pieces
 * the browser needs.
 */

/*
 * 1. Clicks on controls built after the page loaded.
 *
 * htmx wires a control when the page is drawn or when a swap brings it in.
 * Some controls are built later by Alpine — the copies inside an opened
 * catalogue row live in a <template x-if> — so htmx has never seen them and
 * their hx-get would otherwise be inert markup on a normal link. Their
 * clicks are caught here at the document level, which cannot be raced by
 * whatever built them.
 *
 * A control htmx did wire handles its own click and calls preventDefault
 * before this listener runs, so the defaultPrevented test is what stops a
 * second request being sent for the same click.
 */
document.body.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
        return;
    var link = event.target.closest("a[hx-get]");
    if (!link || !window.htmx) return;
    event.preventDefault();
    window.htmx.ajax("GET", link.getAttribute("hx-get"), { swap: "none" });
});

/*
 * 2. URL parameters carried onto every htmx request.
 *
 * Some UI state lives only in the address, written there as the reader
 * clicks — which section tab is on screen, which row stands open. Controls
 * were addressed when they were drawn and know nothing of a click since, so
 * the current values are read off the address here, once, for every
 * request. Which parameter names matter is the page's knowledge, not this
 * file's: the page declares them in a <meta name="n26-carry"> tag.
 *
 * A request that already carries a value — a form field, or a parameter in
 * the requested path — keeps it. Adding a second copy would put both in the
 * address bar, and the address bar is what the next control reads.
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
 * 3. Toasts from the HX-Trigger header.
 *
 * A partial response carries the server's queued messages in its
 * HX-Trigger header as one n26-toasts event holding the whole list. htmx
 * wraps a trigger payload that is not a plain object as { value: ... }
 * before dispatching, so the list arrives one level down — read
 * event.detail as the list itself and it is silently empty. Each entry is
 * handed to the toast container one at a time, which is how it takes them.
 */
document.body.addEventListener("n26-toasts", function (event) {
    var detail = event.detail || {};
    var toasts = Array.isArray(detail) ? detail : detail.value || [];
    toasts.forEach(function (toast) {
        window.dispatchEvent(new CustomEvent("toast", { detail: toast }));
    });
});
