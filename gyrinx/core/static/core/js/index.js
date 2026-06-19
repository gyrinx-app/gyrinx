// Enable tooltips
const tooltipTriggerList = document.querySelectorAll(
    '[data-bs-toggle="tooltip"]',
);
const tooltipList = [...tooltipTriggerList].map(
    (tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl),
);
tooltipTriggerList.forEach((tooltipTriggerEl) => {
    tooltipTriggerEl.addEventListener("click", (event) => {
        if (tooltipTriggerEl.getAttribute("href") === "#") {
            event.preventDefault();
        }
    });
});

/*!
 * Adapted from Bootstrap's docs:
 * Color mode toggler for Bootstrap's docs (https://getbootstrap.com/)
 * Copyright 2011-2024 The Bootstrap Authors
 * Licensed under the Creative Commons Attribution 3.0 Unported License.
 */

(() => {
    "use strict";

    const getThemeFromQueryParam = () => {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get("theme");
    };

    const getCookie = (name) => {
        const decodedCookie = decodeURIComponent(document.cookie);
        const ca = decodedCookie.split(";");
        for (let i = 0; i < ca.length; i++) {
            let c = ca[i];
            while (c.charAt(0) == " ") {
                c = c.substring(1);
            }
            if (c.indexOf(name + "=") == 0) {
                return c.substring(name.length + 1, c.length);
            }
        }
        return null;
    };

    const setCookie = (name, value, days) => {
        const d = new Date();
        d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
        const expires = "expires=" + d.toUTCString();
        document.cookie = name + "=" + value + ";" + expires + ";path=/";
    };

    const getStoredTheme = () => getCookie("theme");
    const setStoredTheme = (theme) => setCookie("theme", theme, 365);
    const setStoredActiveTheme = (theme) =>
        setCookie("theme_active", theme, 365);

    const getPreferredTheme = () => {
        if (getThemeFromQueryParam()) {
            return getThemeFromQueryParam();
        }

        const storedTheme = getStoredTheme();
        if (storedTheme) {
            return storedTheme;
        }

        return window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";
    };

    const setTheme = (theme) => {
        if (theme === "auto") {
            document.documentElement.setAttribute(
                "data-bs-theme",
                window.matchMedia("(prefers-color-scheme: dark)").matches
                    ? "dark"
                    : "light",
            );
        } else {
            document.documentElement.setAttribute("data-bs-theme", theme);
        }
        setStoredActiveTheme(
            document.documentElement.getAttribute("data-bs-theme"),
        );
    };

    setTheme(getPreferredTheme());

    const showActiveTheme = (theme, focus = false) => {
        const themeSwitcher = document.querySelector("#bd-theme");

        if (!themeSwitcher) {
            return;
        }

        const themeSwitcherText = document.querySelector("#bd-theme-text");
        const activeThemeIcon = document.querySelector(".theme-icon-active");
        const btnToActive = document.querySelector(
            `[data-bs-theme-value="${theme}"]`,
        );
        const iconOfActiveBtn = btnToActive.querySelector(".theme-icon");
        const classOfActiveThemeIcon = Array.from(
            activeThemeIcon.classList,
        ).find((_) => _.startsWith("bi-"));
        const classOfBtnIcon = Array.from(iconOfActiveBtn.classList).find((_) =>
            _.startsWith("bi-"),
        );

        document
            .querySelectorAll("[data-bs-theme-value]")
            .forEach((element) => {
                element.classList.remove("active");
                element.setAttribute("aria-pressed", "false");
            });

        btnToActive.classList.add("active");
        btnToActive.setAttribute("aria-pressed", "true");
        activeThemeIcon.classList.replace(
            classOfActiveThemeIcon,
            classOfBtnIcon,
        );
        const themeSwitcherLabel = `${themeSwitcherText.textContent} (${btnToActive.dataset.bsThemeValue})`;
        themeSwitcher.setAttribute("aria-label", themeSwitcherLabel);

        if (focus) {
            themeSwitcher.focus();
        }
    };

    window
        .matchMedia("(prefers-color-scheme: dark)")
        .addEventListener("change", () => {
            const storedTheme = getStoredTheme();
            if (storedTheme !== "light" && storedTheme !== "dark") {
                setTheme(getPreferredTheme());
            }
        });

    window.addEventListener("DOMContentLoaded", () => {
        showActiveTheme(getPreferredTheme());

        document.querySelectorAll("[data-bs-theme-value]").forEach((toggle) => {
            toggle.addEventListener("click", () => {
                const theme = toggle.getAttribute("data-bs-theme-value");
                setStoredTheme(theme);
                setTheme(theme);
                showActiveTheme(theme, true);
            });
        });
    });
})();

