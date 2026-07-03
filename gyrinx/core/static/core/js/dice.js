// Dice roller — progressive enhancement.
//
// The page is fully server-rendered and works without this script: every
// control is an <a> that reloads with new query state. Here we intercept those
// clicks so the common edits are instant: adding/removing dice and groups mutate
// the DOM and the URL client-side (no round-trip). Rolling still submits to the
// backend — a fresh seed in the URL — so results stay reproducible and shareable.
//
// Editing invalidates any current roll: trays are reset to empty "?" placeholder
// dice and the seed is dropped from the URL, matching the server's behaviour.

const root = document.querySelector(".js-dice");

if (root) {
    const groupsRow = root.querySelector(".js-dice-groups");

    const groups = () => Array.from(groupsRow.querySelectorAll(".dice-group"));
    const trayOf = (group) => group.querySelector(".dice-tray");
    const countOf = (group) => trayOf(group).children.length;

    const placeholder = () => {
        const span = document.createElement("span");
        span.className = "dice-placeholder";
        span.setAttribute("role", "img");
        span.setAttribute("aria-label", "Not yet rolled");
        return span;
    };

    // Enable/disable the "remove one die" and "set to one" controls: neither
    // applies when a group is down to a single die.
    const updateButtons = (group, n) => {
        group.querySelectorAll(".js-sub-die, .js-set-one").forEach((btn) => {
            const disabled = n <= 1;
            btn.classList.toggle("disabled", disabled);
            btn.setAttribute("aria-disabled", disabled ? "true" : "false");
        });
    };

    // Fill a group's tray with n empty placeholder dice — also clears any rolled
    // dice, since editing invalidates the current roll.
    const setCount = (group, n) => {
        trayOf(group).replaceChildren(
            ...Array.from({ length: n }, placeholder),
        );
        updateButtons(group, n);
    };

    const setMode = (mode) => {
        root.dataset.mode = mode;
        const d6 = root.querySelector(".js-roll-d6");
        const d3 = root.querySelector(".js-roll-d3");
        if (d6) {
            d6.classList.toggle("btn-primary", mode === "d6");
            d6.classList.toggle("btn-outline-primary", mode !== "d6");
        }
        if (d3) {
            d3.classList.toggle("btn-primary", mode === "d3");
            d3.classList.toggle("btn-outline-primary", mode !== "d3");
        }
    };

    const params = () => {
        const p = new URLSearchParams();
        p.set("m", root.dataset.mode || "d6");
        groups().forEach((g) => p.append("d", String(countOf(g))));
        return p;
    };

    // A fresh 8-hex seed. The server seeds its RNG with this string, so the same
    // URL always reproduces the same roll.
    const newSeed = () =>
        Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) =>
            b.toString(16).padStart(2, "0"),
        ).join("");

    const rollHref = (mode) => {
        const p = params();
        p.set("m", mode);
        p.set("seed", newSeed());
        return "?" + p.toString();
    };

    // Keep the Roll links pointing at the current structure (and a fresh seed) so
    // middle-click / open-in-new-tab still rolls correctly after client edits.
    const refreshRollLinks = () => {
        const d6 = root.querySelector(".js-roll-d6");
        const d3 = root.querySelector(".js-roll-d3");
        if (d6) d6.setAttribute("href", rollHref("d6"));
        if (d3) d3.setAttribute("href", rollHref("d3"));
    };

    // After any structure edit: de-roll every tray, refresh controls, and rewrite
    // the URL (seedless — no roll) without adding a history entry per keystroke.
    const afterEdit = () => {
        groups().forEach((g) => {
            if (trayOf(g).querySelector("i")) setCount(g, countOf(g));
            else updateButtons(g, countOf(g));
        });
        history.replaceState(null, "", "?" + params().toString());
        refreshRollLinks();
    };

    const addGroup = () => {
        const clone = groups()[0].cloneNode(true);
        setCount(clone, 1);
        groupsRow.appendChild(clone);
        afterEdit();
    };

    const resetAll = () => {
        groups()
            .slice(1)
            .forEach((g) => g.remove());
        setCount(groups()[0], 1);
        setMode("d6");
        afterEdit();
    };

    // On a fresh roll (server-rendered dice), give each die a random delay
    // under 300ms so the values cascade in rather than all landing at once.
    // The fade itself is CSS; here we just stagger the start.
    const animateRoll = () => {
        root.querySelectorAll(".dice-tray i").forEach((die) => {
            die.style.animationDelay = Math.floor(Math.random() * 300) + "ms";
        });
    };
    animateRoll();

    root.addEventListener("click", (event) => {
        const link = event.target.closest("a");
        if (!link || !root.contains(link)) return;

        // Rolling submits to the backend with a fresh seed.
        if (link.matches(".js-roll-d6, .js-roll-d3")) {
            event.preventDefault();
            const mode = link.matches(".js-roll-d3") ? "d3" : "d6";
            setMode(mode);
            window.location.assign(rollHref(mode));
            return;
        }

        // Disabled controls (a single-die group's minus / set-to-one) do nothing.
        if (link.classList.contains("disabled")) {
            event.preventDefault();
            return;
        }

        const group = link.closest(".dice-group");

        if (link.matches(".js-add-die")) {
            event.preventDefault();
            setCount(group, countOf(group) + 1);
            afterEdit();
        } else if (link.matches(".js-sub-die")) {
            event.preventDefault();
            setCount(group, Math.max(1, countOf(group) - 1));
            afterEdit();
        } else if (link.matches(".js-set-one")) {
            event.preventDefault();
            setCount(group, 1);
            afterEdit();
        } else if (link.matches(".js-remove-group")) {
            event.preventDefault();
            // The first group is the baseline and stays put.
            if (group && group !== groups()[0]) {
                group.remove();
                afterEdit();
            }
        } else if (link.matches(".js-add-group")) {
            event.preventDefault();
            addGroup();
        } else if (link.matches(".js-reset")) {
            event.preventDefault();
            resetAll();
        }
    });
}
