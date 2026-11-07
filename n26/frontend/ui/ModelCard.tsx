import cotton from "../generated/cotton.json";
import { ButtonLink, HelpPopover, Icon } from "./index";
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
export function FoundingMark() {
    return (
        <span className={cotton.modelCard.foundingMark}>
            <Icon name="flag" className="size-4" />
        </span>
    );
}
export type ModelCardData = ModelPreviewProps & { stored: StoredFacts };
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
                    nameAction: (
                        <span className="ms-1 inline-flex align-baseline">
                            <ButtonLink
                                href={stored.renameHref}
                                size="xs"
                                variant="text"
                                aria-label={`Rename ${card.name}`}
                            >
                                <Icon name="pencil" className="size-3" />
                            </ButtonLink>
                        </span>
                    ),
                    profileExtra: stored.rankTitles.map((title) => (
                        <p key={title} className="text-xs font-medium">
                            {title}
                        </p>
                    )),
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
                                    >
                                        Active
                                    </ButtonLink>
                                ))}
                            {stored.foundingBudget && (
                                <>
                                    <HelpPopover
                                        label="Personal trade points"
                                        triggerContent={
                                            <span className="inline-flex items-baseline gap-1">
                                                <FoundingMark />
                                                {stored.tradePointsLeft} TP
                                            </span>
                                        }
                                    >
                                        <p>
                                            This model can spend these trade
                                            points at the Trading Post while the{" "}
                                            {stored.personalAction} action is
                                            open.
                                        </p>
                                    </HelpPopover>
                                    <span aria-hidden="true">·</span>
                                </>
                            )}
                            <HelpPopover
                                label={`${card.name}'s rating: ${card.rating}¢`}
                                triggerContent={`${card.rating}¢`}
                            >
                                {override.baseRating !== undefined ? (
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
                                ) : (
                                    <p>Rating, including weapons and wargear</p>
                                )}
                            </HelpPopover>
                        </>
                    ),
                    actions: (
                        <div className="col-start-2 row-start-2 flex min-w-0 flex-wrap items-center justify-end">
                            {stored.imageHref && (
                                <HelpPopover
                                    label="Show this model's picture"
                                    triggerContent={
                                        <Icon
                                            name="image"
                                            className="size-3.5"
                                        />
                                    }
                                >
                                    <img
                                        src={stored.imageHref}
                                        alt="Model picture"
                                        className="w-56 max-w-[75vw] rounded-control"
                                    />
                                </HelpPopover>
                            )}
                            {stored.modelCardsHref && (
                                <ButtonLink
                                    href={stored.modelCardsHref}
                                    variant="ghost"
                                    size="xs"
                                    aria-label="Model cards"
                                >
                                    <Icon name="layers" className="size-3.5" />
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
