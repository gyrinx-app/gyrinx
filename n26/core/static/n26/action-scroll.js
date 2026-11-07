// On narrow screens the Edit actions are below the card. Scroll to #actions there; at desktop width they are already beside it.
(() => {
    if (window.location.hash !== "#actions") return;
    if (!window.matchMedia("(width < 64rem)").matches) return;
    (
        document.getElementById("actions") ||
        document.getElementById("n26-action-panels")
    )?.scrollIntoView({ block: "start" });
})();
