import { Fragment, createContext, useContext, type ReactNode } from "react";
import { Button, ButtonLink, Icon } from "./index";
import { ActionMenu } from "./ActionMenu";
import cotton from "../generated/cotton.json";
import { Tooltip } from "./Tooltip";

type Stat = {
    shortName: string;
    fullName: string;
    value: string;
    highlighted: boolean;
    firstOfGroup: boolean;
    explanation: string;
};
export type CardChoiceControl = {
    key: string;
    label: string;
    href: string;
    dismissHref: string;
    restoreHref: string;
    back: string;
    resolved: boolean;
    full: boolean;
    several: boolean;
    followsStatus: boolean;
};
type CardAction = {
    label: string;
    target: string;
    tone: string;
    separatorBefore?: boolean;
};
type ItemChoice = {
    label: string;
    values: string[];
    controls?: CardChoiceControl[];
};
export type CardControls = {
    csrfToken: string;
    frozen: boolean;
    countersFrozen?: boolean;
    onTally: (assignment: string, change: number, name: string) => void;
};
export const CardControlsContext = createContext<CardControls | null>(null);
type Line = {
    key?: string;
    text: string;
    explanation: string;
    choices: ItemChoice[];
    actions?: CardAction[];
    tiers?: CardChoiceControl[];
};
type Part = { key?: string } & (
    | { kind: "names" | "gear"; lines: Line[] }
    | {
          kind: "counter";
          value: number;
          control?: {
              name: string;
              href: string;
              back: string;
              tallied: number;
              assignment: string;
          };
      }
    | {
          kind: "choice";
          chosen: string | null;
          prompt: string;
          control?: CardChoiceControl;
      }
);
type Weapon = {
    key?: string;
    name: string;
    stats: Stat[];
    traits: Line[];
    profiles: {
        key?: string;
        name: string;
        stats: Stat[];
        traits: Line[];
        actions?: CardAction[];
    }[];
    accessories: Line[];
    choices: ItemChoice[];
    actions?: CardAction[];
    tiers?: CardChoiceControl[];
    accessorise?: CardAction | null;
};

export type ModelPreviewProps = {
    name: string;
    rating: number;
    profileName: string;
    ownerLine: string;
    typeLine: string;
    xp: number;
    xpTarget: number | string;
    statGroups: Stat[][];
    typeSpan: number;
    details: {
        key?: string;
        label: string;
        parts: Part[];
        editHref?: string;
    }[];
    weaponColumns: Stat[];
    weapons: Weapon[];
};

function object(value: unknown): value is Record<string, unknown> {
    return !!value && typeof value === "object" && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
    return (
        Array.isArray(value) && value.every((item) => typeof item === "string")
    );
}
function list(value: unknown, valid: (item: unknown) => boolean) {
    return Array.isArray(value) && value.every(valid);
}
function number(value: unknown): value is number {
    return typeof value === "number" && Number.isFinite(value);
}
function stat(value: unknown): boolean {
    return (
        object(value) &&
        typeof value.shortName === "string" &&
        typeof value.fullName === "string" &&
        typeof value.value === "string" &&
        typeof value.explanation === "string" &&
        typeof value.highlighted === "boolean" &&
        typeof value.firstOfGroup === "boolean"
    );
}
function itemChoice(value: unknown): boolean {
    return (
        object(value) &&
        typeof value.label === "string" &&
        strings(value.values)
    );
}
function line(value: unknown): boolean {
    return (
        object(value) &&
        typeof value.text === "string" &&
        typeof value.explanation === "string" &&
        list(value.choices, itemChoice)
    );
}
function part(value: unknown): boolean {
    if (!object(value)) return false;
    if (value.kind === "names" || value.kind === "gear")
        return list(value.lines, line);
    if (value.kind === "counter") return number(value.value);
    return (
        value.kind === "choice" &&
        typeof value.prompt === "string" &&
        (value.chosen === null || typeof value.chosen === "string")
    );
}
function weapon(value: unknown): boolean {
    return (
        object(value) &&
        typeof value.name === "string" &&
        list(value.stats, stat) &&
        list(value.traits, line) &&
        list(
            value.profiles,
            (profile) =>
                object(profile) &&
                typeof profile.name === "string" &&
                list(profile.stats, stat) &&
                list(profile.traits, line),
        ) &&
        list(value.accessories, line) &&
        list(value.choices, itemChoice)
    );
}

