import { Fragment } from "react";
import cotton from "../generated/cotton.json";
import { HelpPopover } from "./HelpPopover";

type Stat = {
    shortName: string;
    fullName: string;
    value: string;
    highlighted: boolean;
    firstOfGroup: boolean;
    explanation: string;
};
type ItemChoice = { label: string; values: string[] };
type Line = { text: string; explanation: string; choices: ItemChoice[] };
type Part =
    | { kind: "names" | "gear"; lines: Line[] }
    | { kind: "counter"; value: number }
    | { kind: "choice"; chosen: string | null; prompt: string };
type Weapon = {
    name: string;
    stats: Stat[];
    traits: Line[];
    profiles: { name: string; stats: Stat[]; traits: Line[] }[];
    accessories: Line[];
    choices: ItemChoice[];
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
    details: { label: string; parts: Part[] }[];
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
}: {
    text: string;
    explanation: string;
    suffix?: string;
}) {
    return explanation ? (
        <HelpPopover
            label={`${text.trim()}: ${explanation}`}
            triggerContent={`${text}${suffix}`}
        >
            <p>{explanation}</p>
        </HelpPopover>
    ) : (
        <span>
            {text}
            {suffix}
        </span>
    );
}

function Names({ lines }: { lines: Line[] }) {
    if (!lines.length) return <>—</>;
    return lines.map((line, index) => (
        <Information
            key={index}
            text={line.text}
            suffix={
                index < lines.length - 1
                    ? line.explanation
                        ? ",\u00a0"
                        : ", "
                    : ""
            }
            explanation={line.explanation}
        />
    ));
}

function ItemChoices({ choices }: { choices: ItemChoice[] }) {
    return choices.map((choice, index) => (
        <span key={index} className={recipe.itemChoice}>
            {choice.label}: {choice.values.join(", ")}
        </span>
    ));
}

function DetailPart({ part }: { part: Part }) {
    if (part.kind === "counter")
        return <span className={recipe.counter}>{part.value}</span>;
    if (part.kind === "choice")
        return (
            <span>
                {part.chosen !== null && <span>{part.chosen}</span>}
                {part.chosen !== null && part.prompt && " "}
                {part.prompt && (
                    <span className={recipe.prompt}>{part.prompt}</span>
                )}
            </span>
        );
    if (part.kind === "names")
        return (
            <span className={recipe.names}>
                <Names lines={part.lines} />
            </span>
        );
    return (
        <>
            <Names lines={part.lines} />
            {part.kind === "gear" &&
                part.lines.map((line, index) =>
                    line.choices.map((choice, choiceIndex) => (
                        <span
                            key={`${index}:${choiceIndex}`}
                            className={recipe.itemChoice}
                        >
                            {line.text} — {choice.label}:{" "}
                            {choice.values.join(", ")}
                        </span>
                    )),
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
                        <Fragment key={index}>
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
                                <Fragment key={profileIndex}>
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
                                        <span className={recipe.accessories}>
                                            <span aria-hidden="true">+</span>{" "}
                                            <Names lines={weapon.accessories} />
                                        </span>
                                    </td>
                                </tr>
                            )}
                            {!!weapon.choices.length && (
                                <tr>
                                    <td
                                        colSpan={tableSpan}
                                        className={recipe.weaponExtra}
                                    >
                                        <ItemChoices choices={weapon.choices} />
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

/** Read-only hire facts; the caller owns option selection and preview loading. */
export function ModelPreview(props: ModelPreviewProps) {
    return (
        <div
            className={recipe.root}
            role="region"
            aria-label={`${props.name} preview`}
        >
            <div className={recipe.header}>
                <div className={recipe.headerGrid}>
                    <div className={recipe.heading}>
                        <div className={recipe.name}>{props.name}</div>
                    </div>
                    <div className={recipe.profilePosition}>
                        {props.profileName && (
                            <div className={recipe.profile}>
                                {props.profileName}
                            </div>
                        )}
                        {props.ownerLine && (
                            <div className={recipe.profile}>
                                {props.ownerLine}
                            </div>
                        )}
                    </div>
                    <div className={recipe.figures}>
                        <Information
                            text={`${props.rating}¢`}
                            explanation="Rating, including weapons and wargear"
                        />
                    </div>
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
                    <Fragment key={index}>
                        <dt className={recipe.detailLabel}>{row.label}</dt>
                        <dd className={recipe.detailValue}>
                            {row.parts.map((part, partIndex) => {
                                const Tag =
                                    part.kind === "gear" ? "div" : "span";
                                return (
                                    <Tag
                                        key={partIndex}
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
