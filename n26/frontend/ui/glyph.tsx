import { createElement } from "react";
import cotton from "../generated/cotton.json";

/** An icon from the exported set, for ui modules that cannot import `Icon`. */
export function Glyph({
    name,
    className,
    strokeWidth = 1.7,
}: {
    name: keyof typeof cotton.icons;
    className: string;
    strokeWidth?: number;
}) {
    return (
        <svg
            className={className}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
        >
            {cotton.icons[name].map(({ tag, attrs }, key) =>
                createElement(tag, { ...attrs, key }),
            )}
        </svg>
    );
}
