import { useId } from "react";
import cotton from "../generated/cotton.json";
import { Button, ButtonLink, Icon } from "./index";
import { ActionMenu } from "./ActionMenu";

export type EquipmentChoice = {
    choose: "one" | "one-or-none" | "any";
    options: Array<{
        key: string;
        name: string;
        surcharge: number;
        checked: boolean;
        setKey: string;
        price: number;
    }>;
};
export type EquipmentNote = { text: string; level: string };
export type EquipmentPart = {
    key: string;
    name: string;
    price: number;
    tradePoints: number | null;
    exclusive: boolean;
    notes: EquipmentNote[];
};
export type EquipmentPurchase = EquipmentPart & {
    choices: EquipmentChoice[];
    parts: EquipmentPart[];
};
type EquipmentAction = { label: string; target: string; tone: string };
type OwnedPart = {
    id: string;
    name: string;
    rating: number;
    actions: EquipmentAction[];
};
export type EquipmentEntry = {
    key: string;
    name: string;
    basePrice: number;
    tradePoints: number | null;
    exclusive: boolean;
    purchase: EquipmentPurchase | null;
    count: number;
    expanded: boolean;
    copies: Array<
        OwnedPart & {
            chosen: string[];
            accessorise: EquipmentAction | null;
            parts: OwnedPart[];
        }
    >;
};
export const equipmentDefaults = (groups: EquipmentChoice[]) =>
    groups.flatMap((group) =>
        group.options
            .filter((option) => option.checked)
            .map((option) => option.key),
    );

export function EquipmentChoices({
    groups,
    selected,
    onChange,
    label,
}: {
    groups: EquipmentChoice[];
    selected: string[];
    onChange: (keys: string[]) => void;
    label: string;
}) {
    const id = useId();
    const recipe = cotton.hireCatalogue;
    function choose(group: EquipmentChoice, key: string, checked: boolean) {
        const members = new Set(group.options.map((option) => option.key));
        const next = selected.filter((value) =>
            group.choose === "any" ? value !== key : !members.has(value),
        );
        if (key && checked) next.push(key);
        onChange(next);
    }
    return (
        <>
            {groups.map((group, index) => (
                <fieldset className="min-w-0" key={index}>
                    <legend className={index ? recipe.groupHeader : "sr-only"}>
                        {group.choose === "any"
                            ? "Choose any"
                            : group.choose === "one"
                              ? "Choose one"
                              : "Choose one, or none"}{" "}
                        for {label}
                    </legend>
                    {[
                        ...group.options,
                        ...(group.choose === "one-or-none"
                            ? [{ key: "", name: "None", surcharge: 0 }]
                            : []),
                    ].map((option) => (
                        <label key={option.key} className={recipe.optionLabel}>
                            <input
                                className={recipe.optionInput}
                                type={
                                    group.choose === "any"
                                        ? "checkbox"
                                        : "radio"
                                }
                                name={`${id}-${index}`}
                                value={option.key}
                                checked={
                                    option.key
                                        ? selected.includes(option.key)
                                        : !group.options.some((option) =>
                                              selected.includes(option.key),
                                          )
                                }
                                onChange={(event) =>
                                    choose(
                                        group,
                                        option.key,
                                        event.target.checked,
                                    )
                                }
                            />
                            <span className={recipe.optionName}>
                                {option.name}
                            </span>
                            {!!option.surcharge && (
                                <span className={recipe.optionPrice}>
                                    {option.surcharge > 0 ? "+" : "−"}
                                    {Math.abs(option.surcharge)}¢
                                </span>
                            )}
                        </label>
                    ))}
                </fieldset>
            ))}
        </>
    );
}

function Terms({ part }: { part: EquipmentPart | EquipmentEntry }) {
    const recipe = cotton.equipment;
    return part.exclusive ? (
        <span
            className={recipe.tradePoints}
            title="Exclusive — equipment list only"
        >
            E
        </span>
    ) : part.tradePoints ? (
        <span
            className={recipe.tradePoints}
            title={`${part.tradePoints} trade points`}
        >
            {part.tradePoints}TP
        </span>
    ) : null;
}
function Notes({ notes }: { notes: EquipmentNote[] }) {
    return (
        <>
            {notes.map((note, index) => (
                <div
                    key={index}
                    className={`${cotton.equipment.note} ${note.level === "error" ? "font-semibold" : ""}`}
                >
                    {note.level !== "info" && (
                        <span className="text-muted">! </span>
                    )}
                    {note.text}
                </div>
            ))}
        </>
    );
}
function Actions({ part }: { part: OwnedPart }) {
    const [first, ...more] = part.actions;
    return (
        <span className="flex shrink-0 items-center gap-1">
            {first && (
                <ButtonLink
                    href={first.target}
                    size="sm"
                    variant={first.tone === "danger" ? "danger" : "default"}
                    data-busy="off"
                >
                    {first.label}
                </ButtonLink>
            )}
            {more.length > 0 && (
                <ActionMenu
                    label={`More for ${part.name}`}
                    trigger="chevron"
                    items={more.map((action, index) => ({
                        label: action.label,
                        href: action.target,
                        tone: action.tone === "danger" ? "danger" : "default",
                        separatorBefore:
                            action.tone === "danger" &&
                            index > 0 &&
                            more[index - 1].tone !== "danger",
                    }))}
                />
            )}
        </span>
    );
}