// Enable copy to clipboard
document.querySelectorAll("[data-clipboard-text]").forEach((element) => {
    element.addEventListener("click", (event) => {
        const textToCopy = element.getAttribute("data-clipboard-text");
        if (!textToCopy) return;

        event.preventDefault();

        const messageElemId = element.getAttribute("data-clipboard-message");

        const success = () => {
            if (messageElemId) {
                const messageElem = document.getElementById(messageElemId);
                if (messageElem) {
                    messageElem.classList.remove("d-none");
                    setTimeout(() => {
                        messageElem.classList.add("d-none");
                    }, 2000);
                }
            }
        };

        if (navigator.clipboard) {
            navigator.clipboard.writeText(textToCopy).then(
                () => {
                    console.log("Text copied to clipboard", textToCopy);
                    success();
                },
                (err) => {
                    console.error("Could not copy text: ", err);
                },
            );
        } else {
            const textArea = document.createElement("textarea");
            textArea.value = textToCopy;
            document.body.appendChild(textArea);
            textArea.select();
            try {
                document.execCommand("copy");
                success();
            } catch (err) {
                console.error("Could not copy text: ", err);
            }
            document.body.removeChild(textArea);
        }
    });
});

// Support syncing two or more form elements
document.querySelectorAll("[data-gy-sync]").forEach((element) => {
    const key = element.getAttribute("data-gy-sync");
    const targets = Array.from(
        document.querySelectorAll(`[data-gy-sync="${CSS.escape(key)}"]`),
    ).filter((target) => target !== element);

    if (targets.length === 0) return;

    const dispatch = (event) => {
        targets.forEach((target) => {
            if (target.value !== event.target.value) {
                target.value = event.target.value;
            }
        });
    };

    element.addEventListener("change", dispatch);
    element.addEventListener("input", dispatch);
});

// The availability dropdown's disabled state + tooltip when the equipment-list
// filter is on is rendered server-side in
// core/includes/fighter_gear_filter.html (the filter-switch is a GET
// navigation, so the server re-renders the correct state on each toggle). No
// client-side JS is needed to mirror it.

// Generic handler for "All/None" filter links in dropdown menus
function setupFilterLinks(config) {
    const { prefix, param, allValues } = config;

    document.addEventListener("DOMContentLoaded", () => {
        const allLink = document.getElementById(`${prefix}-all-link`);
        if (allLink) {
            allLink.addEventListener("click", (event) => {
                event.preventDefault();
                const url = new URL(window.location.href);
                const params = new URLSearchParams(url.search);
                params.delete(param);

                if (Array.isArray(allValues)) {
                    allValues.forEach((v) => params.append(param, v));
                } else {
                    params.set(param, allValues);
                }

                window.location.href = `${url.pathname}?${params.toString()}#search`;
            });
        }

        const noneLink = document.getElementById(`${prefix}-none-link`);
        if (noneLink) {
            noneLink.addEventListener("click", (event) => {
                event.preventDefault();
                const url = new URL(window.location.href);
                const params = new URLSearchParams(url.search);
                params.delete(param);
                params.append(param, "");
                window.location.href = `${url.pathname}?${params.toString()}#search`;
            });
        }
    });
}

