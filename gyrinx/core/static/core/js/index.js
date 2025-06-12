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

    element.addEventListener("change", (event) => {
        targets.forEach((target) => {
            if (target.value !== event.target.value) {
                target.value = event.target.value;
            }
        });
    });
});

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
                // Store original content
                const originalContent = button.innerHTML;

                // Create spinner SVG
                const spinnerSVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="16" height="16" style="display: inline-block; vertical-align: middle;"><circle fill="currentColor" stroke="currentColor" stroke-width="4" r="15" cx="40" cy="100"><animate attributeName="opacity" calcMode="spline" dur="2" values="1;0;1;" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite" begin="-.4"></animate></circle><circle fill="currentColor" stroke="currentColor" stroke-width="4" r="15" cx="100" cy="100"><animate attributeName="opacity" calcMode="spline" dur="2" values="1;0;1;" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite" begin="-.2"></animate></circle><circle fill="currentColor" stroke="currentColor" stroke-width="4" r="15" cx="160" cy="100"><animate attributeName="opacity" calcMode="spline" dur="2" values="1;0;1;" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite" begin="0"></animate></circle></svg>`;

                // Replace button content with spinner
                button.innerHTML = spinnerSVG;

                // Disable the button
                button.disabled = true;

                // Add a data attribute to prevent multiple submissions
                button.setAttribute("data-submitting", "true");
            });
        });
    });
});
