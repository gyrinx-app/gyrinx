import { useState, type MouseEvent } from "react";
import { Icon } from "../../ui";

export type AnnouncementProps = {
    dismissUrl: string;
    bannerId: string;
    csrfToken: string;
};

export function Announcement({
    dismissUrl,
    bannerId,
    csrfToken,
}: AnnouncementProps) {
    const [failed, setFailed] = useState(false);
    const [pending, setPending] = useState(false);

    async function dismiss(event: MouseEvent<HTMLButtonElement>) {
        const bar = event.currentTarget.closest(".n26-announcement");
        if (!dismissUrl || !bannerId) {
            if (bar instanceof HTMLElement) bar.hidden = true;
            return;
        }
        setPending(true);
        setFailed(false);
        try {
            const response = await fetch(dismissUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ banner_id: bannerId }),
            });
            if (!response.ok) {
                setFailed(true);
                return;
            }
            if (bar instanceof HTMLElement) bar.hidden = true;
        } catch {
            setFailed(true);
        } finally {
            setPending(false);
        }
    }

    return (
        <>
            <button
                type="button"
                className="n26-announcement-dismiss focus-ring"
                aria-label="Dismiss announcement"
                disabled={pending}
                onClick={(event) => {
                    void dismiss(event);
                }}
            >
                <Icon name="x" className="size-4" strokeWidth={2} />
            </button>
            {failed && (
                <p role="alert" className="mt-1 max-w-48 text-right text-xs">
                    This announcement is still showing. Try again.
                </p>
            )}
        </>
    );
}
