import { createContext, useContext, useId } from "react";
import cotton from "../generated/cotton.json";

const BusyControl = createContext<string | null>(null);
export const BusyControlScope = BusyControl.Provider;

/** React supplies the state; the shared busy stylesheet preserves control geometry. */
export function useBusyControl(busy = false) {
    const id = useId();
    const active = useContext(BusyControl);
    return {
        "data-busy-id": id,
        ...(busy || active === id
            ? {
                  "data-busy": "on",
                  "data-busy-disabled": "",
                  "aria-busy": true as const,
              }
            : {}),
    };
}

export function Spinner({ label }: { label: string }) {
    return (
        <svg
            role="status"
            aria-label={label}
            className={cotton.spinner[0]}
            viewBox="0 0 24 24"
            fill="none"
        >
            <circle
                className={cotton.spinner[1]}
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
            />
            <path
                className={cotton.spinner[2]}
                fill="currentColor"
                d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z"
            />
        </svg>
    );
}
