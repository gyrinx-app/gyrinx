import { readFileSync } from "node:fs";
import { expect, test, vi } from "vitest";

test("the native busy guard blocks repeats while React owners retain cancellation", () => {
    const frame = document.createElement("iframe");
    document.body.append(frame);
    try {
        const doc = frame.contentDocument!;
        new Function(
            "window",
            "document",
            readFileSync("n26/core/static/n26/busy.js", "utf8"),
        )(frame.contentWindow, doc);
        doc.body.innerHTML =
            '<button type="button" data-busy="on" id="native">Save</button><div data-busy="off"><button type="button" data-busy="on" id="react"><span>Hide card</span></button></div>';
        const native = doc.getElementById("native")!;
        const react = doc.getElementById("react")!;
        const saved = vi.fn();
        const cancelled = vi.fn();
        native.addEventListener("click", saved);
        react.addEventListener("click", cancelled);
        expect(
            native.dispatchEvent(
                new MouseEvent("click", { bubbles: true, cancelable: true }),
            ),
        ).toBe(false);
        expect(saved).not.toHaveBeenCalled();
        expect(
            react.firstElementChild!.dispatchEvent(
                new MouseEvent("click", { bubbles: true, cancelable: true }),
            ),
        ).toBe(true);
        expect(cancelled).toHaveBeenCalledOnce();
    } finally {
        frame.remove();
    }
});
