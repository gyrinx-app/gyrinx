import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeChoice, type ThemeChoiceProps } from "./ThemeChoice";

const props: ThemeChoiceProps = {
    storageKey: "theme",
    defaultMode: "system",
    choices: [
        ["light", "Light", "sun"],
        ["dark", "Dark", "moon"],
        ["system", "System", "monitor"],
    ],
};

let deviceDark = false;
let listeners: (() => void)[] = [];

function device(dark: boolean) {
    deviceDark = dark;
    act(() => listeners.forEach((listener) => listener()));
}

beforeEach(() => {
    deviceDark = false;
    listeners = [];
    vi.stubGlobal(
        "matchMedia",
        vi.fn(() => ({
            get matches() {
                return deviceDark;
            },
            addEventListener: (_: string, listener: () => void) =>
                listeners.push(listener),
            removeEventListener: (_: string, listener: () => void) => {
                listeners = listeners.filter((other) => other !== listener);
            },
        })),
    );
    localStorage.clear();
    document.documentElement.classList.remove("dark");
});
afterEach(() => vi.unstubAllGlobals());

const choice = (name: RegExp) => screen.getByRole("menuitemradio", { name });
const dark = () => document.documentElement.classList.contains("dark");

describe("theme choice", () => {
    it("starts from the stored choice and paints it", () => {
        localStorage.setItem("theme", "dark");
        render(<ThemeChoice {...props} />);
        expect(choice(/^Dark$/).getAttribute("aria-checked")).toBe("true");
        expect(dark()).toBe(true);
    });

    it("adopts what the head script painted when nothing is stored", () => {
        document.documentElement.classList.add("dark");
        render(<ThemeChoice {...props} />);
        expect(choice(/^Dark$/).getAttribute("aria-checked")).toBe("true");
    });

    it("stores and paints a choice", async () => {
        const user = userEvent.setup();
        localStorage.setItem("theme", "dark");
        render(<ThemeChoice {...props} />);
        await user.click(choice(/^Light$/));
        expect(localStorage.getItem("theme")).toBe("light");
        expect(dark()).toBe(false);
        expect(choice(/^Light$/).getAttribute("aria-checked")).toBe("true");
        expect(choice(/^Dark$/).getAttribute("aria-checked")).toBe("false");
    });

    it("follows the device in System and names what it asks for", async () => {
        const user = userEvent.setup();
        render(<ThemeChoice {...props} />);
        await user.click(choice(/^System/));
        expect(choice(/^System/).getAttribute("aria-label")).toBe(
            "System — your device asks for light",
        );
        device(true);
        expect(dark()).toBe(true);
        expect(choice(/^System/).getAttribute("aria-label")).toBe(
            "System — your device asks for dark",
        );
    });

    it("follows another control and another tab", async () => {
        render(<ThemeChoice {...props} />);
        await act(async () => {
            document.documentElement.classList.add("dark");
        });
        expect(choice(/^Dark$/).getAttribute("aria-checked")).toBe("true");
        localStorage.setItem("theme", "light");
        act(() => {
            window.dispatchEvent(
                new StorageEvent("storage", {
                    key: "theme",
                    newValue: "light",
                }),
            );
        });
        expect(choice(/^Light$/).getAttribute("aria-checked")).toBe("true");
        expect(dark()).toBe(false);
    });
});
