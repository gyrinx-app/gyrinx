import { createElement } from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PostBattleToolbar } from "./PostBattleToolbar";
const props = {
    countOne: "1 model took part",
    countMany: "{n} models took part",
    plusOne: "Add 1 XP",
    plusMany: "Add 1 XP to {n} models",
    minusOne: "Remove 1 XP",
    minusMany: "Remove 1 XP from {n} models",
};
afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
});
describe("PostBattleToolbar bridge", () => {
    it("marks reinforcements explicitly, preserves XP and permits an individual override", async () => {
        vi.resetModules();
        vi.stubGlobal(
            "fetch",
            vi.fn(() => new Promise(() => {})),
        );
        const listeners = vi.spyOn(window, "addEventListener");
        document.body.innerHTML =
            '<form id="post-battle-form"><input name="revision" value="1"><input name="generation" value="1"><div data-react-module="post-battle-toolbar" id="toolbar"></div><input id="a" type="checkbox" data-xp-participant="a-xp" checked><input id="a-xp" value="2"><input id="b" type="checkbox" data-xp-participant="b-xp"><input id="b-xp" value=""><input id="confirmation" type="checkbox"></form><p id="draft-save-status"></p>';
        await import("../../../core/static/n26/post-battle.js");
        render(createElement(PostBattleToolbar, props), {
            container: document.getElementById("toolbar"),
        });
        const user = userEvent.setup();
        expect(screen.getByRole("status").textContent).toBe(
            "1 model took part",
        );
        await user.click(
            screen.getByRole("button", { name: "Mark all attended" }),
        );
        expect(screen.getByRole("status").textContent).toBe(
            "2 models took part",
        );
        expect(document.getElementById("b").checked).toBe(true);
        expect(document.getElementById("b-xp").value).toBe("");
        expect(document.getElementById("confirmation").checked).toBe(false);
        await user.click(
            screen.getByRole("button", { name: "Add 1 XP to 2 models" }),
        );
        expect(document.getElementById("a-xp").value).toBe("3");
        expect(document.getElementById("b-xp").value).toBe("1");
        act(() => {
            const b = document.getElementById("b");
            b.checked = false;
            b.dispatchEvent(new Event("input", { bubbles: true }));
        });
        expect(screen.getByRole("status").textContent).toBe(
            "1 model took part",
        );
        expect(
            screen.getByRole("button", {
                name: "Mark all attended",
            }).disabled,
        ).toBe(false);
        for (const [type, handler, options] of listeners.mock.calls)
            window.removeEventListener(type, handler, options);
        listeners.mockRestore();
    });
});