// Configure all filter dropdowns with All/None links
setupFilterLinks({
    prefix: "availability",
    param: "al",
    allValues: ["C", "R", "I", "E", "U"],
});
setupFilterLinks({ prefix: "category", param: "cat", allValues: "all" });
setupFilterLinks({
    prefix: "type",
    param: "type",
    allValues: ["list", "gang"],
});
setupFilterLinks({ prefix: "house", param: "house", allValues: "all" });
setupFilterLinks({ prefix: "status", param: "status", allValues: "all" });

// Site-wide form-submit "busy" affordance.
//
// This is a deliberate exception to our "JS is for one-off enhancements" rule:
// it applies to *every* form on submit so the whole app feels responsive on
// slow POSTs (content-pack saves, large list edits, etc.) and discourages
// accidental double-submits. It is purely an enhancement — it never calls
// preventDefault(), so forms still submit natively and redirects are followed
// as normal even if this script fails to load.
//
// Two things keep it well-behaved:
//   1. It is non-destructive. We keep the clicked button's original label/icon
//      in the DOM and set aria-busy, rather than replacing the button's
//      innerHTML. CSS (button[aria-busy]) then hides that content and shows a
//      centred spinner over it, so nothing inside the button is thrown away and
//      the original markup can be restored verbatim.
//   2. It restores itself from the bfcache. A pageshow handler clears the busy
//      state when a page is restored after pressing Back, so a form is never
//      left stuck disabled/spinning.
document.addEventListener("DOMContentLoaded", () => {
    const forms = document.querySelectorAll("form");

    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            // Find all submit buttons within this form
            const submitButtons = form.querySelectorAll(
                'button[type="submit"], input[type="submit"]',
            );

            submitButtons.forEach((button) => {
                // Only add the spinner to the button that was clicked, and do
                // it non-destructively: keep the existing label/icon in place
                // and let CSS hide it behind a centred spinner.
                if (button.isSameNode(event.submitter)) {
                    button.setAttribute("aria-busy", "true");

                    // <input type="submit"> can't hold child markup, so only
                    // <button> gets a spinner element prepended.
                    if (button.tagName === "BUTTON") {
                        const spinner = document.createElement("span");
                        // Centred over the button via CSS (button[aria-busy])
                        // rather than flowed beside the label, so small /
                        // icon-only buttons collapse to just the spinner.
                        spinner.className = "spinner-border spinner-border-sm";
                        spinner.setAttribute("role", "status");
                        spinner.setAttribute("aria-hidden", "true");
                        spinner.dataset.submitSpinner = "true";
                        button.prepend(spinner);
                    }
                }

                // Skip buttons that were already disabled before this submit —
                // they aren't ours to re-enable on pageshow, so we must not tag
                // them.
                if (button.disabled) {
                    return;
                }

                // Disable the (previously-enabled) buttons to prevent
                // double-submits. We tag each one we touch so pageshow can
                // restore exactly these.
                // This is setTimeout to ensure it runs after the form submission starts so that any
                // name/value attributes are still submitted.
                setTimeout(() => {
                    button.dataset.submitDisabled = "true";
                    button.disabled = true;
                }, 0);
            });
        });
    });
});

// Clear the form-submit busy state when a page is restored from the bfcache
// (e.g. pressing Back after submitting). Without this the restored DOM keeps
// the disabled buttons and spinners, leaving the form looking permanently busy.
// We only undo what the submit handler above set, identified by our data-*
// markers, so buttons disabled for other reasons are left alone.
window.addEventListener("pageshow", (event) => {
    if (!event.persisted) {
        return;
    }

    // Only touch buttons we tagged. aria-busy is cleared here too (rather than
    // via a separate document-wide [aria-busy] sweep) so we never clobber other
    // UI that legitimately uses aria-busy.
    document
        .querySelectorAll('[data-submit-disabled="true"]')
        .forEach((button) => {
            button.disabled = false;
            button.removeAttribute("aria-busy");
            delete button.dataset.submitDisabled;
        });

    document
        .querySelectorAll('[data-submit-spinner="true"]')
        .forEach((spinner) => spinner.remove());
});

