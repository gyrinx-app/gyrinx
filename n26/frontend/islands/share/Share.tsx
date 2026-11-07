import { useEffect, useRef, useState, type MouseEvent } from "react";
import { useQueryHref } from "../../runtime/useQueryHref";
import {
    ButtonLink,
    type ButtonLinkSize,
    type ButtonLinkVariant,
    Icon,
} from "../../ui";

export type ShareProps = {
    url: string;
    label?: string;
    compact?: boolean;
    message: string;
    size: ButtonLinkSize;
    variant: ButtonLinkVariant;
    queryKeys?: string[];
};

const COPIED_FOR_MS = 4000;
// These overrides hold the control to 20px so it sits on a breadcrumb row.
const FIT = "!inline-flex min-h-5 items-center gap-1.5 !py-px";

export const shareNavigation = {
    assign(url: string) {
        window.location.assign(url);
    },
};

function isAbort(error: unknown) {
    return (
        typeof error === "object" &&
        error !== null &&
        "name" in error &&
        error.name === "AbortError"
    );
}

export function Share({
    url,
    message,
    size,
    variant,
    label = "Share",
    compact = true,
    queryKeys,
}: ShareProps) {
    const href = useQueryHref(url, queryKeys);
    const [copied, setCopied] = useState(false);
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(
        () => () => {
            if (timer.current !== null) clearTimeout(timer.current);
        },
        [],
    );

    function showCopied() {
        setCopied(true);
        if (timer.current !== null) clearTimeout(timer.current);
        timer.current = setTimeout(() => setCopied(false), COPIED_FOR_MS);
    }

    function follow(absoluteUrl: string) {
        shareNavigation.assign(absoluteUrl);
    }

    function copy(absoluteUrl: string) {
        const clipboard = navigator.clipboard;
        if (!clipboard) {
            follow(absoluteUrl);
            return;
        }
        clipboard.writeText(absoluteUrl).then(
            () => showCopied(),
            () => follow(absoluteUrl),
        );
    }

    function share(absoluteUrl: string) {
        const opened = navigator.share?.bind(navigator);
        const canShare = navigator.canShare?.bind(navigator);
        const rejected = (error: unknown) => {
            if (!isAbort(error)) copy(absoluteUrl);
        };
        if (opened && (!canShare || canShare({ url: absoluteUrl }))) {
            try {
                opened({ url: absoluteUrl }).catch(rejected);
            } catch (error) {
                rejected(error);
            }
            return;
        }
        copy(absoluteUrl);
    }

    function onClick(event: MouseEvent<HTMLAnchorElement>) {
        const link = event.currentTarget;
        // Leave modified clicks and other-window targets to the browser.
        if (
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        )
            return;
        if (link.target && link.target !== "_self") return;
        event.preventDefault();
        // Use the browser-resolved absolute URL for sharing and clipboard fallback.
        share(link.href);
    }

    return (
        <>
            <ButtonLink
                href={href}
                size={size}
                variant={variant}
                aria-label={label}
                className={compact ? FIT : "inline-flex items-center gap-1.5"}
                onClick={onClick}
            >
                <Icon name="share-2" className="size-3.5" strokeWidth={1.7} />
                <span className={compact ? "hidden sm:inline" : undefined}>
                    {label}
                </span>
            </ButtonLink>
            {/*
             * Mount the live region before its content changes so screen readers announce
             * the result.
             */}
            <span
                role="status"
                className={copied ? "text-xs text-muted" : "sr-only"}
            >
                {copied ? message : ""}
            </span>
        </>
    );
}
