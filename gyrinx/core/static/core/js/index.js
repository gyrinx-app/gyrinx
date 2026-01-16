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
    const targets = Array.from(
        document.querySelectorAll(
            `[data-gy-sync=${element.getAttribute("data-gy-sync")}`,
        ),
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

// Equipment list filter toggle functionality
document.addEventListener("DOMContentLoaded", () => {
    const filterSwitch = document.getElementById("filter-switch");
    const illegalCheckbox = document.getElementById("al-i");

    // Find the availability button by its ID
    const availabilityButton = document.getElementById(
        "availability-dropdown-button",
    );

    if (filterSwitch && availabilityButton) {
        filterSwitch.addEventListener("change", (event) => {
            if (event.target.checked) {
                // Equipment list is ON - disable availability
                availabilityButton.classList.add("disabled");
                availabilityButton.setAttribute("disabled", "");
                availabilityButton.removeAttribute("data-bs-toggle");
                availabilityButton.removeAttribute("aria-expanded");
                availabilityButton.removeAttribute("data-bs-auto-close");

                // Remove existing tooltip if any
                const existingTooltip = bootstrap.Tooltip.getInstance(
                    availabilityButton.parentElement,
                );
                if (existingTooltip) {
                    existingTooltip.dispose();
                }

                // Add tooltip
                availabilityButton.parentElement.setAttribute(
                    "data-bs-toggle",
                    "tooltip",
                );
                availabilityButton.parentElement.setAttribute(
                    "data-bs-placement",
                    "top",
                );
                availabilityButton.parentElement.setAttribute(
                    "title",
                    "Availability filters are disabled when Equipment List is toggled on. All equipment on the fighter's equipment list is shown regardless of availability.",
                );
                new bootstrap.Tooltip(availabilityButton.parentElement);
            } else {
                // Equipment list is OFF - enable availability
                availabilityButton.classList.remove("disabled");
                availabilityButton.removeAttribute("disabled");
                availabilityButton.setAttribute("data-bs-toggle", "dropdown");
                availabilityButton.setAttribute("aria-expanded", "false");
                availabilityButton.setAttribute(
                    "data-bs-auto-close",
                    "outside",
                );

                // Remove tooltip
                const tooltip = bootstrap.Tooltip.getInstance(
                    availabilityButton.parentElement,
                );
                if (tooltip) {
                    tooltip.dispose();
                }
                availabilityButton.parentElement.removeAttribute(
                    "data-bs-toggle",
                );
                availabilityButton.parentElement.removeAttribute(
                    "data-bs-placement",
                );
                availabilityButton.parentElement.removeAttribute("title");

                // Automatically tick the illegal checkbox when equipment list is unticked
                if (illegalCheckbox) {
                    illegalCheckbox.checked = true;
                }
            }
        });
    }
});

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

// Add loading spinner to form submit buttons
document.addEventListener("DOMContentLoaded", () => {
    const forms = document.querySelectorAll("form");

    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            // Find all submit buttons within this form
            const submitButtons = form.querySelectorAll(
                'button[type="submit"], input[type="submit"]',
            );

            submitButtons.forEach((button) => {
                // Only modify the button if it is the one that was clicked
                if (button.isSameNode(event.submitter)) {
                    button.style.width = `${button.offsetWidth}px`;
                    button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>`;
                }

                // Disable all the buttons
                // This is setTimeout to ensure it runs after the form submission starts so that any
                // name/value attributes are still submitted.
                setTimeout(() => {
                    button.disabled = true;
                }, 0);
            });
        });
    });
});

// Find all checkboxes and add change event listeners to any hidden fields
// with the same name in the same form and disable them when the checkbox is checked.
// This is useful for forms where a checkbox controls whether a hidden field should be submitted.
document.addEventListener("DOMContentLoaded", () => {
    const checkboxes = document.querySelectorAll(
        'input[type="checkbox"][name]',
    );

    checkboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", (event) => {
            // If this is a checkbox, find any hidden input with the same name in the same form
            // and disable it when the checkbox is checked
            const form = checkbox.form || checkbox.closest("form");
            if (form) {
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
                    // Set initial state
                    hiddenInput.disabled = checkbox.checked;
                }
            }
        });
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
                // Submit the form
                form.submit();
            }
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
