import { useEffect, useRef, useState, type MouseEvent } from "react";
import {
    ButtonLink,
    type ButtonLinkSize,
    type ButtonLinkVariant,
    Icon,
} from "../../ui";

export type ShareProps = {
    url: string;
    message: string;
    size: ButtonLinkSize;
    variant: ButtonLinkVariant;
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

export function Share({ url, message, size, variant }: ShareProps) {
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
        // A modified click, or a link aimed at another window, is the
        // browser's to handle: open in a new tab, and so on.
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
        // Share the browser's absolute href, not the path the template passed.
        share(link.href);
    }

    return (
        <>
            <ButtonLink
                href={url}
                size={size}
                variant={variant}
                aria-label="Share"
                className={FIT}
                onClick={onClick}
            >
                <Icon name="share-2" className="size-3.5" strokeWidth={1.7} />
                <span className="hidden sm:inline">Share</span>
            </ButtonLink>
            {/* Mounted from the start so a reader announces the text when it appears. */}
            <span
                role="status"
                className={copied ? "text-xs text-muted" : "sr-only"}
            >
                {copied ? message : ""}
            </span>
        </>
    );
}
