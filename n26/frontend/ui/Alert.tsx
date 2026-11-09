import { useState, type ComponentProps } from "react";
import cotton from "../generated/cotton.json";

export type AlertTone = keyof typeof cotton.alert;

export function Alert({
    tone = "info",
    children,
    dismissible = true,
    className = "",
    ...props
}: ComponentProps<"div"> & {
    tone?: AlertTone;
    dismissible?: boolean;
}) {
    const [visible, setVisible] = useState(true);
    if (!visible) return null;
    const recipe = cotton.alert[tone];
    return (
        <div
            {...props}
            role={props.role ?? "alert"}
            data-message={tone}
            className={className ? `${recipe.root} ${className}` : recipe.root}
        >
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
