import { domToBlob } from "modern-screenshot";
import { useEffect, useId, useState, type MouseEvent } from "react";
import {
    Button,
    ButtonLink,
    Dialog,
    Field,
    FormActions,
    Icon,
    Input,
    Textarea,
} from "../../ui";

export type ShareCardProps = { name: string; gang: string; cardUrl: string };
export type Aspect = "standard" | `${number}:${number}`;
type Theme = "light" | "dark";

const STAGE_WIDTH = 480;
const LABEL = "Share card";
export type Stage = { card: HTMLElement; remove: () => void };

/** Browser boundaries kept separate so tests can exercise cancellation and failures. */
export const shareCardTools = {
    copyText(text: string) {
        return navigator.clipboard.writeText(text);
    },
    copyImage(png: Promise<Blob>) {
        return navigator.clipboard.write([
            new ClipboardItem({ "image/png": png }),
        ]);
    },
    async stage(url: string, aspect: Aspect = "standard"): Promise<Stage> {
        // An isolated document keeps explicit light exports light even on a dark page.
        const frame = document.createElement("iframe");
        frame.setAttribute("aria-hidden", "true");
        frame.tabIndex = -1;
        Object.assign(frame.style, {
            position: "fixed",
            left: "-10000px",
            top: "0",
            width: `${STAGE_WIDTH}px`,
            height: "1000px",
            border: "0",
            pointerEvents: "none",
        });
        try {
            await new Promise<void>((resolve, reject) => {
                const timeout = window.setTimeout(
                    () => reject(new Error("The card took too long to load")),
                    20000,
                );
                frame.onload = () => {
                    clearTimeout(timeout);
                    resolve();
                };
                frame.onerror = () => {
                    clearTimeout(timeout);
                    reject(new Error("The card could not load"));
                };
                frame.src = url;
                document.body.append(frame);
            });
            const doc = frame.contentDocument;
            const card = doc?.querySelector<HTMLElement>("[data-shared-card]");
            if (!card) throw new Error("The shared page has no card");
            await doc?.fonts?.ready;
            await Promise.all(
                Array.from(card.querySelectorAll("img"), (img) =>
                    img.decode().catch(() => {}),
                ),
            );
            if (aspect !== "standard") {
                const [across, down] = aspect.split(":").map(Number);
                const target = down / across;
                let low = STAGE_WIDTH,
                    high = Math.max(
                        STAGE_WIDTH,
                        Math.ceil(card.getBoundingClientRect().height / target),
                    ),
                    best = STAGE_WIDTH;
                const needsWiderLayout =
                    card.getBoundingClientRect().height / STAGE_WIDTH > target;
                if (needsWiderLayout) best = high;
                // Keep the standard text scale; only widen the layout when needed to fit all content.
                for (
                    let attempt = 0;
                    needsWiderLayout && attempt < 10;
                    attempt++
                ) {
                    const width = Math.round((low + high) / 2);
                    frame.style.width = `${width}px`;
                    const proportion =
                        card.getBoundingClientRect().height / width;
                    if (proportion > target) low = width;
                    else {
                        best = width;
                        high = width;
                    }
                }
                frame.style.width = `${best}px`;
                Object.assign(card.style, {
                    minHeight: `${best * target}px`,
                    display: "flex",
                    flexDirection: "column",
                });
            }
            return { card, remove: () => frame.remove() };
        } catch (error) {
            frame.remove();
            throw error;
        }
    },
    async image(stage: Stage, aspect: Aspect): Promise<Blob> {
        const background =
            stage.card.ownerDocument.defaultView!.getComputedStyle(
                stage.card,
            ).backgroundColor;
        const width = stage.card.getBoundingClientRect().width;
        const height =
            aspect === "standard"
                ? stage.card.getBoundingClientRect().height
                : (width * Number(aspect.split(":")[1])) /
                  Number(aspect.split(":")[0]);
        const blob = await domToBlob(stage.card, {
            width,
            height,
            scale: 1440 / width,
            type: "image/png",
            backgroundColor: background,
        });
        if (!blob) throw new Error("The image could not be made");
        return blob;
    },
    canShare(data: ShareData) {
        return (
            !!navigator.share &&
            (!navigator.canShare || navigator.canShare(data))
        );
    },
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
function escapeAttribute(text: string) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}
export function embedCode(
    url: string,
    title: string,
    height: number | string = "",
    width: number | string = "100%",
) {
    const hasHeight = String(height).trim() !== "";
    const heightAttribute = hasHeight
        ? ` height="${escapeAttribute(String(height))}"`
        : "";
    const heightStyle = hasHeight
        ? `;height:${escapeAttribute(embedDimensionStyle(height))}`
        : "";
    return `<iframe src="${escapeAttribute(url)}" title="${escapeAttribute(title)}" width="${escapeAttribute(String(width))}"${heightAttribute} style="border:0;width:${escapeAttribute(embedDimensionStyle(width))}${heightStyle}" loading="lazy"></iframe>`;
}
export function embedDimensionStyle(dimension: string | number) {
    const value = String(dimension);
    return /^\d+(?:\.\d+)?$/.test(value) ? `${value}px` : value;
}
function fileName(name: string) {
    return `${
        name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-|-$/g, "") || "card"
    }.png`;
}
function currentTheme(): Theme {
    return document.documentElement.classList.contains("dark")
        ? "dark"
        : "light";
}
export function customRatio(width: string, height: string): Aspect | null {
    const across = Number(width),
        down = Number(height);
    if (
        !Number.isFinite(across) ||
        !Number.isFinite(down) ||
        across <= 0 ||
        down <= 0 ||
        across / down < 0.2 ||
        across / down > 5
    )
        return null;
    return `${across}:${down}`;
}
type Status = { text: string; failed?: boolean };

