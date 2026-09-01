/**
 * Places a dropdown menu in viewport coordinates instead of beside its
 * trigger in the page's flow.
 *
 * A menu positioned with `absolute` is clipped by any ancestor that
 * scrolls, and `overflow-x: auto` clips top and bottom as well as left
 * and right — the browser gives an element one scroll box, not one per
 * axis. So a menu inside a sideways-scrolling table loses whatever hangs
 * below the last row. `fixed` is measured against the viewport and no
 * scroll box clips it.
 *
 * The kit's own placement is kept everywhere else: this runs only for
 * <c-ui.dropdown strategy="fixed">, which replaces positionDropdown on
 * the component so that reopening, scrolling and resizing all come back
 * through here.
 *
 * Above and below are the only two placements: a menu that opens to the
 * side is never one of these, and the strategy does not claim to serve
 * one.
 */
(function () {
    // Kept clear of the viewport edges, so a menu against the bottom of
    // the window still reads as a box rather than as a cut-off list.
    const MARGIN = 8;

    window.n26PositionMenu = function (trigger, content, options) {
        if (!trigger || !content) return;

        // A collapsed menu is in the flow under its trigger and nothing
        // places it. Whatever a wider window left behind is cleared, so
        // a resize down does not strand it over the page.
        if (options.collapsible && window.innerWidth < 768) {
            content.style.position = "";
            content.style.top = "";
            content.style.left = "";
            return;
        }

        const align = options.align || "start";
        const offset = parseInt(options.offset, 10) || 0;
        const flip = options.flip !== false;

        const t = trigger.getBoundingClientRect();

        // Cleared before measuring: the kit's own placement may have left
        // an edge set, and two opposing edges on one box decide its size.
        content.style.position = "fixed";
        content.style.right = "";
        content.style.bottom = "";
        content.style.transform = "";

        const width = content.offsetWidth;
        const height = content.offsetHeight;

        const below = t.bottom + offset;
        const above = t.top - offset - height;
        let top = options.position === "top" ? above : below;
        if (flip) {
            const overflowsBelow = top + height > window.innerHeight - MARGIN;
            if (overflowsBelow && above > MARGIN) {
                top = above;
            } else if (top < MARGIN) {
                top = below;
            }
        }

        let left = t.left;
        if (align === "end") {
            left = t.right - width;
        } else if (align === "center") {
            left = t.left + t.width / 2 - width / 2;
        }
        // A narrow window can leave no room on the side the alignment
        // asks for, and a menu half off the screen is unreadable either
        // way — so the window wins over the alignment.
        left = Math.min(
            Math.max(MARGIN, left),
            window.innerWidth - width - MARGIN,
        );

        content.style.top = Math.max(MARGIN, top) + "px";
        content.style.left = left + "px";
    };
})();
