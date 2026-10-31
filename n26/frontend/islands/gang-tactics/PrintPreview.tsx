import {
    useEffect,
    useRef,
    useState,
    type CSSProperties,
    type ReactElement,
} from "react";

export function PrintPreview({
    orientation,
    scale,
    items,
}: {
    orientation: string;
    scale: number;
    items: ReactElement[];
}) {
    const width = orientation === "landscape" ? 297 : 210;
    const height = orientation === "landscape" ? 210 : 297;
    const columns = Math.max(
        1,
        Math.floor((width - 16 + (2 * scale) / 100) / ((78 * scale) / 100)),
    );
    const rows = Math.max(
        1,
        Math.floor((height - 16 + (2 * scale) / 100) / ((113 * scale) / 100)),
    );
    const perPage = columns * rows;
    const pages = Array.from(
        { length: Math.ceil(items.length / perPage) },
        (_, index) => items.slice(index * perPage, (index + 1) * perPage),
    );
    const ref = useRef<HTMLDivElement>(null);
    const [fit, setFit] = useState(1);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const observer = new ResizeObserver(() =>
            setFit(Math.min(1, (el.clientWidth - 24) / ((width * 96) / 25.4))),
        );
        observer.observe(el);
        return () => observer.disconnect();
    }, [width]);
    return (
        <div
            className="n26-tactic-print-pages"
            ref={ref}
            style={
                {
                    "--tactic-page-width": `${width}mm`,
                    "--tactic-page-height": `${height}mm`,
                    "--tactic-preview-fit": fit,
                } as CSSProperties
            }
        >
            {pages.map((page, index) => (
                <section
                    className="n26-tactic-print-page"
                    key={index}
                    aria-label={`Print page ${index + 1}`}
                >
                    <p className="n26-tactic-page-label">
                        Page {index + 1} of {pages.length}
                    </p>
                    <ul className="n26-tactic-grid n26-print-tactic-grid">
                        {page}
                    </ul>
                </section>
            ))}
        </div>
    );
}