function ShareDialog({
    name,
    gang,
    cardUrl,
    onDismiss,
}: ShareCardProps & { onDismiss: () => void }) {
    const id = useId();
    const [theme, setTheme] = useState<Theme>(currentTheme);
    const address = new URL(cardUrl, window.location.href);
    address.searchParams.set("theme", theme);
    const url = address.href;
    const title = `${name} – ${gang}`;
    const [aspect, setAspect] = useState<Aspect>("standard");
    const [custom, setCustom] = useState(false);
    const [ratioWidth, setRatioWidth] = useState("1");
    const [ratioHeight, setRatioHeight] = useState("1");
    const [ratioError, setRatioError] = useState("");
    function applyRatio() {
        const next = customRatio(ratioWidth, ratioHeight);
        if (!next) {
            setRatioError(
                "Use positive numbers and a ratio between 1:5 and 5:1.",
            );
            return;
        }
        setRatioError("");
        setAspect(next);
    }
    const [retry, setRetry] = useState(0);
    const [staged, setStaged] = useState<{ key: string; stage: Stage } | null>(
        null,
    );
    const [asset, setAsset] = useState<{
        key: string;
        file: File;
        src: string;
    } | null>(null);
    const [failedKey, setFailedKey] = useState("");
    const key = `${url}|${aspect}|${retry}`;
    const ready = asset?.key === key ? asset : null;
    const failed = failedKey === key;
    const [width, setWidth] = useState("100%");
    const [height, setHeight] = useState("");
    const code = embedCode(url, title, height, width);
    const [status, setStatus] = useState<Status | null>(null);

    const [filesSupported] = useState(() =>
        shareCardTools.canShare({
            files: [new File([""], "card.png", { type: "image/png" })],
        }),
    );
    const [linksSupported] = useState(() => shareCardTools.canShare({ url }));

    useEffect(() => {
        let active = true;
        const pending = shareCardTools.stage(url, aspect);
        pending.then(
            (stage) => {
                if (active) setStaged({ key: key, stage });
            },
            () => {
                if (active) setFailedKey(key);
            },
        );
        return () => {
            active = false;
            pending.then(
                (stage) => stage.remove(),
                () => {},
            );
        };
    }, [url, aspect, retry]);

    useEffect(() => {
        if (!staged || staged.key !== key) return;
        let active = true;
        let src = "";
        shareCardTools.image(staged.stage, aspect).then(
            (blob) => {
                if (!active) return;
                src = URL.createObjectURL(blob);
                setAsset({
                    key,
                    file: new File([blob], fileName(name), {
                        type: "image/png",
                    }),
                    src,
                });
            },
            () => {
                if (active) setFailedKey(key);
            },
        );
        return () => {
            active = false;
            if (src) URL.revokeObjectURL(src);
        };
    }, [staged, url, aspect, retry, name]);

    useEffect(() => {
        setStatus(null);
    }, [key, code]);

    function copyText(text: string, success: string) {
        const fail = () =>
            setStatus({
                text: "Your browser did not allow the copy. Select the text and copy it.",
                failed: true,
            });
        try {
            shareCardTools
                .copyText(text)
                .then(() => setStatus({ text: success }), fail);
        } catch {
            fail();
        }
    }
    function copyImage() {
        if (!ready) return;
        const fail = () => {
            setStatus({
                text: "Your browser did not allow the copy. Download the image instead.",
                failed: true,
            });
        };
        try {
            shareCardTools.copyImage(Promise.resolve(ready.file)).then(
                () =>
                    setStatus({
                        text: "Image copied. Paste it into a message or document.",
                    }),
                fail,
            );
        } catch {
            fail();
        }
    }
    function shareImage() {
        if (!ready) return;
        const fail = (error: unknown) => {
            if (!isAbort(error))
                setStatus({
                    text: "The image could not be shared. Copy or download it instead.",
                    failed: true,
                });
        };
        setStatus(null);
        try {
            shareCardTools.share({ files: [ready.file], title }).catch(fail);
        } catch (error) {
            fail(error);
        }
    }
    function shareLink() {
        const fail = (error: unknown) => {
            if (!isAbort(error)) copyText(url, "Link copied.");
        };
        setStatus(null);
        try {
            shareCardTools.share({ url, title }).catch(fail);
        } catch (error) {
            fail(error);
        }
    }

    return (
        <Dialog
            title={LABEL}
            lead={`Share ${name}’s card as an image, link or embed.`}
            className="n26-share-dialog"
            onDismiss={onDismiss}
            onSubmit={(event) => event.preventDefault()}
        >
            <div
                role="group"
                aria-label="Card theme"
                className="n26-share-theme"
            >
                {(
                    [
                        ["light", "Light", "sun"],
                        ["dark", "Dark", "moon"],
                    ] as const
                ).map(([value, label, icon]) => (
                    <Button
                        key={value}
                        size="xs"
                        variant="ghost"
                        className="n26-share-icon"
                        aria-label={label}
                        title={`${label} card theme`}
                        aria-pressed={theme === value}
                        onClick={() => setTheme(value)}
                    >
                        <Icon name={icon} />
                    </Button>
                ))}
            </div>
            <div className="n26-share-workspace">
                <section
                    className="min-w-0 grid content-start gap-3"
                    aria-label="Card image"
                >
                    <div
                        className="n26-share-image-preview"
                        style={
                            aspect === "standard"
                                ? undefined
                                : { aspectRatio: aspect.replace(":", " / ") }
                        }
                        aria-busy={!ready && !failed}
                    >
                        {ready ? (
                            <a
                                href={ready.src}
                                target="_blank"
                                rel="noopener"
                                aria-label="Open full-resolution card image"
                            >
                                <img
                                    src={ready.src}
                                    alt={`${name}’s card, ${theme} theme, ${aspect === "standard" ? "standard proportions" : aspect}`}
                                    draggable
                                />
                            </a>
                        ) : (
                            <div className="n26-share-loading">
                                {failed ? (
                                    <>
                                        <p>The image could not be made.</p>
                                        <Button
                                            variant="ghost"
                                            onClick={() =>
                                                setRetry((value) => value + 1)
                                            }
                                        >
                                            Try again
                                        </Button>
                                    </>
                                ) : (
                                    <p>Invoking machine spirit…</p>
                                )}
                            </div>
                        )}
                    </div>
                    <div className="n26-share-toolbar">
                        <div
                            role="group"
                            aria-label="Image aspect ratio"
                            className="flex gap-0.5"
                        >
                            {(["standard", "1:1", "4:5"] as const).map(
                                (value) => (
                                    <Button
                                        key={value}
                                        size="xs"
                                        variant="ghost"
                                        aria-pressed={
                                            !custom && aspect === value
                                        }
                                        onClick={() => {
                                            setCustom(false);
                                            setRatioError("");
                                            setAspect(value);
                                        }}
                                    >
                                        {value === "standard"
                                            ? "Standard"
                                            : value}
                                    </Button>
                                ),
                            )}
                            <Button
                                size="xs"
                                variant="ghost"
                                aria-pressed={custom}
                                onClick={() => setCustom((value) => !value)}
                            >
                                Custom
                            </Button>
                        </div>
                        <div
                            className="flex gap-0.5"
                            role="group"
                            aria-label="Image actions"
                        >
                            <Button
                                size="xs"
                                variant="ghost"
                                className="n26-share-icon"
                                aria-label="Copy image"
                                title="Copy image"
                                disabled={!ready}
                                onClick={copyImage}
                            >
                                <Icon name="copy" />
                            </Button>
                            {filesSupported && (
                                <Button
                                    size="xs"
                                    variant="ghost"
                                    className="n26-share-icon"
                                    aria-label="Share image"
                                    title="Share image"
                                    disabled={!ready}
                                    onClick={shareImage}
                                >
                                    <Icon name="share-2" />
                                </Button>
                            )}
                            {ready && (
                                <ButtonLink
                                    size="xs"
                                    variant="ghost"
                                    className="n26-share-icon"
                                    aria-label="Download image"
                                    title="Download image"
                                    href={ready.src}
                                    download={fileName(name)}
                                >
                                    <Icon name="download" />
                                </ButtonLink>
                            )}
                        </div>
                    </div>
                    {custom && (
                        <div
                            className="n26-share-custom"
                            onKeyDown={(event) => {
                                if (event.key === "Enter") {
                                    event.preventDefault();
                                    applyRatio();
                                }
                            }}
                        >
                            <Input
                                aria-label="Ratio width"
                                type="number"
                                min="0"
                                step="any"
                                value={ratioWidth}
                                onChange={(event) =>
                                    setRatioWidth(event.target.value)
                                }
                            />
                            <span aria-hidden="true">:</span>
                            <Input
                                aria-label="Ratio height"
                                type="number"
                                min="0"
                                step="any"
                                value={ratioHeight}
                                onChange={(event) =>
                                    setRatioHeight(event.target.value)
                                }
                            />
                            <Button
                                size="sm"
                                variant="ghost"
                                onClick={applyRatio}
                            >
                                Apply ratio
                            </Button>
                            {ratioError && (
                                <p
                                    role="alert"
                                    className="col-span-full text-sm text-red-600 dark:text-red-400"
                                >
                                    {ratioError}
                                </p>
                            )}
                        </div>
                    )}
                </section>
                <div className="min-w-0 grid content-start gap-6">
                    <details className="n26-share-link">
                        <summary className="cursor-pointer font-semibold">
                            Link
                        </summary>
                        <div className="grid gap-2 pt-3">
                            <p className="text-sm text-muted">
                                Anyone with the link can view the card.
                            </p>
                            <div className="flex items-start gap-2">
                                <div className="min-w-0 flex-1">
                                    <Input
                                        aria-label="Link to the card"
                                        readOnly
                                        value={url}
                                        onFocus={(event) =>
                                            event.currentTarget.select()
                                        }
                                    />
                                </div>
                                <Button
                                    variant="ghost"
                                    className="n26-share-icon"
                                    title="Copy link"
                                    aria-label="Copy link"
                                    onClick={() =>
                                        copyText(url, "Link copied.")
                                    }
                                >
                                    <Icon name="copy" />
                                </Button>
                                {linksSupported && (
                                    <Button
                                        variant="ghost"
                                        className="n26-share-icon"
                                        title="Share link"
                                        aria-label="Share link"
                                        onClick={shareLink}
                                    >
                                        <Icon name="share-2" />
                                    </Button>
                                )}
                            </div>
                        </div>
                    </details>
                    <details className="n26-share-embed">
                        <summary className="cursor-pointer font-semibold">
                            Embed
                        </summary>
                        <div className="grid gap-3 pt-3">
                            <p className="text-sm text-muted">
                                Add the card to your website. It stays up to
                                date.
                            </p>
                            <div className="grid grid-cols-2 gap-3">
                                <Field label="Width" htmlFor={`${id}-width`}>
                                    <Input
                                        id={`${id}-width`}
                                        type="text"
                                        value={width}
                                        placeholder="100%"
                                        onChange={(event) =>
                                            setWidth(event.target.value)
                                        }
                                    />
                                </Field>
                                <Field label="Height" htmlFor={`${id}-height`}>
                                    <Input
                                        id={`${id}-height`}
                                        type="text"
                                        value={height}
                                        placeholder="Optional"
                                        onChange={(event) =>
                                            setHeight(event.target.value)
                                        }
                                    />
                                </Field>
                            </div>
                            <div className="n26-share-embed-preview">
                                <iframe
                                    title="Embed preview"
                                    src={url}
                                    width={width}
                                    style={{
                                        width: embedDimensionStyle(width),
                                        height: height.trim()
                                            ? embedDimensionStyle(height)
                                            : undefined,
                                    }}
                                    height={height.trim() ? height : undefined}
                                    loading="lazy"
                                />
                            </div>
                            <Textarea
                                aria-label="Embed code"
                                rows={5}
                                readOnly
                                value={code}
                                onFocus={(event) =>
                                    event.currentTarget.select()
                                }
                                className="font-mono text-xs"
                            />
                            <div>
                                <Button
                                    variant="ghost"
                                    className="n26-share-icon"
                                    aria-label="Copy embed code"
                                    title="Copy embed code"
                                    onClick={() =>
                                        copyText(code, "Embed code copied.")
                                    }
                                >
                                    <Icon name="copy" />
                                </Button>
                            </div>
                        </div>
                    </details>
                </div>
            </div>
            <p
                role="status"
                className={
                    status
                        ? `mt-3 text-sm ${status.failed ? "text-red-600 dark:text-red-400" : "font-semibold"}`
                        : "sr-only"
                }
            >
                {status?.text ?? ""}
            </p>
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