// Find all checkboxes and add change event listeners to any hidden fields
// with the same name in the same form and disable them when the checkbox is checked.
// This is useful for forms where a checkbox controls whether a hidden field should be submitted.
document.addEventListener("DOMContentLoaded", () => {
    const checkboxes = document.querySelectorAll(
        'input[type="checkbox"][name]',
    );

    checkboxes.forEach((checkbox) => {
        // Find any hidden input with the same name in the same form and disable
        // it when the checkbox is checked, so only one value is submitted.
        const sync = () => {
            const form = checkbox.form || checkbox.closest("form");
            if (!form) return;
            // The input may not be within (DOM Child) of the form, so we need to use
            // document.querySelector as a fallback to find it by name and form ID.
            const hiddenInput =
                form.querySelector(
                    `input[type="hidden"][name="${checkbox.name}"]`,
                ) ||
                document.querySelector(
                    `input[type="hidden"][name="${checkbox.name}"][form="${form.id}"]`,
                );
            if (hiddenInput) {
                hiddenInput.disabled = checkbox.checked;
            }
        };

        checkbox.addEventListener("change", sync);
        // Set initial state on load — a pre-checked checkbox must disable its
        // paired hidden input immediately, otherwise both values submit until
        // the box is first toggled.
        sync();
    });
});

// Auto-submit forms when elements with data-gy-toggle-submit are changed
document.addEventListener("DOMContentLoaded", () => {
    // Find all elements with data-gy-toggle-submit attribute
    const autoSubmitElements = document.querySelectorAll(
        "[data-gy-toggle-submit]",
    );

    autoSubmitElements.forEach((element) => {
        element.addEventListener("change", (event) => {
            const formIdentifier = element.getAttribute(
                "data-gy-toggle-submit",
            );
            let form;

            if (formIdentifier) {
                // If a value is provided, find the form by that identifier
                form =
                    document.getElementById(formIdentifier) ||
                    document.querySelector(formIdentifier);
            } else {
                // If no value provided, find the parent form
                form = event.target.form || event.target.closest("form");
            }

            if (form) {
                // Use requestSubmit() rather than submit() so the form's
                // submit event fires (busy spinner) and HTML5 constraint
                // validation runs, matching a real submit-button click.
                form.requestSubmit();
            }
        });
    });
});

// Persist collapse open/closed state in the URL.
//
// Used by the campaign list summary cards (Actions / Assets / Attributes),
// which collapse in single-column view. The server renders the initial state
// from the query param; here we mirror each Bootstrap collapse toggle back into
// the URL (via replaceState, so it survives reload and is linkable) without a
// navigation. The slide animation is Bootstrap's; this is purely state-syncing.
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-gy-collapse-url]").forEach((el) => {
        const key = el.getAttribute("data-gy-collapse-url");
        if (!key) return;

        const setParam = (open) => {
            const url = new URL(window.location.href);
            if (open) {
                url.searchParams.set(key, "1");
            } else {
                url.searchParams.delete(key);
            }
            window.history.replaceState(null, "", url);
        };

        // Guard on event.target so we only react to this element's own
        // transitions, not those of any nested collapse that bubbles up.
        el.addEventListener("shown.bs.collapse", (event) => {
            if (event.target === el) setParam(true);
        });
        el.addEventListener("hidden.bs.collapse", (event) => {
            if (event.target === el) setParam(false);
        });
    });
});

// Handle collapse chevron icon rotation
document.addEventListener("DOMContentLoaded", () => {
    // Find all elements with data-gy-collapse-icon attribute
    const collapseIcons = document.querySelectorAll("[data-gy-collapse-icon]");

    collapseIcons.forEach((icon) => {
        const collapseId = icon.getAttribute("data-gy-collapse-icon");
        if (!collapseId) return;

        const collapseElement = document.getElementById(collapseId);
        if (!collapseElement) return;

        // Rotate icon on show
        collapseElement.addEventListener("show.bs.collapse", () => {
            icon.classList.remove("bi-chevron-down");
            icon.classList.add("bi-chevron-up");
        });

        // Rotate icon on hide
        collapseElement.addEventListener("hide.bs.collapse", () => {
            icon.classList.remove("bi-chevron-up");
            icon.classList.add("bi-chevron-down");
        });
    });
});

