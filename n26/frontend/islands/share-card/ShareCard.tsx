import { domToBlob } from "modern-screenshot";
import { useEffect, useState, type MouseEvent } from "react";
import { Button, ButtonLink, Dialog, FormActions, Icon } from "../../ui";

export type ShareCardProps = {
    name: string;
    gang: string;
    /** The card's own page, which other websites may frame. */
    cardUrl: string;
};

// The width the card is drawn at for its picture and its measured height.
const STAGE_WIDTH = 480;
// Used when the card's page has not loaded by the time HTML is copied.
const FALLBACK_HEIGHT = 420;
const LABEL = "Share card";

/** The shared page's content, drawn out of sight on this page. */
export type Stage = {
    /** What the picture is taken of: the card alone. */
    card: HTMLElement;
    /** How tall the shared page is at the stage's width. */
    height: number;
    remove: () => void;
};

/** The browser calls, apart so tests can stand in for them. */
export const shareCardTools = {
    copyText(text: string) {
        return navigator.clipboard.writeText(text);
    },
    /**
     * The picture goes in as a promise: Safari allows a clipboard write
     * only while the click that asked for it is still running, and the
     * picture takes longer than that to make.
     */
    copyImage(png: Promise<Blob>) {
        return navigator.clipboard.write([
            new ClipboardItem({ "image/png": png }),
        ]);
    },
    /**
     * The shared page's content, copied onto this page out of sight. This
     * page already has the stylesheet and fonts, and the picture library
     * cannot draw an element that lives in another document, such as a
     * frame's. The shared page carries no script, so nothing runs.
     */
    async stage(url: string): Promise<Stage> {
        const response = await fetch(url, { credentials: "omit" });
        if (!response.ok)
            throw new Error(`The card's page answered ${response.status}`);
        const page = new DOMParser().parseFromString(
            await response.text(),
            "text/html",
        );
        const main = page.querySelector("main");
        if (!main) throw new Error("The card's page has no content");
        const holder = document.createElement("div");
        holder.setAttribute("aria-hidden", "true");
        holder.className = page.body.className;
        Object.assign(holder.style, {
            position: "fixed",
            left: "-10000px",
            top: "0",
            width: `${STAGE_WIDTH}px`,
            pointerEvents: "none",
        });
        holder.append(document.importNode(main, true));
        document.body.append(holder);
        const card = holder.querySelector<HTMLElement>("[data-shared-card]");
        if (!card) {
            holder.remove();
            throw new Error("The card's page has no card");
        }
        return {
            card,
            height: Math.ceil(holder.getBoundingClientRect().height),
            remove: () => holder.remove(),
        };
    },
    async picture(stage: Stage) {
        await document.fonts?.ready;
        const blob = await domToBlob(stage.card, {
            scale: 2,
            type: "image/png",
            backgroundColor: getComputedStyle(stage.card).backgroundColor,
        });
        if (!blob) throw new Error("No picture was made");
        return blob;
    },
    /** Whether the device's share sheet takes this, such as a file. */
    /** Whether the main pointer is a finger: a phone or a tablet. */
    touchScreen() {
        return window.matchMedia?.("(pointer: coarse)").matches ?? false;
    },
    canShare(data: ShareData) {
        if (!navigator.share) return false;
        return !navigator.canShare || navigator.canShare(data);
    },
    /**
     * Opens the device's share sheet. Safari opens it only while the click
     * is still running, so whatever is shared must be ready beforehand.
     */
    share(data: ShareData) {
        return navigator.share(data);
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

/** A tiny PNG, only to ask the device whether it shares pictures at all. */
function sharesPictures() {
    return shareCardTools.canShare({
        files: [new File([""], "card.png", { type: "image/png" })],
    });
}

function escapeAttribute(text: string) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

export function embedCode(url: string, title: string, height: number) {
    return `<iframe src="${escapeAttribute(url)}" title="${escapeAttribute(title)}" width="100%" height="${height}" style="border:0" loading="lazy"></iframe>`;
}

function fileName(name: string) {
    const slug = name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
    return `${slug || "card"}.png`;
}

type Status = { text: string; tone: "working" | "copied" | "failed" };

// A copy that worked is said in bold, so it stands out from the help text.
const TONE = {
    working: "text-muted",
    copied: "font-semibold text-ink-900 dark:text-white",
    failed: "text-red-600 dark:text-red-400",
};

function ShareDialog({
    name,
    gang,
    cardUrl,
    onDismiss,
}: ShareCardProps & { onDismiss: () => void }) {
    const url = new URL(cardUrl, window.location.href).href;
    // The card's page, drawn out of sight while the dialog is open: it is
    // measured for the embed's height and photographed for the picture.
    const [stage, setStage] = useState<Promise<Stage> | null>(null);
    const [height, setHeight] = useState<number | null>(null);
    useEffect(() => {
        let open = true;
        const staged = shareCardTools.stage(url);
        setStage(staged);
        staged.then(
            (drawn) => {
                if (open) setHeight(drawn.height);
            },
            () => {},
        );
        return () => {
            open = false;
            staged.then(
                (drawn) => drawn.remove(),
                () => {},
            );
        };
    }, [url]);
    // Where the device shares pictures, the picture is made as the dialog
    // opens, so it is ready to hand over within the click.
    const [pictures] = useState(sharesPictures);
    // A phone's share sheet has its own Copy, so Copy image is left out there.
    // Desktop share sheets have none, so computers keep the button.
    const [copies] = useState(() => !pictures || !shareCardTools.touchScreen());
    const [picture, setPicture] = useState<File | null>(null);
    useEffect(() => {
        if (!pictures || !stage) return;
        let open = true;
        stage
            .then((staged) => shareCardTools.picture(staged))
            .then(
                (blob) => {
                    if (open)
                        setPicture(
                            new File([blob], fileName(name), {
                                type: "image/png",
                            }),
                        );
                },
                () => {},
            );
        return () => {
            open = false;
        };
    }, [pictures, stage, name]);
    const title = `${name} – ${gang}`;
    const [status, setStatus] = useState<Status | null>(null);
    const [manual, setManual] = useState<{
        label: string;
        text: string;
    } | null>(null);
    const [download, setDownload] = useState("");

    useEffect(
        () => () => {
            if (download) URL.revokeObjectURL(download);
        },
        [download],
    );

    function copyHtml() {
        const code = embedCode(url, title, height ?? FALLBACK_HEIGHT);
        setManual(null);
        const failed = () => {
            setManual({ label: "Embed code", text: code });
            setStatus({
                text: "Your browser did not allow the copy. Select the code below and copy it.",
                tone: "failed",
            });
        };
        try {
            shareCardTools.copyText(code).then(
                () =>
                    setStatus({
                        text: "HTML copied. Paste it where your website takes embed code.",
                        tone: "copied",
                    }),
                failed,
            );
        } catch {
            failed();
        }
    }

    function copyImage() {
        // The stage starts as the dialog opens, so it exists by any click.
        const png = (
            stage ?? Promise.reject(new Error("The card is not ready"))
        ).then((staged) => shareCardTools.picture(staged));
        setStatus({ text: "Making the picture…", tone: "working" });
        const failed = () =>
            png.then(
                (blob) => {
                    setDownload(URL.createObjectURL(blob));
                    setStatus({
                        text: "Your browser did not allow the copy. Download the picture instead.",
                        tone: "failed",
                    });
                },
                () =>
                    setStatus({
                        text: "The picture could not be made. Try again.",
                        tone: "failed",
                    }),
            );
        try {
            shareCardTools.copyImage(png).then(
                () =>
                    setStatus({
                        text: "Image copied. Paste it into a message or document.",
                        tone: "copied",
                    }),
                failed,
            );
        } catch {
            failed();
        }
    }

    function sharePicture() {
        if (!picture) return;
        const failed = (error: unknown) => {
            // Closing the share sheet without picking an app is not a failure.
            if (isAbort(error)) return;
            setStatus({
                text: copies
                    ? "The picture could not be shared. Use Copy image instead."
                    : "The picture could not be shared. Try again.",
                tone: "failed",
            });
        };
        setStatus(null);
        try {
            shareCardTools.share({ files: [picture], title }).catch(failed);
        } catch (error) {
            failed(error);
        }
    }

    function copyLink() {
        setManual(null);
        const failed = () => {
            setManual({ label: "Link to the card", text: url });
            setStatus({
                text: "Your browser did not allow the copy. Select the link below and copy it.",
                tone: "failed",
            });
        };
        try {
            shareCardTools
                .copyText(url)
                .then(
                    () => setStatus({ text: "Link copied.", tone: "copied" }),
                    failed,
                );
        } catch {
            failed();
        }
    }

    function shareLink() {
        // No share sheet: copy the link, as the page's Share button does.
        if (!shareCardTools.canShare({ url })) {
            copyLink();
            return;
        }
        const failed = (error: unknown) => {
            if (!isAbort(error)) copyLink();
        };
        setStatus(null);
        try {
            shareCardTools.share({ url, title }).catch(failed);
        } catch (error) {
            failed(error);
        }
    }

    return (
        <Dialog
            title={LABEL}
            className="n26-share-dialog"
            lead={`Show ${name}’s card on another website, or send it as a picture or a link.`}
            onDismiss={onDismiss}
            onSubmit={(event) => event.preventDefault()}
        >
            <div className="grid gap-4">
                {/* The buttons span the dialog, so all four are one size. */}
                {pictures && (
                    <div className="grid gap-1">
                        <Button
                            onClick={sharePicture}
                            disabled={!picture}
                            className="n26-share-button w-full"
                        >
                            Share picture
                        </Button>
                        <p className="text-sm text-muted">
                            {picture
                                ? "Send the picture to another app, such as a message or email."
                                : "Making the picture…"}
                        </p>
                    </div>
                )}
                <div className="grid gap-1">
                    <Button
                        onClick={shareLink}
                        className="n26-share-button w-full"
                    >
                        Share link
                    </Button>
                    <p className="text-sm text-muted">
                        A link to the card’s own page, which anyone can open.
                    </p>
                </div>
                <div className="grid gap-1">
                    <Button
                        onClick={copyHtml}
                        className="n26-share-button w-full"
                    >
                        Embed HTML
                    </Button>
                    <p className="text-sm text-muted">
                        Embed code for Google Sites, Squarespace, WordPress or
                        any page that takes HTML. The card stays up to date.
                    </p>
                </div>
                {copies && (
                    <div className="grid gap-1">
                        <Button
                            onClick={copyImage}
                            className="n26-share-button w-full"
                        >
                            Copy image
                        </Button>
                        <p className="text-sm text-muted">
                            A picture of the card as it is now.
                        </p>
                    </div>
                )}
                <p
                    role="status"
                    className={
                        status ? `text-sm ${TONE[status.tone]}` : "sr-only"
                    }
                >
                    {status?.text ?? ""}
                </p>
                {manual && (
                    <textarea
                        readOnly
                        rows={3}
                        aria-label={manual.label}
                        value={manual.text}
                        onFocus={(event) => event.currentTarget.select()}
                        className="w-full rounded-control border border-box-border bg-surface px-3 py-2 font-mono text-xs"
                    />
                )}
                {download && (
                    <div>
                        <ButtonLink
                            href={download}
                            download={fileName(name)}
                            variant="ghost"
                        >
                            Download picture
                        </ButtonLink>
                    </div>
                )}
            </div>
            <FormActions>
                <Button variant="ghost" onClick={onDismiss}>
                    Close
                </Button>
            </FormActions>
        </Dialog>
    );
}

export function ShareCard(props: ShareCardProps) {
    const [open, setOpen] = useState(false);

    function onClick(event: MouseEvent<HTMLAnchorElement>) {
        // A modified click opens the card's page, as the link would.
        if (
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        )
            return;
        event.preventDefault();
        setOpen(true);
    }

    return (
        <>
            <ButtonLink
                href={props.cardUrl}
                size="xs"
                variant="ghost"
                aria-label={LABEL}
                title={LABEL}
                aria-haspopup="dialog"
                className="!px-1.5"
                onClick={onClick}
            >
                <span className="n26-icon-only">
                    <Icon name="share-2" className="size-3.5" />
                </span>
            </ButtonLink>
            {open && (
                <ShareDialog {...props} onDismiss={() => setOpen(false)} />
            )}
        </>
    );
}
