import cotton from "../generated/cotton.json";
import { useId, useRef, useState } from "react";
import { useAnchoredPlacement, useDismiss } from "./anchoredPanel";
import { ButtonLink, HelpPopover, Icon, Tooltip } from "./index";
import {
    ModelPreview,
    isModelPreview,
    CardControlsContext,
    type CardControls,
    type ModelPreviewProps,
} from "./ModelPreview";

type StoredFacts = {
    id: string;
    renameHref: string;
    status: string;
    statusLabel: string;
    statusColour: "ink" | "amber" | "red";
    statusHref: string;
    imageHref: string;
    modelCardsHref: string;
    rankTitles: string[];
    foundingBudget: boolean;
    tradePointsLeft: number | null;
    personalAction: string;
    ratingOverride: { baseRating?: number; defaultBaseRating?: number };
};
export function FoundingMark({ className = "size-4" }: { className?: string }) {
    return (
        <span className={cotton.modelCard.foundingMark}>
            <Icon name="flag" className={className} />
        </span>
    );
}
export type ModelCardData = ModelPreviewProps & { stored: StoredFacts };

function ModelPicture({ href }: { href: string }) {
    const id = useId();
    const root = useRef<HTMLSpanElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const [open, setOpen] = useState(false);
    useDismiss(root, trigger, open, () => setOpen(false));
    const style = useAnchoredPlacement({
        open,
        trigger,
        panel,
        width: "content",
        minWidth: "12rem",
        align: "end",
        gap: 4,
        margin: 8,
        clampHeight: true,
    });
    return (
        <span ref={root} className="inline-block">
            <button
                ref={trigger}
                type="button"
                aria-label="Show this model's picture"
                aria-haspopup="dialog"
                aria-expanded={open}
                aria-controls={open ? id : undefined}
                className={cotton.modelCard.pictureTrigger}
                onClick={() => setOpen(!open)}
            >
                <span className="n26-icon-only">
                    <Icon name="image" className="size-3.5" />
                </span>
            </button>
            {open && (
                <div
                    ref={panel}
                    id={id}
                    role="dialog"
                    aria-label="Model picture"
                    className={`${cotton.actionMenu.panel} fixed p-1`}
                    style={style}
                >
                    <img
                        src={href}
                        alt="Model picture"
                        className="w-56 max-w-[75vw] rounded-control"
                    />
                </div>
            )}
        </span>
    );
}

export function ModelCard({
    card,
    ...controls
}: CardControls & { card: ModelCardData }) {
    const stored = card.stored;
    const override = stored.ratingOverride;
    return (
        <CardControlsContext.Provider value={controls}>
            <ModelPreview
                {...card}
                presentation={{
                    id: `model-${stored.id}`,
                    label: `${card.name} model card`,
                    dead: stored.status === "dead",
                    nameAction: stored.renameHref && (
                        <>
                            {" "}
                            <ButtonLink
                                href={stored.renameHref}
                                size="xs"
                                variant="text"
                                className={cotton.modelCard.editLink}
                                aria-label={`Rename ${card.name}`}
                                title="Rename"
                            >
                                <span className="n26-icon-inline">
                                    <Icon name="pencil" className="" />
                                </span>
                            </ButtonLink>
                        </>
                    ),
                    profileExtra: !!stored.rankTitles.length && (
                        <div className="mt-1 space-y-0.5 text-xs text-muted">
                            {stored.rankTitles.map((title) => (
                                <p key={title}>
                                    <span className="font-medium text-ink-900 dark:text-ink-100">
                                        {title}
                                    </span>
                                </p>
                            ))}
                        </div>
                    ),
                    figures: (
                        <>
                            {stored.statusHref &&
                                (stored.statusLabel ? (
                                    <a
                                        href={stored.statusHref}
                                        className={
                                            cotton.modelCard.status[
                                                stored.statusColour
                                            ]
                                        }
                                    >
                                        {stored.statusLabel}
                                    </a>
                                ) : (
                                    <ButtonLink
                                        href={stored.statusHref}
                                        size="xs"
                                        variant="ghost"
                                        className={`${cotton.modelCard.compactLink} !text-muted !font-normal`}
                                    >
                                        Active
                                    </ButtonLink>
                                ))}
                            {stored.foundingBudget && (
                                <>
                                    <Tooltip
                                        size="sm"
                                        closeOnActivate={false}
                                        label={`This model can spend these trade points at the Trading Post while the ${stored.personalAction} action is open.`}
                                    >
                                        <button
                                            type="button"
                                            className="text-muted focus-ring"
                                        >
                                            <span>
                                                <span className="inline-block align-[-0.1875em]">
                                                    <FoundingMark className="size-3.5" />
                                                </span>{" "}
                                                <span>
                                                    {stored.tradePointsLeft} TP
                                                </span>
                                            </span>
                                        </button>
                                    </Tooltip>
                                    <span
                                        aria-hidden="true"
                                        className="text-muted"
                                    >
                                        ·
                                    </span>
                                </>
                            )}
                            {override.baseRating !== undefined ? (
                                <HelpPopover
                                    inline
                                    label={`${card.name}'s rating: ${card.rating}¢. Includes a base rating override`}
                                    triggerContent={`${card.rating}¢`}
                                >
                                    <>
                                        <p>
                                            Base rating overridden to{" "}
                                            {override.baseRating}¢.
                                        </p>
                                        <p>
                                            Base rating without an override:{" "}
                                            {override.defaultBaseRating}¢.
                                        </p>
                                        <p>
                                            Equipment and advancements add to
                                            this figure.
                                        </p>
                                    </>
                                </HelpPopover>
                            ) : (
                                <Tooltip
                                    label="Rating, including weapons and wargear"
                                    size="sm"
                                    closeOnActivate={false}
                                >
                                    <button
                                        type="button"
                                        className="focus-ring"
                                    >
                                        {card.rating}¢
                                    </button>
                                </Tooltip>
                            )}
                        </>
                    ),
                    actions: (
                        <div className="col-start-2 row-start-2 flex min-w-0 flex-wrap items-center justify-end">
                            {stored.imageHref && (
                                <ModelPicture href={stored.imageHref} />
                            )}
                            {stored.modelCardsHref && (
                                <ButtonLink
                                    href={stored.modelCardsHref}
                                    variant="ghost"
                                    size="xs"
                                    className={cotton.modelCard.compactLink}
                                    aria-label="Model cards"
                                >
                                    <span className="n26-icon-only">
                                        <Icon
                                            name="layers"
                                            className="size-3.5"
                                        />
                                    </span>
                                </ButtonLink>
                            )}
                        </div>
                    ),
                }}
            />
        </CardControlsContext.Provider>
    );
}

