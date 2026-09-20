"use strict";

// Keep fields and the site footer clear of a dock that wraps with the viewport.
(() => {
    const actions = document.querySelector("[data-battle-actions]");
    if (!actions) return;
    const measure = () => {
        document.documentElement.style.setProperty(
            "--n26-battle-actions-height",
            `${actions.getBoundingClientRect().height}px`,
        );
    };
    measure();
    if (window.ResizeObserver) new ResizeObserver(measure).observe(actions);
    window.addEventListener("resize", measure);
})();