export type EquipmentDraft = {
    paid: string;
    selection: string[];
    parts: Record<string, string>;
    partPrices: Record<string, string>;
};
export function equipmentDraft(entry: EquipmentEntry): EquipmentDraft {
    return {
        paid: String(entry.purchase?.price ?? 0),
        selection: equipmentDefaults(entry.purchase?.choices ?? []),
        parts: {},
        partPrices: {},
    };
}

export function EquipmentRow({
    entry,
    expanded,
    onExpand,
    onBuy,
    disabled,
    draft,
    onDraftChange,
}: {
    entry: EquipmentEntry;
    draft: EquipmentDraft;
    onDraftChange: (
        update: (previous: EquipmentDraft) => EquipmentDraft,
    ) => void;
    expanded: boolean;
    onExpand: () => void;
    disabled: boolean;
    onBuy: (
        purchase: EquipmentPurchase,
        paid: string,
        selection: string[],
        parts: Array<{ key: string; paid: string }>,
    ) => void;
}) {
    const recipe = cotton.hireCatalogue;
    const equip = cotton.equipment;
    const id = useId();
    const purchase = entry.purchase;
    const { paid, selection, parts, partPrices } = draft;
    const surcharge =
        purchase?.choices
            .flatMap((group) => group.options)
            .filter((option) => selection.includes(option.key))
            .reduce((sum, option) => sum + option.surcharge, 0) ?? 0;
    const amount = paid === "" ? (purchase?.price ?? 0) : Number(paid);
    function price(
        part: EquipmentPart,
        raw: string,
        change: (raw: string) => void,
        base = false,
    ) {
        return (
            <div className="n26-cp-price flex shrink-0 items-center justify-end gap-1.5 text-sm text-ink-900 dark:text-ink-100">
                {raw !== "" && Number(raw) !== part.price && (
                    <span
                        className="text-xs text-muted"
                        title={`Listed at ${part.price}¢`}
                    >
                        {Number(raw) > part.price ? "+" : "−"}
                        {Math.abs(Number(raw) - part.price)}¢
                    </span>
                )}
                <input
                    className={equip.priceInput}
                    type="number"
                    min={Math.min(0, part.price)}
                    max={100000}
                    step={1}
                    inputMode="numeric"
                    aria-label={`${base ? "Base price" : "Price"} for ${part.name}`}
                    value={raw}
                    onChange={(event) => change(event.target.value)}
                />
            </div>
        );
    }
    const buy = purchase && (
        <>
            <div className={recipe.rowHeader}>
                <span className={recipe.nameBlock}>
                    {entry.count ? (
                        "Buy another"
                    ) : (
                        <>
                            <span className={recipe.rail} aria-hidden="true" />
                            <span className={`${recipe.name} break-words`}>
                                {entry.name}
                            </span>
                        </>
                    )}
                </span>
                <Terms part={entry} />
                {price(
                    purchase,
                    paid,
                    (raw) =>
                        onDraftChange((previous) => ({
                            ...previous,
                            paid: raw,
                        })),
                    purchase.choices.length > 0,
                )}
                <Button
                    size="sm"
                    variant="success"
                    disabled={disabled}
                    aria-label={`Buy ${entry.name}`}
                    onClick={() =>
                        onBuy(
                            purchase,
                            paid,
                            selection,
                            Object.entries(parts).map(([key, value]) => ({
                                key,
                                paid: value,
                            })),
                        )
                    }
                >
                    Buy
                </Button>
            </div>
            {purchase.choices.length > 0 && (
                <div className={recipe.inset}>
                    <EquipmentChoices
                        groups={purchase.choices}
                        selected={selection}
                        onChange={(selection) =>
                            onDraftChange((previous) => ({
                                ...previous,
                                selection,
                            }))
                        }
                        label={entry.name}
                    />
                    <p role="status" className="text-sm text-muted">
                        Total{" "}
                        {Number.isFinite(amount) ? amount + surcharge : "—"}¢
                    </p>
                </div>
            )}
            <Notes notes={purchase.notes} />
            {purchase.parts.map((part) => (
                <div key={part.key} className={recipe.inset}>
                    <div className={recipe.rowHeader}>
                        <label className={recipe.optionLabel}>
                            <input
                                className={recipe.optionInput}
                                type="checkbox"
                                checked={part.key in parts}
                                onChange={(event) =>
                                    onDraftChange((previous) => {
                                        const parts = { ...previous.parts };
                                        if (event.target.checked)
                                            parts[part.key] =
                                                previous.partPrices[part.key] ??
                                                String(part.price);
                                        else delete parts[part.key];
                                        return { ...previous, parts };
                                    })
                                }
                            />
                            <span className={recipe.optionName}>
                                {part.name}
                            </span>
                        </label>
                        <Terms part={part} />
                        {price(
                            part,
                            part.key in parts
                                ? parts[part.key]
                                : (partPrices[part.key] ?? String(part.price)),
                            (raw) => {
                                onDraftChange((previous) => ({
                                    ...previous,
                                    partPrices: {
                                        ...previous.partPrices,
                                        [part.key]: raw,
                                    },
                                    parts:
                                        part.key in previous.parts
                                            ? {
                                                  ...previous.parts,
                                                  [part.key]: raw,
                                              }
                                            : previous.parts,
                                }));
                            },
                        )}
                    </div>
                    <Notes notes={part.notes} />
                </div>
            ))}
        </>
    );
    return (
        <fieldset
            disabled={disabled}
            aria-label={`${entry.name} equipment`}
            className={`${recipe.row} min-w-0`}
        >
            {entry.count ? (
                <>
                    <div className={recipe.rowHeader}>
                        <span className={recipe.nameBlock}>
                            <span className={recipe.rail} aria-hidden="true" />
                            <span className={`${recipe.name} break-words`}>
                                {entry.name}
                            </span>
                        </span>
                        <Terms part={entry} />
                        <Button
                            size="sm"
                            onClick={onExpand}
                            aria-label={`${expanded ? "Hide" : "Show"} ${entry.name} in stash (${entry.count})`}
                            className="inline-flex items-center gap-1.5"
                            aria-expanded={expanded}
                            aria-controls={id}
                        >
                            {entry.count} in stash
                            <Icon
                                name="chevron-down"
                                className={`size-3 transition-transform ${expanded ? "rotate-180" : ""}`}
                                strokeWidth={2.5}
                            />
                        </Button>
                    </div>
                    <div id={id} hidden={!expanded} className={recipe.inset}>
                        <div className={equip.copyList}>
                            {entry.copies.map((copy) => (
                                <div key={copy.id}>
                                    <div className={equip.copyLine}>
                                        <span className={equip.copyNameBlock}>
                                            <span className={equip.copyName}>
                                                {copy.name}
                                                {copy.accessorise && (
                                                    <>
                                                        {" "}
                                                        <ButtonLink
                                                            href={
                                                                copy.accessorise
                                                                    .target
                                                            }
                                                            variant="text"
                                                            size="xs"
                                                            data-busy="off"
                                                        >
                                                            {
                                                                copy.accessorise
                                                                    .label
                                                            }
                                                        </ButtonLink>
                                                    </>
                                                )}
                                            </span>
                                            {copy.chosen.length > 0 && (
                                                <span className={equip.chosen}>
                                                    {copy.chosen.join(" · ")}
                                                </span>
                                            )}
                                        </span>
                                        <span className={equip.rating}>
                                            {copy.rating
                                                ? `${copy.rating}¢`
                                                : ""}
                                        </span>
                                        <Actions part={copy} />
                                    </div>
                                    {copy.parts.map((part) => (
                                        <div
                                            key={part.id}
                                            className={equip.partLine}
                                        >
                                            <span className={equip.partName}>
                                                {part.name}
                                            </span>
                                            <span className={equip.rating}>
                                                {part.rating
                                                    ? `+${part.rating}¢`
                                                    : ""}
                                            </span>
                                            <Actions part={part} />
                                        </div>
                                    ))}
                                </div>
                            ))}
                        </div>
                        {buy && (
                            <div className="mt-1 border-t border-box-border pt-1">
                                {buy}
                            </div>
                        )}
                    </div>
                </>
            ) : (
                buy
            )}
        </fieldset>
    );
}