/** Reject malformed read responses before they enter the preview renderer. */
export function isModelPreview(value: unknown): value is ModelPreviewProps {
    return (
        object(value) &&
        typeof value.name === "string" &&
        number(value.rating) &&
        typeof value.profileName === "string" &&
        typeof value.ownerLine === "string" &&
        typeof value.typeLine === "string" &&
        number(value.xp) &&
        (typeof value.xpTarget === "string" || number(value.xpTarget)) &&
        list(value.statGroups, (group) => list(group, stat)) &&
        number(value.typeSpan) &&
        list(
            value.details,
            (detail) =>
                object(detail) &&
                typeof detail.label === "string" &&
                list(detail.parts, part),
        ) &&
        list(value.weaponColumns, stat) &&
        list(value.weapons, weapon)
    );
}

const recipe = cotton.modelPreview;

function Information({
    text,
    explanation,
    suffix = "",
    plain = false,
}: {
    text: string;
    explanation: string;
    suffix?: string;
    plain?: boolean;
}) {
    return explanation ? (
        <Tooltip label={explanation} size="sm" closeOnActivate={false}>
            <button
                type="button"
                className={`${plain ? "" : recipe.information} focus-ring`}
            >
                {text}
                {suffix}
            </button>
        </Tooltip>
    ) : (
        <span>
            {text}
            {suffix}
        </span>
    );
}