const object = (value: unknown): value is Record<string, unknown> =>
    !!value && typeof value === "object" && !Array.isArray(value);
const list = (value: unknown, valid: (value: unknown) => boolean): boolean =>
    Array.isArray(value) && value.every(valid);
const texts = (value: Record<string, unknown>, names: string[]) =>
    names.every((name) => typeof value[name] === "string");
const sameOrigin = (value: unknown) => {
    if (typeof value !== "string") return false;
    try {
        return (
            new URL(value, window.location.href).origin ===
            window.location.origin
        );
    } catch {
        return false;
    }
};
function choice(value: unknown): boolean {
    return (
        object(value) &&
        texts(value, [
            "key",
            "label",
            "href",
            "dismissHref",
            "restoreHref",
            "back",
        ]) &&
        ["resolved", "full", "several", "followsStatus"].every(
            (name) => typeof value[name] === "boolean",
        ) &&
        [value.href, value.dismissHref, value.restoreHref, value.back].every(
            sameOrigin,
        )
    );
}
function action(value: unknown): boolean {
    return (
        object(value) &&
        texts(value, ["label", "target", "tone"]) &&
        (value.separatorBefore === undefined ||
            typeof value.separatorBefore === "boolean") &&
        sameOrigin(value.target)
    );
}
function extras(value: unknown): boolean {
    return (
        object(value) &&
        (value.actions === undefined || list(value.actions, action)) &&
        (value.tiers === undefined || list(value.tiers, choice)) &&
        (value.choices === undefined ||
            list(
                value.choices,
                (item) =>
                    object(item) &&
                    (item.controls === undefined ||
                        list(item.controls, choice)),
            ))
    );
}
export function isModelCard(value: unknown): value is ModelCardData {
    if (!object(value)) return false;
    const stored = value.stored;
    if (!object(stored) || !isModelPreview(value)) return false;
    return (
        texts(stored, [
            "id",
            "renameHref",
            "status",
            "statusLabel",
            "statusColour",
            "statusHref",
            "imageHref",
            "modelCardsHref",
            "personalAction",
        ]) &&
        [stored.renameHref, stored.statusHref, stored.modelCardsHref].every(
            sameOrigin,
        ) &&
        ["ink", "amber", "red"].includes(String(stored.statusColour)) &&
        typeof stored.foundingBudget === "boolean" &&
        (stored.tradePointsLeft === null ||
            typeof stored.tradePointsLeft === "number") &&
        list(stored.rankTitles, (value) => typeof value === "string") &&
        object(stored.ratingOverride) &&
        (stored.ratingOverride.baseRating === undefined ||
            (typeof stored.ratingOverride.baseRating === "number" &&
                typeof stored.ratingOverride.defaultBaseRating === "number")) &&
        value.details.every(
            (row) =>
                typeof row.editHref === "string" &&
                sameOrigin(row.editHref) &&
                row.parts.every((part) => {
                    if (part.kind === "choice")
                        return (
                            part.control === undefined || choice(part.control)
                        );
                    if (part.kind === "counter")
                        return (
                            part.control === undefined ||
                            (texts(part.control, [
                                "name",
                                "href",
                                "back",
                                "assignment",
                            ]) &&
                                typeof part.control.tallied === "number" &&
                                sameOrigin(part.control.href) &&
                                sameOrigin(part.control.back))
                        );
                    return part.lines.every(extras);
                }),
        ) &&
        value.weapons.every(
            (weapon) =>
                extras(weapon) &&
                (!weapon.accessorise || action(weapon.accessorise)) &&
                weapon.profiles.every(extras) &&
                weapon.accessories.every(extras),
        )
    );
}
