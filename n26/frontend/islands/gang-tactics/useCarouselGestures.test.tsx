import { useRef } from "react";
import { fireEvent, render } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useCarouselGestures } from "./useCarouselGestures";

function Carousel({ enabled = true }: { enabled?: boolean }) {
    const ref = useRef<HTMLUListElement>(null);
    useCarouselGestures(ref, enabled);
    return (
        <ul ref={ref}>
            <li>Card</li>
        </ul>
    );
}
function track(enabled = true) {
    const view = render(<Carousel enabled={enabled} />);
    const el = view.container.querySelector("ul")!;
    Object.defineProperties(el, {
        scrollWidth: { value: 1000 },
        clientWidth: { value: 300 },
    });
    return { el, ...view };
}
test("ordinary vertical and native horizontal wheels remain browser gestures", () => {
    const { el } = track();
    for (const delta of [
        { deltaY: 200 },
        { deltaX: 200 },
        { deltaY: 200, ctrlKey: true, shiftKey: true },
    ]) {
        const event = new WheelEvent("wheel", {
            ...delta,
            bubbles: true,
            cancelable: true,
        });
        el.dispatchEvent(event);
        expect(event.defaultPrevented).toBe(false);
        expect(el.scrollLeft).toBe(0);
    }
});
test("Shift wheel scrolls horizontally and restores snap on cleanup", () => {
    const { el, unmount } = track();
    const event = new WheelEvent("wheel", {
        deltaY: 100,
        shiftKey: true,
        cancelable: true,
    });
    el.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(el.scrollLeft).toBe(100);
    expect(el.style.scrollSnapType).toBe("none");
    unmount();
    expect(el.style.scrollSnapType).toBe("");
});
test("disabled carousel leaves wheel behavior unchanged", () => {
    const { el } = track(false);
    fireEvent.wheel(el, { deltaY: 100, shiftKey: true });
    expect(el.scrollLeft).toBe(0);
});
