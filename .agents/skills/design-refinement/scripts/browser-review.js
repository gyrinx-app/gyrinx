/* Load in a browser evaluation tool. Diagnostics stay local to the current page. */
(() => {
    window.gyrinxDesignReview?.clear();
    const ns = "http://www.w3.org/2000/svg";
    let layer;
    let options;
    const round = (n) => Math.round(n * 100) / 100;
    const bounds = (el) => {
        const r = el.getBoundingClientRect();
        return Object.fromEntries(
            ["x", "y", "width", "height", "top", "right", "bottom", "left"].map(
                (k) => [k, round(r[k])],
            ),
        );
    };
    const visible = (el) =>
        el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
        el.getBoundingClientRect().width > 0 &&
        el.getBoundingClientRect().height > 0;
    const select = (selector) =>
        [...document.querySelectorAll(selector)].filter(
            (el) => !layer?.contains(el) && visible(el),
        );
    const requireOne = (selector) => {
        const matches = select(selector);
        if (matches.length !== 1)
            throw new Error(
                `Expected one visible root for ${selector}; found ${matches.length}`,
            );
        return matches[0];
    };
    const inspect = (selector) =>
        select(selector).map((el) => {
            const s = getComputedStyle(el);
            return {
                tag: el.tagName.toLowerCase(),
                id: el.id,
                bounds: bounds(el),
                styles: Object.fromEntries(
                    [
                        "display",
                        "position",
                        "fontFamily",
                        "fontSize",
                        "fontWeight",
                        "lineHeight",
                        "color",
                        "backgroundColor",
                        "paddingTop",
                        "paddingRight",
                        "paddingBottom",
                        "paddingLeft",
                        "marginTop",
                        "marginRight",
                        "marginBottom",
                        "marginLeft",
                        "rowGap",
                        "columnGap",
                        "gridTemplateColumns",
                        "alignItems",
                        "justifyContent",
                    ].map((k) => [k, s[k]]),
                ),
            };
        });
    const compare = (selectors) => {
        const items = selectors.map((selector) => ({
            selector,
            ...inspect(selector)[0],
        }));
        if (
            items.some(
                (item) => !item.bounds || select(item.selector).length !== 1,
            )
        )
            throw new Error(
                "Each comparison selector must identify one visible element",
            );
        const first = items[0]?.bounds;
        return items.map((item) => ({
            ...item,
            deltaFromFirst: Object.fromEntries(
                ["left", "right", "top", "bottom"].map((edge) => [
                    edge,
                    round(item.bounds[edge] - first[edge]),
                ]),
            ),
        }));
    };
    function clear() {
        layer?.remove();
        layer = undefined;
        options = undefined;
        window.removeEventListener("scroll", redraw, true);
        window.removeEventListener("resize", redraw);
    }
    function shape(tag, attrs) {
        const el = document.createElementNS(ns, tag);
        for (const [key, value] of Object.entries(attrs))
            el.setAttribute(key, String(value));
        layer.append(el);
        return el;
    }
    function rect(r, attrs = {}) {
        return shape("rect", {
            x: r.left,
            y: r.top,
            width: r.width,
            height: r.height,
            ...attrs,
        });
    }
    function line(x1, y1, x2, y2, attrs = {}) {
        shape("line", {
            x1,
            y1,
            x2,
            y2,
            stroke: "#0284c7",
            "stroke-width": 0.5,
            ...attrs,
        });
    }
    function redraw() {
        if (!options) return;
        layer?.remove();
        layer = undefined;
        const root = requireOne(options.root);
        const r = bounds(root);
        layer = document.createElementNS(ns, "svg");
        layer.setAttribute("data-gyrinx-design-review", "");
        layer.setAttribute("aria-hidden", "true");
        layer.setAttribute("width", window.innerWidth);
        layer.setAttribute("height", window.innerHeight);
        Object.assign(layer.style, {
            position: "fixed",
            inset: "0",
            zIndex: "2147483647",
            pointerEvents: "none",
            overflow: "hidden",
        });
        document.documentElement.append(layer);
        const { mode, step, columns, gutter, regions, selectors } = options;
        if (mode === "grid") {
            for (
                let y = r.top;
                y < Math.min(r.bottom, innerHeight);
                y += step
            ) {
                if (y >= 0) line(r.left, y, r.right, y, { opacity: 0.4 });
            }
            const track = (r.width - gutter * (columns - 1)) / columns;
            if (track <= 0)
                throw new Error("Columns and gutters exceed root width");
            for (let i = 0; i < columns; i++) {
                const x = r.left + i * (track + gutter);
                rect(
                    {
                        left: x,
                        top: Math.max(0, r.top),
                        width: track,
                        height: Math.max(
                            0,
                            Math.min(innerHeight, r.bottom) -
                                Math.max(0, r.top),
                        ),
                    },
                    { fill: "#0284c7", opacity: 0.06 },
                );
                line(x, r.top, x, r.bottom);
                line(x + track, r.top, x + track, r.bottom);
            }
        } else if (mode === "anchors") {
            for (const selector of selectors)
                for (const el of select(selector)) {
                    const b = bounds(el);
                    rect(b, {
                        fill: "none",
                        stroke: "#dc2626",
                        "stroke-width": 1,
                    });
                    line(b.left, 0, b.left, innerHeight);
                    line(b.right, 0, b.right, innerHeight);
                    line(0, b.top, innerWidth, b.top, { stroke: "#d97706" });
                    line(0, b.bottom, innerWidth, b.bottom, {
                        stroke: "#d97706",
                    });
                }
        } else {
            let background = "#fff";
            if (mode === "blocks") {
                for (let el = root; el; el = el.parentElement) {
                    const colour = getComputedStyle(el).backgroundColor;
                    if (
                        colour !== "transparent" &&
                        colour !== "rgba(0, 0, 0, 0)"
                    ) {
                        background = colour;
                        break;
                    }
                }
            }
            rect(r, { fill: background });
            if (mode === "zones") {
                for (const { selector, priority } of regions)
                    for (const el of select(selector)) {
                        rect(bounds(el), {
                            fill: ["#333", "#888", "#ccc"][priority - 1],
                            stroke: "#fff",
                            "stroke-width": 1,
                        });
                    }
            } else {
                layer.style.filter = "grayscale(1)";
                // Paint surfaces before text. DOM order preserves nested surfaces without
                // converting container area into a false estimate of content occupancy.
                for (const el of [root, ...root.querySelectorAll("*")].filter(
                    visible,
                )) {
                    if (["SCRIPT", "STYLE", "NOSCRIPT"].includes(el.tagName))
                        continue;
                    const b = bounds(el),
                        s = getComputedStyle(el);
                    rect(b, {
                        fill: s.backgroundColor,
                        stroke: s.borderTopColor,
                        "stroke-width": parseFloat(s.borderTopWidth) || 0,
                    });
                    if (
                        [
                            "IMG",
                            "SVG",
                            "CANVAS",
                            "VIDEO",
                            "INPUT",
                            "SELECT",
                            "TEXTAREA",
                        ].includes(el.tagName)
                    ) {
                        rect(b, { fill: "#aaa" });
                        continue;
                    }
                    for (const node of el.childNodes) {
                        if (
                            node.nodeType !== Node.TEXT_NODE ||
                            !node.textContent.trim()
                        )
                            continue;
                        const range = document.createRange();
                        range.selectNodeContents(node);
                        for (const box of range.getClientRects()) {
                            const height = Math.min(
                                box.height,
                                parseFloat(s.fontSize) * 0.65,
                            );
                            rect(
                                {
                                    left: box.left,
                                    top: box.top + (box.height - height) / 2,
                                    width: box.width,
                                    height,
                                },
                                {
                                    fill: s.color,
                                    opacity:
                                        Number(s.fontWeight) >= 600 ? 1 : 0.7,
                                },
                            );
                        }
                    }
                }
            }
        }
    }
    function overlay({
        root = "main",
        mode = "grid",
        step = 4,
        columns = 12,
        gutter = 16,
        selectors = [],
        regions = [],
    } = {}) {
        if (!["grid", "anchors", "blocks", "zones"].includes(mode))
            throw new Error("Unknown overlay mode");
        if (
            !Number.isFinite(step) ||
            step < 2 ||
            !Number.isInteger(columns) ||
            columns < 1 ||
            columns > 48 ||
            !Number.isFinite(gutter) ||
            gutter < 0
        )
            throw new Error("Invalid grid geometry");
        if (
            mode === "zones" &&
            (!regions.length ||
                regions.some(({ priority }) => ![1, 2, 3].includes(priority)))
        )
            throw new Error("Zones need explicit priorities 1, 2 or 3");
        requireOne(root);
        clear();
        options = { root, mode, step, columns, gutter, selectors, regions };
        try {
            redraw();
        } catch (error) {
            clear();
            throw error;
        }
        window.addEventListener("scroll", redraw, true);
        window.addEventListener("resize", redraw);
        return {
            mode,
            root: bounds(requireOne(root)),
            viewport: {
                width: innerWidth,
                height: innerHeight,
                devicePixelRatio,
            },
            note:
                mode === "zones"
                    ? "Tones show declared priorities, not observed prominence."
                    : "Geometry in CSS px. Inspect the original alongside this diagnostic.",
        };
    }
    window.gyrinxDesignReview = { inspect, compare, overlay, clear };
    return { ready: true, methods: ["inspect", "compare", "overlay", "clear"] };
})();