// Filterable lists: wire up search inputs with data-gy-filter-target
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-gy-filter-target]").forEach((input) => {
        input.addEventListener("input", () => {
            const query = input.value.toLowerCase();
            const container = document.getElementById(
                input.getAttribute("data-gy-filter-target"),
            );
            if (!container) return;

            const items = container.querySelectorAll("[data-filter-label]");
            let visible = 0;

            items.forEach((item) => {
                const match = item
                    .getAttribute("data-filter-label")
                    .toLowerCase()
                    .includes(query);
                item.classList.toggle("d-none", !match);
                if (match) visible++;
            });

            const emptyMsg = container.querySelector("[data-filter-empty]");
            if (emptyMsg) {
                emptyMsg.style.display = visible === 0 ? "" : "none";
            }
        });
    });
});

// Content packs: enable "Include selected packs" button when ≥1 pack is checked
document.addEventListener("DOMContentLoaded", () => {
    const includePacksBtn = document.getElementById("include-packs-btn");
    if (!includePacksBtn) return;

    const packCheckboxes = document.querySelectorAll('input[name="pack_ids"]');
    if (packCheckboxes.length === 0) return;

    const arrowIcon = includePacksBtn.querySelector("i");
    const arrowClone = arrowIcon ? arrowIcon.cloneNode(true) : null;
    const updateButtonState = () => {
        const checkedCount = [...packCheckboxes].filter(
            (cb) => cb.checked,
        ).length;
        includePacksBtn.disabled = checkedCount === 0;
        const label =
            checkedCount > 0
                ? `Include selected packs (${checkedCount}) `
                : "Include selected packs ";
        includePacksBtn.textContent = label;
        if (arrowClone) {
            includePacksBtn.appendChild(arrowClone.cloneNode(true));
        }
    };

    packCheckboxes.forEach((cb) => {
        cb.addEventListener("change", updateButtonState);
    });

    // Set initial state (disabled unless packs are preselected)
    updateButtonState();
});

// Handle banner dismissal
document.addEventListener("DOMContentLoaded", () => {
    // Find all elements with data-gy-banner-dismiss attribute
    const bannerDismissButtons = document.querySelectorAll(
        "[data-gy-banner-dismiss]",
    );

    bannerDismissButtons.forEach((button) => {
        button.addEventListener("click", (event) => {
            const bannerId = button.getAttribute("data-gy-banner-dismiss");
            if (!bannerId) return;

            // Get CSRF token from Django
            const csrfToken = document.querySelector(
                "[name=csrfmiddlewaretoken]",
            )?.value;

            // Fallback to getting CSRF from cookie if not in form
            const getCookie = (name) => {
                let cookieValue = null;
                if (document.cookie && document.cookie !== "") {
                    const cookies = document.cookie.split(";");
                    for (let i = 0; i < cookies.length; i++) {
                        const cookie = cookies[i].trim();
                        if (
                            cookie.substring(0, name.length + 1) ===
                            name + "="
                        ) {
                            cookieValue = decodeURIComponent(
                                cookie.substring(name.length + 1),
                            );
                            break;
                        }
                    }
                }
                return cookieValue;
            };

            const finalCsrfToken = csrfToken || getCookie("csrftoken");

            fetch("/banner/dismiss/", {
                method: "POST",
                headers: {
                    "X-CSRFToken": finalCsrfToken,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    banner_id: bannerId,
                }),
            })
                .then((response) => {
                    if (!response.ok) {
                        console.error(
                            `Failed to dismiss banner: ${response.statusText}`,
                        );
                    }
                    return response.json();
                })
                .then((data) => {
                    if (!data.success) {
                        console.error("Failed to dismiss banner:", data.error);
                    }
                })
                .catch((error) => {
                    console.error("Error dismissing banner:", error);
                });
        });
    });
});
