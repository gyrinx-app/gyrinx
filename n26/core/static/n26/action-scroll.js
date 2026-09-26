// The roster's action mark links to Edit with #actions. Below the width where
// the flows sit beside the card they sit under it, out of view, so scroll to
// them. At desktop width they are already beside the card and the page stays.
(() => {
    if (window.location.hash !== "#actions") return;
    if (!window.matchMedia("(width < 64rem)").matches) return;
    document
        .getElementById("n26-action-panels")
        ?.scrollIntoView({ block: "start" });
})();
