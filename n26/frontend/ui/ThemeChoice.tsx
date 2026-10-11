import { useEffect, useState } from "react";
import { Glyph } from "./glyph";

type Mode = "light" | "dark" | "system";

export type ThemeChoiceProps = {
    /** The key the page's head script reads before first paint. */
    storageKey: string;
    defaultMode: Mode;
    /** Each scheme with its words and drawing, in the order shown. */
    choices: [Mode, string, "sun" | "moon" | "monitor"][];
    /** A caller's classes for the group. */
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
 * Light, dark or the device's choice. The `dark` class on the root element
 * is the shared truth: another control or the head script may change it, and
 * this follows; another tab's choice arrives through storage.
 */
export function ThemeChoice({
    storageKey,
    defaultMode,
    choices,
    className = "",
}: ThemeChoiceProps) {
    // The head script painted from the same two, so this matches the page.
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
            // A control sharing the key stored its choice first; that keeps System.
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
            // A blocked store still changes the page for this visit.
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
