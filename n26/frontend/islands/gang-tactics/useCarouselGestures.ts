import { useEffect, useState, type RefObject } from "react";

export function useCarouselGestures(
    ref: RefObject<HTMLUListElement | null>,
    enabled: boolean,
) {
    const [dragging, setDragging] = useState(false);
    useEffect(() => {
        const el = ref.current;
        if (!el || !enabled) return;
        let pointer: {
            id: number;
            x: number;
            scroll: number;
            moved: boolean;
        } | null = null;
        let suppressClick = false;
        let timer: ReturnType<typeof setTimeout> | undefined;
        let wheelTimer: ReturnType<typeof setTimeout> | undefined;
        const originalSnap = el.style.scrollSnapType;
        function down(event: PointerEvent) {
            if (
                event.pointerType === "touch" ||
                event.button !== 0 ||
                (event.target as HTMLElement).closest(
                    "button, a, input, label",
                ) ||
                el!.scrollWidth <= el!.clientWidth
            )
                return;
            pointer = {
                id: event.pointerId,
                x: event.clientX,
                scroll: el!.scrollLeft,
                moved: false,
            };
        }
        function move(event: PointerEvent) {
            if (!pointer || event.pointerId !== pointer.id) return;
            const delta = event.clientX - pointer.x;
            if (!pointer.moved && Math.abs(delta) < 5) return;
            if (!pointer.moved) {
                pointer.moved = true;
                setDragging(true);
                el!.setPointerCapture(event.pointerId);
            }
            event.preventDefault();
            el!.scrollLeft = pointer.scroll - delta;
        }
        function up(event: PointerEvent) {
            if (!pointer || event.pointerId !== pointer.id) return;
            suppressClick = pointer.moved;
            if (el!.hasPointerCapture(event.pointerId))
                el!.releasePointerCapture(event.pointerId);
            pointer = null;
            setDragging(false);
            clearTimeout(timer);
            timer = setTimeout(() => {
                suppressClick = false;
            }, 0);
        }
        function click(event: MouseEvent) {
            if (suppressClick) {
                event.preventDefault();
                event.stopPropagation();
            }
        }
        function wheel(event: WheelEvent) {
            if (
                !event.shiftKey ||
                event.ctrlKey ||
                event.metaKey ||
                Math.abs(event.deltaX) > Math.abs(event.deltaY)
            )
                return;
            const delta =
                event.deltaY *
                (event.deltaMode === 1
                    ? 16
                    : event.deltaMode === 2
                      ? el!.clientWidth
                      : 1);
            const max = el!.scrollWidth - el!.clientWidth;
            if (
                (delta > 0 && el!.scrollLeft < max - 1) ||
                (delta < 0 && el!.scrollLeft > 1)
            ) {
                event.preventDefault();
                el!.style.scrollSnapType = "none";
                el!.scrollLeft += delta;
                clearTimeout(wheelTimer);
                wheelTimer = setTimeout(() => {
                    el!.style.scrollSnapType = originalSnap;
                }, 160);
            }
        }
        el.addEventListener("pointerdown", down);
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", up);
        el.addEventListener("pointercancel", up);
        window.addEventListener("pointerup", up);
        el.addEventListener("click", click, true);
        el.addEventListener("wheel", wheel, { passive: false });
        return () => {
            clearTimeout(timer);
            clearTimeout(wheelTimer);
            el.style.scrollSnapType = originalSnap;
            el.removeEventListener("pointerdown", down);
            el.removeEventListener("pointermove", move);
            el.removeEventListener("pointerup", up);
            el.removeEventListener("pointercancel", up);
            window.removeEventListener("pointerup", up);
            el.removeEventListener("click", click, true);
            el.removeEventListener("wheel", wheel);
        };
    }, [ref, enabled]);
    return dragging;
}