export function Tally({
    facts,
}: {
    facts: Array<{
        label: string;
        value: string;
        sub: string;
        ruled: boolean;
        strong: boolean;
    }>;
}) {
    return (
        <dl className={cotton.tally["00"].root}>
            {facts.map((fact, index) => {
                const recipe =
                    cotton.tally[
                        `${fact.ruled ? 1 : 0}${fact.strong ? 1 : 0}` as keyof typeof cotton.tally
                    ];
                return (
                    <div key={index} className={recipe.row}>
                        <dt className={recipe.label}>
                            {fact.label}
                            {fact.sub && (
                                <span className={recipe.sub}>{fact.sub}</span>
                            )}
                        </dt>
                        <dd className={recipe.value}>{fact.value}</dd>
                    </div>
                );
            })}
        </dl>
    );
}

export function EquipmentRail({
    tabs,
}: {
    tabs: Array<{
        key: string;
        label: string;
        title: string;
        href: string;
        current: boolean;
    }>;
}) {
    const recipe = cotton.equipmentRail;
    return (
        <nav aria-label="Which list" className={recipe.root}>
            {tabs.map((tab) => (
                <a
                    key={tab.key}
                    href={tab.href}
                    title={tab.title}
                    aria-current={tab.current ? "page" : undefined}
                    data-busy="off"
                    className={tab.current ? recipe.active : recipe.inactive}
                >
                    {tab.label}
                </a>
            ))}
        </nav>
    );
}
