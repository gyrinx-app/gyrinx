/*
 * Position strategy="fixed" dropdowns relative to the viewport so scrolling
 * table ancestors do not clip them. Supports placement above or below the
 * trigger.
 */
(function () {
    // Leave a visible margin around the menu at the viewport edges.
    const MARGIN = 8;

    window.n26PositionMenu = function (trigger, content, options) {
        if (!trigger || !content) return;

        // Clear fixed positioning when the responsive menu returns to normal document flow.
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

        // Clear opposing edges before measuring because they can constrain the menu's size.
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
        // Keep the menu inside the viewport when its requested alignment would overflow.
        left = Math.min(
            Math.max(MARGIN, left),
            window.innerWidth - width - MARGIN,
        );

        content.style.top = Math.max(MARGIN, top) + "px";
        content.style.left = left + "px";
    };
})();
