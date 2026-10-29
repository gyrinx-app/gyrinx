import { useLayoutEffect, type RefObject } from "react";

/** Find the largest readable size that leaves one fifth of the body free. */
export function fitRules(
    available: number,
    maximum: number,
    measure: (size: number) => number,
) {
    if (measure(maximum) <= available * 0.8) return maximum;
    let low = 0;
    let high = maximum;
    for (let attempt = 0; attempt < 12; attempt++) {
        const middle = (low + high) / 2;
        if (measure(middle) <= available * 0.8) low = middle;
        else high = middle;
    }
    return Math.floor(low * 100) / 100;
}

export function useFittedRules(
    ref: RefObject<HTMLDivElement | null>,
    content: unknown,
    enabled = true,
) {
    useLayoutEffect(() => {
        const box = ref.current;
        const rules = box?.firstElementChild as HTMLElement | null;
        if (!enabled || !box || !rules) return;
        let disposed = false;
        const fit = () => {
            if (disposed || !box.clientHeight) return;
            const style = getComputedStyle(box);
            const available =
                box.clientHeight -
                parseFloat(style.paddingTop) -
                parseFloat(style.paddingBottom);
            // The probe inherits the layout's maximum size (including print scale).
            rules.style.removeProperty("font-size");
            const maximum = parseFloat(getComputedStyle(rules).fontSize);
            const size = fitRules(available, maximum, (candidate) => {
                rules.style.fontSize = `${candidate}px`;
                return rules.offsetHeight;
            });
            rules.style.fontSize = `${size}px`;
        };
        fit();
        const observer = new ResizeObserver(fit);
        observer.observe(box);
        // Print uses physical dimensions rather than screen zoom.
        window.addEventListener("beforeprint", fit);
        window.addEventListener("afterprint", fit);
        document.fonts?.ready.then(fit);
        return () => {
            disposed = true;
            observer.disconnect();
            window.removeEventListener("beforeprint", fit);
            window.removeEventListener("afterprint", fit);
        };
    }, [ref, content, enabled]);
}
