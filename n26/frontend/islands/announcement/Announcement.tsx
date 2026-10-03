import { useState } from "react";
import cotton from "../../generated/cotton.json";
import { Icon } from "../../ui";

export type AnnouncementProps = {
    tone: "info" | "success" | "warning" | "danger" | "neutral";
    icon: string;
    message: string;
    ctaText: string;
    ctaUrl: string;
    dismissible: boolean;
    dismissUrl: string;
    bannerId: string;
    csrfToken: string;
    id: string;
    className: string;
};

const TONE_ICON = {
    success: "circle-check",
    warning: "triangle-alert",
    danger: "triangle-alert",
    info: "info",
    neutral: "info",
} as const;

function iconName(icon: string, tone: AnnouncementProps["tone"]) {
    if (icon === "none") return "";
    const chosen = icon || TONE_ICON[tone];
    if (chosen in cotton.icons) return chosen as keyof typeof cotton.icons;
    return TONE_ICON[tone];
}

export function Announcement({
    tone,
    icon,
    message,
    ctaText,
    ctaUrl,
    dismissible,
    dismissUrl,
    bannerId,
    csrfToken,
    id,
    className,
}: AnnouncementProps) {
    const [shown, setShown] = useState(true);
    if (!shown) return null;
    const drawing = iconName(icon, tone);

    function dismiss() {
        setShown(false);
        if (!dismissUrl || !bannerId) return;
        void fetch(dismissUrl, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ banner_id: bannerId }),
        });
    }

    return (
        <aside
            id={id || undefined}
            className={`n26-announcement ${className}`.trim()}
            data-tone={tone}
            aria-label="Site announcement"
        >
            <div className="n26-site-container n26-announcement-row">
                {drawing && (
                    <Icon
                        name={drawing}
                        className="size-5 shrink-0"
                        strokeWidth={1.7}
                    />
                )}
                <div className="n26-announcement-message">
                    <span>{message}</span>
                    {ctaText && ctaUrl && (
                        <a
                            href={ctaUrl}
                            className="n26-announcement-cta focus-ring"
                        >
                            {ctaText}
                            <Icon
                                name="arrow-right"
                                className="size-4"
                                strokeWidth={2}
                            />
                        </a>
                    )}
                </div>
                {dismissible && (
                    <button
                        type="button"
                        className="n26-announcement-dismiss focus-ring"
                        aria-label="Dismiss announcement"
                        onClick={dismiss}
                    >
                        <Icon name="x" className="size-4" strokeWidth={2} />
                    </button>
                )}
            </div>
        </aside>
    );
}
