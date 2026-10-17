(() => {
    const stylesheets = new Map();

    function stylesheet(url) {
        if (!stylesheets.has(url)) {
            stylesheets.set(
                url,
                fetch(url).then((response) => {
                    if (!response.ok)
                        throw new Error("Colour stylesheet unavailable");
                    return response.text();
                }),
            );
        }
        return stylesheets.get(url);
    }

    async function enhance(container) {
        const select = container.querySelector("select");
        if (!select || select.disabled) return;
        try {
            const css = await stylesheet(container.dataset.themeCss);
            const host = document.createElement("span");
            const shadow = host.attachShadow({
                mode: "open",
                delegatesFocus: true,
            });
            const style = document.createElement("style");
            // The site's root tokens belong to this widget's shadow host in admin.
            style.textContent = css
                .replaceAll(":root", ":host")
                .replace(/\.dark\s*\{/g, ":host(.dark),.dark{");
            shadow.append(
                style,
                container.querySelector("template").content.cloneNode(true),
            );
            const theme = shadow.querySelector(".tag-colour-theme");
            const trigger = shadow.querySelector("[role=combobox]");
            const label = shadow.querySelector("[data-selected-colour]");
            const menu = shadow.querySelector("[role=listbox]");
            const options = [...menu.querySelectorAll("[role=option]")];
            menu.id = `${select.id}-options`;
            trigger.setAttribute("aria-controls", menu.id);
            let active = 0;
            let search = "";
            let searchTime = 0;

            function sync() {
                const selected = options.find(
                    (option) => option.dataset.value === select.value,
                );
                label.textContent =
                    selected?.textContent.trim() ||
                    select.selectedOptions[0]?.textContent;
                trigger.style.color = selected?.style.color || "inherit";
                for (const option of options) {
                    option.setAttribute(
                        "aria-selected",
                        String(option === selected),
                    );
                }
            }
            for (const option of options) {
                const value = option.dataset.value;
                option.style.color =
                    value === "default"
                        ? "inherit"
                        : `var(--color-${value}-500)`;
            }
            function close(focus = false) {
                menu.hidden = true;
                trigger.setAttribute("aria-expanded", "false");
                if (focus) trigger.focus();
            }
            function focusOption(index) {
                active = index;
                options.forEach((option, i) => {
                    option.tabIndex = i === index ? 0 : -1;
                });
                options[index].focus();
            }
            function open() {
                menu.hidden = false;
                trigger.setAttribute("aria-expanded", "true");
                focusOption(
                    Math.max(
                        0,
                        options.findIndex(
                            (option) => option.dataset.value === select.value,
                        ),
                    ),
                );
            }
            function choose(option) {
                select.value = option.dataset.value;
                select.dispatchEvent(new Event("input", { bubbles: true }));
                select.dispatchEvent(new Event("change", { bubbles: true }));
                close(true);
            }
            trigger.addEventListener("click", () =>
                menu.hidden ? open() : close(true),
            );
            trigger.addEventListener("keydown", (event) => {
                if (
                    ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)
                ) {
                    event.preventDefault();
                    open();
                    if (event.key === "Home") focusOption(0);
                    if (event.key === "End") focusOption(options.length - 1);
                }
            });
            options.forEach((option, index) => {
                option.addEventListener("click", () => choose(option));
                option.addEventListener("focus", () => {
                    active = index;
                });
            });
            menu.addEventListener("keydown", (event) => {
                const moves = {
                    ArrowDown: Math.min(options.length - 1, active + 1),
                    ArrowUp: Math.max(0, active - 1),
                    Home: 0,
                    End: options.length - 1,
                };
                if (Object.hasOwn(moves, event.key)) {
                    event.preventDefault();
                    focusOption(moves[event.key]);
                } else if (event.key === "Escape") {
                    event.preventDefault();
                    close(true);
                } else if (event.key === "Tab") {
                    close();
                } else if (
                    event.key.length === 1 &&
                    event.key !== " " &&
                    !event.ctrlKey &&
                    !event.metaKey &&
                    !event.altKey
                ) {
                    event.preventDefault();
                    const now = Date.now();
                    search =
                        now - searchTime < 700
                            ? search + event.key.toLowerCase()
                            : event.key.toLowerCase();
                    searchTime = now;
                    const index = options.findIndex((option) =>
                        option.textContent
                            .trim()
                            .toLowerCase()
                            .startsWith(search),
                    );
                    if (index >= 0) focusOption(index);
                }
            });
            document.addEventListener("pointerdown", (event) => {
                if (!event.composedPath().includes(host)) close();
            });
            shadow.addEventListener("focusout", (event) => {
                if (!shadow.contains(event.relatedTarget)) close();
            });
            select.addEventListener("change", sync);
            select.form?.addEventListener("reset", () => setTimeout(sync, 0));
            for (const fieldLabel of select.labels) {
                fieldLabel.addEventListener("click", (event) => {
                    event.preventDefault();
                    trigger.focus();
                });
            }
            const media = window.matchMedia("(prefers-color-scheme: dark)");
            function syncTheme() {
                const setting = document.documentElement.dataset.theme;
                const dark =
                    setting === "dark" ||
                    (setting !== "light" && media.matches);
                host.classList.toggle("dark", dark);
                theme.classList.toggle("dark", dark);
            }
            new MutationObserver(syncTheme).observe(document.documentElement, {
                attributes: true,
                attributeFilter: ["data-theme"],
            });
            media.addEventListener("change", syncTheme);
            syncTheme();
            sync();
            container.append(host);
            container.style.width = "16rem";
            container.style.maxWidth = "100%";
            select.hidden = true;
            const fieldRow = container.closest(".form-row");
            if (fieldRow) fieldRow.style.overflow = "visible";
        } catch {
            // Saving the native field still works when enhancement cannot load.
        }
    }

    function mount() {
        document.querySelectorAll("[data-tag-colour-picker]").forEach(enhance);
    }
    if (document.readyState === "loading")
        document.addEventListener("DOMContentLoaded", mount);
    else mount();
})();