export function ChoiceDismiss({ choice }: { choice: CardChoiceControl }) {
    const controls = useContext(CardControlsContext);
    const href = choice.restoreHref || choice.dismissHref;
    if (!controls || !href) return null;
    return (
        <form
            action={href}
            method="post"
            className="inline-flex shrink-0 items-center"
            data-busy="off"
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={controls.csrfToken}
            />
            <input type="hidden" name="back" value={choice.back} />
            <Button
                size="xs"
                variant="ghost"
                type="submit"
                disabled={controls.frozen}
                aria-label={`${choice.restoreHref ? "Restore" : "Dismiss"} ${choice.label}`}
            >
                {choice.restoreHref ? (
                    "Restore"
                ) : (
                    <span className="n26-icon-only">
                        <Icon name="x" className="size-3" />
                    </span>
                )}
            </Button>
        </form>
    );
}
function TierControls({ choices }: { choices?: CardChoiceControl[] }) {
    return choices?.map((choice, i) => (
        <span className="inline-flex items-center" key={i}>
            {choice.href && (
                <ButtonLink href={choice.href} variant="ghost" size="xs">
                    {choice.resolved ? "Change tier" : "Choose tier"}
                </ButtonLink>
            )}
            <ChoiceDismiss choice={choice} />
        </span>
    ));
}
function CardActions({
    name,
    actions,
    accessory,
}: {
    name: string;
    actions?: CardAction[];
    accessory?: CardAction | null;
}) {
    if (!actions?.length && !accessory) return null;
    const entries = [...(accessory ? [accessory] : []), ...(actions || [])];
    return (
        <span className="flex shrink-0 items-center">
            <ActionMenu
                label={`More for ${name}`}
                trigger="inline-chevron"
                align="end"
                minWidth="10rem"
                items={entries.map((action, index) => ({
                    label: action.label,
                    href: action.target,
                    tone: action.tone === "danger" ? "danger" : "default",
                    separatorBefore:
                        !!action.separatorBefore ||
                        (!!accessory && index === 1),
                }))}
            />
        </span>
    );
}
function Names({ lines }: { lines: Line[] }) {
    if (!lines.length) return <>—</>;
    const interactive = lines.some(
        (line) => line.actions?.length || line.tiers?.length,
    );
    return (
        <>
            {lines.map((line, index) => (
                <Fragment key={line.key || index}>
                    <span
                        className={
                            interactive
                                ? "inline-flex max-w-full flex-wrap items-center gap-1"
                                : undefined
                        }
                    >
                        <Information
                            text={line.text}
                            explanation={line.explanation}
                            suffix={
                                index < lines.length - 1
                                    ? line.explanation
                                        ? ",\u00a0"
                                        : ", "
                                    : ""
                            }
                        />
                        <TierControls choices={line.tiers} />
                        <CardActions name={line.text} actions={line.actions} />
                    </span>
                </Fragment>
            ))}
        </>
    );
}
function ItemChoices({
    choices,
    weapon = false,
}: {
    choices: ItemChoice[];
    weapon?: boolean;
}) {
    const Tag = weapon ? "li" : "span";
    return choices.map((choice, index) => (
        <Tag
            key={index}
            className={
                weapon ? "flex flex-wrap items-center gap-2" : recipe.itemChoice
            }
        >
            <span className="min-w-0">{choice.label}:</span>{" "}
            {choice.values.map((value, i) => (
                <Fragment key={i}>
                    {i > 0 && ", "}
                    <span className="inline-flex items-center gap-0">
                        {value}
                        {choice.controls?.[i]?.href && (
                            <ButtonLink
                                href={choice.controls[i].href}
                                variant="ghost"
                                size="xs"
                            >
                                {choice.controls[i].resolved
                                    ? "Change"
                                    : "Choose"}
                            </ButtonLink>
                        )}
                        {choice.controls?.[i] && (
                            <ChoiceDismiss choice={choice.controls[i]} />
                        )}
                    </span>
                </Fragment>
            ))}
        </Tag>
    ));
}
function DetailPart({ part }: { part: Part }) {
    const controls = useContext(CardControlsContext);
    if (part.kind === "counter")
        return (
            <>
                <span className={recipe.counter}>{part.value}</span>
                {controls && part.control?.href && (
                    <span className="ms-1 inline-flex items-center gap-1 align-middle">
                        <Button
                            size="xs"
                            variant="default"
                            className={cotton.modelCard.counterStep}
                            disabled={
                                (controls.countersFrozen ?? controls.frozen) ||
                                !part.control.tallied
                            }
                            aria-label={`Take one off ${part.control.name}`}
                            onClick={() =>
                                controls.onTally(
                                    part.control!.assignment,
                                    -1,
                                    part.control!.name,
                                )
                            }
                        >
                            −
                        </Button>
                        <Button
                            size="xs"
                            variant="default"
                            className={cotton.modelCard.counterStep}
                            disabled={
                                controls.countersFrozen ?? controls.frozen
                            }
                            aria-label={`Add one to ${part.control.name}`}
                            onClick={() =>
                                controls.onTally(
                                    part.control!.assignment,
                                    1,
                                    part.control!.name,
                                )
                            }
                        >
                            +
                        </Button>
                    </span>
                )}
            </>
        );
    if (part.kind === "choice")
        return (
            <span
                className={
                    part.chosen === null && part.prompt.startsWith("Choose ")
                        ? "inline-flex items-center gap-0"
                        : undefined
                }
            >
                {part.chosen !== null &&
                    (part.control?.href ? (
                        <ButtonLink
                            href={part.control.href}
                            variant="ghost"
                            size="xs"
                            className="max-w-full whitespace-normal! text-left px-0!"
                        >
                            {part.chosen}
                        </ButtonLink>
                    ) : (
                        <span>{part.chosen}</span>
                    ))}
                {part.chosen !== null && part.prompt && " "}
                {part.prompt &&
                    (part.control?.href ? (
                        <ButtonLink
                            href={part.control.href}
                            variant="ghost"
                            size="xs"
                        >
                            {part.control.followsStatus &&
                            part.prompt === "Resolve" ? (
                                <span className="inline-flex items-center gap-1">
                                    Resolve{" "}
                                    <Icon
                                        name="arrow-right"
                                        className="size-3.5 shrink-0"
                                    />
                                </span>
                            ) : (
                                part.prompt
                            )}
                        </ButtonLink>
                    ) : (
                        <span className={recipe.prompt}>{part.prompt}</span>
                    ))}
                {part.control && <ChoiceDismiss choice={part.control} />}
            </span>
        );
    if (part.kind === "names")
        return (
            <span className={recipe.names}>
                <Names lines={part.lines} />
            </span>
        );
    if (
        controls &&
        part.kind === "gear" &&
        part.lines.some((line) => line.actions?.length || line.tiers?.length)
    )
        return (
            <ul className="flex flex-col gap-1">
                {part.lines.map((line, index) => (
                    <li key={line.key || index}>
                        <div className="flex flex-wrap items-center gap-1">
                            <Information
                                text={line.text}
                                explanation={line.explanation}
                            />
                            <TierControls choices={line.tiers} />
                            <CardActions
                                name={line.text}
                                actions={line.actions}
                            />
                        </div>
                        <ItemChoices choices={line.choices} />
                    </li>
                ))}
            </ul>
        );
    return (
        <>
            <Names lines={part.lines} />
            {part.kind === "gear" &&
                part.lines.map((line, index) =>
                    controls ? (
                        <span key={index}>
                            <ItemChoices choices={line.choices} />
                        </span>
                    ) : (
                        line.choices.map((choice, i) => (
                            <span
                                key={`${index}:${i}`}
                                className={recipe.itemChoice}
                            >
                                {line.text} — {choice.label}:{" "}
                                {choice.values.join(", ")}
                            </span>
                        ))
                    ),
                )}
        </>
    );
}

