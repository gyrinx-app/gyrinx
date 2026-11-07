import { useState, type ReactNode } from "react";
import cotton from "../generated/cotton.json";

export type AlertTone = keyof typeof cotton.alert;

export function Alert({
    tone = "info",
    children,
    dismissible = true,
}: {
    tone?: AlertTone;
    children: ReactNode;
    dismissible?: boolean;
}) {
    const [visible, setVisible] = useState(true);
    if (!visible) return null;
    const recipe = cotton.alert[tone];
    return (
        <div role="alert" data-message={tone} className={recipe.root}>
            <svg
                className={recipe.icon}
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
                aria-hidden="true"
            >
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d={recipe.path}
                />
            </svg>
            <div className={recipe.content}>
                <div className={recipe.body}>{children}</div>
            </div>
            {dismissible && (
                <button
                    type="button"
                    aria-label="Dismiss"
                    className={recipe.dismiss}
                    onClick={() => setVisible(false)}
                >
                    <svg
                        className={recipe.close}
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={2}
                        stroke="currentColor"
                        aria-hidden="true"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d={recipe.closePath}
                        />
                    </svg>
                </button>
            )}
        </div>
    );
}
