import { useEffect, useState } from "react";
import { Glyph } from "./glyph";

type Mode = "light" | "dark" | "system";

export type ThemeChoiceProps = {
    /** The key the page's head script reads before first paint. */
    storageKey: string;
    defaultMode: Mode;
    /** Theme identifier, label and icon for each option, in display order. */
    choices: [Mode, string, "sun" | "moon" | "monitor"][];
    /** Additional classes for the group. */
    className?: string;
};

const QUERY = "(prefers-color-scheme: dark)";

function stored(key: string): Mode | null {
    try {
        const value = localStorage.getItem(key);
        return value === "light" || value === "dark" || value === "system"
            ? value
            : null;
    } catch {
        return null;
    }
}

function darkFor(mode: Mode) {
    return (
        mode === "dark" ||
        (mode === "system" && window.matchMedia(QUERY).matches)
    );
}

/**
 * Synchronise the theme with the root dark class, device preference and shared
 * storage key. Observe class changes from other controls and storage changes
 * from other tabs.
 */
export function ThemeChoice({
    storageKey,
    defaultMode,
    choices,
    className = "",
}: ThemeChoiceProps) {
    // Use the same stored choice and default as the head script to match
    // the initial page theme.
    const [mode, setMode] = useState<Mode>(
        () => stored(storageKey) ?? defaultMode,
    );
    const [deviceDark, setDeviceDark] = useState(
        () => window.matchMedia(QUERY).matches,
    );

    useEffect(() => {
        document.documentElement.classList.toggle("dark", darkFor(mode));
    }, [mode, deviceDark]);

    useEffect(() => {
        const media = window.matchMedia(QUERY);
        const followDevice = () => setDeviceDark(media.matches);
        media.addEventListener("change", followDevice);
        const observer = new MutationObserver(() => {
            const dark = document.documentElement.classList.contains("dark");
            // Prefer the saved mode when it matches the class, preserving
            // System rather than replacing it with Light or Dark.
            const saved = stored(storageKey);
            setMode((current) =>
                saved && darkFor(saved) === dark
                    ? saved
                    : dark === darkFor(current)
                      ? current
                      : dark
                        ? "dark"
                        : "light",
            );
        });
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["class"],
        });
        const followOtherTab = (event: StorageEvent) => {
            if (event.key === storageKey)
                setMode(stored(storageKey) ?? defaultMode);
        };
        window.addEventListener("storage", followOtherTab);
        return () => {
            media.removeEventListener("change", followDevice);
            observer.disconnect();
            window.removeEventListener("storage", followOtherTab);
        };
    }, [storageKey, defaultMode]);

    function choose(next: Mode) {
        try {
            localStorage.setItem(storageKey, next);
        } catch {
            // Apply the choice for this page even when storage is
            // unavailable.
        }
        setMode(next);
    }

    return (
        <div
            role="group"
            aria-label="Theme"
            className={`mx-3 my-1 flex gap-1 rounded-control bg-ink-100 p-1 dark:bg-ink-800 ${className}`}
        >
            {choices.map(([scheme, label, icon]) => {
                const checked = mode === scheme;
                return (
                    <button
                        key={scheme}
                        type="button"
                        role="menuitemradio"
                        tabIndex={-1}
                        aria-checked={checked}
                        aria-label={
                            scheme === "system"
                                ? `System — this device is set to ${deviceDark ? "dark" : "light"}`
                                : undefined
                        }
                        onClick={() => choose(scheme)}
                        className={`flex flex-1 cursor-pointer flex-col items-center gap-1 whitespace-nowrap rounded-control px-2 py-1.5 text-xs transition-colors focus-ring ${
                            checked
                                ? "bg-white font-medium text-ink-900 shadow-sm dark:bg-ink-600 dark:text-white"
                                : "text-ink-600 hover:text-ink-900 dark:text-ink-400 dark:hover:text-white"
                        }`}
                    >
                        <Glyph name={icon} className="size-4" />
                        {label}
                    </button>
                );
            })}
        </div>
    );
}