function statClass(stat: Stat, index: number, tag: "th" | "td") {
    const variant = `${Number(index > 0 && stat.firstOfGroup)}${Number(stat.highlighted)}`;
    return recipe.stats[variant as keyof typeof recipe.stats][tag];
}

function StatHeadings({ stats }: { stats: Stat[] }) {
    return stats.map((stat, index) => (
        <th
            key={index}
            scope="col"
            title={stat.fullName}
            className={statClass(stat, index, "th")}
        >
            {stat.shortName}
        </th>
    ));
}

function StatValues({ stats }: { stats: Stat[] }) {
    return stats.map((stat, index) => (
        <td key={index} className={statClass(stat, index, "td")}>
            {stat.explanation ? (
                <span className={recipe.changed}>
                    <Information
                        text={stat.value}
                        explanation={stat.explanation}
                    />
                </span>
            ) : (
                stat.value
            )}
        </td>
    ));
}

function Weapons({ weapons, columns }: { weapons: Weapon[]; columns: Stat[] }) {
    if (!weapons.length) return null;
    // Full-width Cotton rows span implicit columns as well as the headings.
    const tableSpan = 99;
    return (
        <div className={recipe.weaponRoot}>
            <table className={recipe.table} aria-label="Weapons">
                <thead className={recipe.weaponHeaderRow}>
                    <tr>
                        <th scope="col" className={recipe.weaponHeader}>
                            Weapons
                        </th>
                        <StatHeadings stats={columns} />
                    </tr>
                </thead>
                <tbody className={recipe.weaponBody}>
                    {weapons.map((weapon, index) => (
                        <Fragment key={weapon.key || index}>
                            <tr
                                className={
                                    index ? recipe.weaponDivider : undefined
                                }
                            >
                                <td
                                    colSpan={
                                        weapon.stats.length ? 1 : tableSpan
                                    }
                                    className={
                                        weapon.stats.length
                                            ? recipe.weaponName
                                            : recipe.weaponNoStats
                                    }
                                >
                                    <span className={recipe.weaponNameGroup}>
                                        <span className={recipe.names}>
                                            {weapon.name}
                                        </span>
                                        <TierControls choices={weapon.tiers} />
                                        <CardActions
                                            name={weapon.name}
                                            actions={weapon.actions}
                                            accessory={weapon.accessorise}
                                        />
                                    </span>
                                </td>
                                <StatValues stats={weapon.stats} />
                            </tr>
                            {!!weapon.traits.length && (
                                <tr>
                                    {!!weapon.stats.length && <td />}
                                    <td
                                        colSpan={
                                            weapon.stats.length || tableSpan
                                        }
                                        className={recipe.weaponTraits}
                                    >
                                        <Names lines={weapon.traits} />
                                    </td>
                                </tr>
                            )}
                            {weapon.profiles.map((profile, profileIndex) => (
                                <Fragment key={profile.key || profileIndex}>
                                    <tr>
                                        <td className={recipe.weaponName}>
                                            <span
                                                className={
                                                    recipe.weaponProfileName
                                                }
                                            >
                                                <span
                                                    className={
                                                        recipe.weaponProfileText
                                                    }
                                                >
                                                    <span aria-hidden="true">
                                                        -
                                                    </span>
                                                    <span>{profile.name}</span>
                                                </span>
                                                <CardActions
                                                    name={profile.name}
                                                    actions={profile.actions}
                                                />
                                            </span>
                                        </td>
                                        <StatValues stats={profile.stats} />
                                    </tr>
                                    {!!profile.traits.length && (
                                        <tr>
                                            <td />
                                            <td
                                                colSpan={
                                                    profile.stats.length || 1
                                                }
                                                className={recipe.weaponTraits}
                                            >
                                                <Names lines={profile.traits} />
                                            </td>
                                        </tr>
                                    )}
                                </Fragment>
                            ))}
                            {!!weapon.accessories.length && (
                                <tr>
                                    <td
                                        colSpan={tableSpan}
                                        className={recipe.weaponExtra}
                                    >
                                        {weapon.accessories.some(
                                            (line) => line.actions?.length,
                                        ) ? (
                                            <ul
                                                className={recipe.weaponChoices}
                                            >
                                                {weapon.accessories.map(
                                                    (line, i) => (
                                                        <li
                                                            key={line.key || i}
                                                            className="flex items-center gap-2"
                                                        >
                                                            <span className="min-w-0">
                                                                <span aria-hidden="true">
                                                                    +
                                                                </span>{" "}
                                                                <Information
                                                                    text={
                                                                        line.text
                                                                    }
                                                                    explanation={
                                                                        line.explanation
                                                                    }
                                                                />
                                                            </span>
                                                            <CardActions
                                                                name={line.text}
                                                                actions={
                                                                    line.actions
                                                                }
                                                            />
                                                        </li>
                                                    ),
                                                )}
                                            </ul>
                                        ) : (
                                            <span
                                                className={recipe.accessories}
                                            >
                                                <span aria-hidden="true">
                                                    +
                                                </span>{" "}
                                                <Names
                                                    lines={weapon.accessories}
                                                />
                                            </span>
                                        )}
                                    </td>
                                </tr>
                            )}
                            {!!weapon.choices.length && (
                                <tr>
                                    <td
                                        colSpan={tableSpan}
                                        className={recipe.weaponExtra}
                                    >
                                        <ul className={recipe.weaponChoices}>
                                            <ItemChoices
                                                choices={weapon.choices}
                                                weapon
                                            />
                                        </ul>
                                    </td>
                                </tr>
                            )}
                        </Fragment>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

/** Shared card facts; stored-card controls are supplied by the workflow owner. */
export function ModelPreview(
    props: ModelPreviewProps & {
        presentation?: {
            id: string;
            label: string;
            nameAction: ReactNode;
            profileExtra: ReactNode;
            figures: ReactNode;
            actions: ReactNode;
            dead: boolean;
        };
    },
) {
    return (
        <div
            className={`${recipe.root} ${props.presentation?.dead ? "opacity-60" : ""}`}
            id={props.presentation?.id}
            role="region"
            aria-label={props.presentation?.label || `${props.name} preview`}
        >
            <div className={recipe.header}>
                <div className={recipe.headerGrid}>
                    <div className={recipe.heading}>
                        <div className={recipe.name}>
                            {props.name}
                            {props.presentation?.nameAction}
                        </div>
                    </div>
                    <div className={recipe.profilePosition}>
                        {props.profileName && (
                            <div className={recipe.profile}>
                                {props.profileName}
                            </div>
                        )}
                        {props.presentation?.profileExtra}
                        {props.ownerLine && (
                            <div className={recipe.profile}>
                                {props.ownerLine}
                            </div>
                        )}
                    </div>
                    <div className={recipe.figures}>
                        {props.presentation?.figures ?? (
                            <Information
                                plain
                                text={`${props.rating}¢`}
                                explanation="Rating, including weapons and wargear"
                            />
                        )}
                    </div>
                    {props.presentation?.actions}
                </div>
            </div>
            <div className={recipe.statRoot}>
                <table className={recipe.table} aria-label="Characteristics">
                    <tbody>
                        {props.statGroups.map((group, index) => {
                            const last = index === props.statGroups.length - 1;
                            const showType = last && !!props.typeLine;
                            return (
                                <Fragment key={index}>
                                    <tr>
                                        <StatHeadings stats={group} />
                                        {showType && (
                                            <>
                                                <th
                                                    scope="col"
                                                    colSpan={props.typeSpan}
                                                    className={
                                                        recipe.typeHeader
                                                    }
                                                >
                                                    Type
                                                </th>
                                                <th
                                                    scope="col"
                                                    className={
                                                        recipe.typeHeader
                                                    }
                                                >
                                                    XP
                                                </th>
                                            </>
                                        )}
                                    </tr>
                                    <tr
                                        className={
                                            !last
                                                ? recipe.statRowDivider
                                                : undefined
                                        }
                                    >
                                        <StatValues stats={group} />
                                        {showType && (
                                            <>
                                                <td
                                                    colSpan={props.typeSpan}
                                                    className={recipe.typeCell}
                                                >
                                                    {props.typeLine}
                                                </td>
                                                <td className={recipe.xpCell}>
                                                    {props.xpTarget ? (
                                                        <>
                                                            <Information
                                                                plain
                                                                text={String(
                                                                    props.xp,
                                                                )}
                                                                explanation="Current"
                                                            />
                                                            <span
                                                                className={
                                                                    recipe.muted
                                                                }
                                                            >
                                                                /
                                                            </span>
                                                            <span
                                                                className={
                                                                    recipe.muted
                                                                }
                                                            >
                                                                <Information
                                                                    plain
                                                                    text={String(
                                                                        props.xpTarget,
                                                                    )}
                                                                    explanation="Target"
                                                                />
                                                            </span>
                                                        </>
                                                    ) : (
                                                        props.xp
                                                    )}
                                                </td>
                                            </>
                                        )}
                                    </tr>
                                </Fragment>
                            );
                        })}
                    </tbody>
                </table>
            </div>
            <dl className={recipe.details}>
                {props.details.map((row, index) => (
                    <Fragment key={row.key || index}>
                        <dt className={recipe.detailLabel}>
                            {row.label}
                            {row.editHref && (
                                <>
                                    {" "}
                                    <ButtonLink
                                        href={row.editHref}
                                        variant="text"
                                        size="xs"
                                        className={cotton.modelCard.editLink}
                                        aria-label="Edit skills & powers"
                                        title="Edit skills & powers"
                                    >
                                        <span className="n26-icon-inline">
                                            <Icon name="pencil" className="" />
                                        </span>
                                    </ButtonLink>
                                </>
                            )}
                        </dt>
                        <dd className={recipe.detailValue}>
                            {row.parts.map((part, partIndex) => {
                                const Tag =
                                    part.kind === "gear" ? "div" : "span";
                                return (
                                    <Tag
                                        key={part.key || partIndex}
                                        className={
                                            part.kind === "gear"
                                                ? recipe.gearPart
                                                : recipe.part
                                        }
                                    >
                                        <DetailPart part={part} />
                                        {partIndex < row.parts.length - 1 && (
                                            <span className={recipe.separator}>
                                                ,
                                            </span>
                                        )}
                                    </Tag>
                                );
                            })}
                        </dd>
                    </Fragment>
                ))}
            </dl>
            <Weapons weapons={props.weapons} columns={props.weaponColumns} />
        </div>
    );
}
