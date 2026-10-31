import { TacticCard, type Card } from "./TacticCard";
import { useCarouselGestures } from "./useCarouselGestures";
import { PrintPreview } from "./PrintPreview";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
    Button,
    Dialog,
    FormActions,
    ButtonLink,
    RadioCards,
    RadioCard,
    Field,
    FieldErrors,
    Input,
    Icon,
    MenuButton,
    MenuAction,
    MenuGroup,
    MenuSeparator,
    NativeSelect,
} from "../../ui";

export type GangTacticsProps = {
    cards: Card[];
    yours: boolean;
    toGenerate: number;
    tableChoices: {
        value: string;
        label: string;
        description: string;
        checked: boolean;
        full: boolean;
    }[];
    count: string;
    errors: Record<string, string[]>;
    csrfToken: string;
    rollUrl: string;
    batchUrl: string;
    /** Every set in the library: a bonus card may come from any of them. */
    bonusChoices: GangTacticsProps["tableChoices"];
    bonusUrl: string;
    printView: boolean;
    initialLayout: string;
};
export function GangTactics(props: GangTacticsProps) {
    const { yours, printView } = props;
    const [cards, setCards] = useState(props.cards);
    const [toGenerate, setToGenerate] = useState(props.toGenerate);
    const [tableChoices, setTableChoices] = useState(props.tableChoices);
    const [bonusChoices, setBonusChoices] = useState(props.bonusChoices);
    const [bonusOpen, setBonusOpen] = useState(false);
    const [bonusTable, setBonusTable] = useState("");
    const [bonusCount, setBonusCount] = useState("1");
    const [action, setAction] = useState<{
        kind: "delete" | "reroll";
        keys: string[];
        returnFocusId: string;
    } | null>(null);
    const [actionTable, setActionTable] = useState("");
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const submitting = useRef(false);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [layout, setLayout] = useState(() =>
        props.initialLayout === "grid" || props.initialLayout === "carousel"
            ? props.initialLayout
            : matchMedia("(max-width: 639px)").matches
              ? "carousel"
              : "grid",
    );
    const [active, setActive] = useState(0);
    const [columns, setColumns] = useState(5);
    const [screenScale, setScreenScale] = useState(1);
    const [lastStart, setLastStart] = useState(Math.max(0, cards.length - 1));
    const [generationOpen, setGenerationOpen] = useState(false);
    const [orientation, setOrientation] = useState("portrait");
    const [scaleInput, setScaleInput] = useState("100");
    const scale = Math.min(200, Math.max(25, Number(scaleInput) || 100));
    const activeIndex = useRef(active);
    activeIndex.current = active;
    const track = useRef<HTMLUListElement>(null);
    const dragging = useCarouselGestures(
        track,
        layout === "carousel" && !printView,
    );
    const [pending, setPending] = useState(false);
    const [table, setTable] = useState(
        tableChoices.find((choice) => choice.checked)?.value ??
            tableChoices.find((choice) => !choice.full)?.value ??
            "",
    );
    useEffect(() => {
        const onPop = () => {
            const value = new URL(location.href).searchParams.get("layout");
            setLayout(
                value === "grid" || value === "carousel"
                    ? value
                    : matchMedia("(max-width: 639px)").matches
                      ? "carousel"
                      : "grid",
            );
        };
        const media = matchMedia("(max-width: 639px)");
        media.addEventListener("change", onPop);
        window.addEventListener("popstate", onPop);
        return () => {
            media.removeEventListener("change", onPop);
            window.removeEventListener("popstate", onPop);
        };
    }, []);
    function chooseLayout(value: string) {
        setLayout(value);
        const url = new URL(location.href);
        url.searchParams.set("layout", value);
        history.pushState({}, "", url);
    }
    function show(index: number) {
        const el = track.current;
        index = Math.max(0, Math.min(lastStart, index));
        const item = el?.children[index] as HTMLElement | undefined;
        if (!el || !item) return;
        setActive(index);
        el.scrollTo({
            left: item.offsetLeft - (el.children[0] as HTMLElement).offsetLeft,
            behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
                ? "instant"
                : "smooth",
        });
    }
    useEffect(() => {
        const el = track.current;
        if (!el || printView) return;
        const first = el.children[0] as HTMLElement | undefined;
        const measure = () => {
            const style = getComputedStyle(el);
            const padding =
                parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
            setScreenScale(
                Math.max(
                    0.1,
                    (el.clientWidth - padding - (columns - 1) * 16) /
                        columns /
                        245,
                ),
            );
            if (layout !== "carousel") return;
            const step = first ? first.offsetWidth + parseFloat(style.gap) : 1;
            const max = Math.max(0, el.scrollWidth - el.clientWidth);
            const last = Math.max(0, Math.ceil((max - 1) / step));
            const index = Math.min(activeIndex.current, last);
            setLastStart(last);
            setActive(index);
            el.scrollLeft = Math.min(index * step, max);
        };
        const observer = new ResizeObserver(measure);
        observer.observe(el);
        if (first) observer.observe(first);
        return () => observer.disconnect();
    }, [columns, layout, printView, cards]);
    function printSelected() {
        const url = new URL(props.rollUrl, location.origin);
        url.searchParams.set("print", "1");
        selected.forEach((pk) => url.searchParams.append("selected", pk));
        window.open(url.toString(), "_blank", "noopener");
    }
    function openAction(kind: "delete" | "reroll", keys: string[]) {
        if (!keys.length || pending) return;
        const origin = document.activeElement as HTMLElement | null;
        const menu = origin?.closest('[role="menu"]');
        setAction({
            kind,
            keys,
            returnFocusId:
                menu?.getAttribute("aria-labelledby") ||
                origin?.id ||
                "tactics-print-action",
        });
        // Start on the first card's own set, unless the gang already holds
        // every tactic in it: then the first set that can still be rolled.
        const own = cards.find((card) => card.pk === keys[0])?.tableKey ?? "";
        const open = rerollChoices(keys).filter((choice) => !choice.full);
        setActionTable(
            open.some((choice) => choice.value === own)
                ? own
                : (open[0]?.value ?? ""),
        );
        setError("");
    }
    // Bonus cards alone may be re-rolled onto any set; a selection with a
    // counted card keeps to the gang's own sets.
    function rerollChoices(keys: string[]) {
        const chosen = cards.filter((card) => keys.includes(card.pk));
        return chosen.length > 0 && chosen.every((card) => card.bonus)
            ? bonusChoices
            : tableChoices;
    }
    function openBonus() {
        if (pending) return;
        setBonusTable(bonusChoices.find((choice) => !choice.full)?.value ?? "");
        setBonusCount("1");
        setError("");
        setBonusOpen(true);
    }
    async function submitBonus() {
        if (submitting.current) return;
        submitting.current = true;
        setPending(true);
        setError("");
        const fields = new URLSearchParams({
            table: bonusTable,
            count: bonusCount,
        });
        try {
            const response = await fetch(props.bonusUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "X-CSRFToken": props.csrfToken,
                },
                body: fields,
            });
            if (
                !response.headers
                    .get("content-type")
                    ?.includes("application/json")
            ) {
                throw new Error(
                    response.status === 403 || response.redirected
                        ? "Your session may have expired. Reload the page and try again."
                        : "The bonus cards could not be drawn. Reload the page and try again.",
                );
            }
            const result = await response.json();
            if (!response.ok)
                throw new Error(
                    result.error ||
                        "The bonus cards could not be drawn. Try again.",
                );
            setCards(result.cards);
            setToGenerate(result.toGenerate);
            setTableChoices(result.tableChoices);
            setBonusChoices(result.bonusChoices);
            setNotice(result.message);
            setBonusOpen(false);
        } catch (failure) {
            setError(
                failure instanceof TypeError
                    ? "The bonus cards could not be drawn. Check your connection and try again."
                    : failure instanceof Error
                      ? failure.message
                      : "The bonus cards could not be drawn. Try again.",
            );
        } finally {
            submitting.current = false;
            setPending(false);
        }
    }
    function changeSelected(kind: "delete" | "reroll") {
        openAction(kind, [...selected]);
    }
    async function submitAction() {
        if (!action || submitting.current) return;
        submitting.current = true;
        setPending(true);
        setError("");
        const fields = new URLSearchParams({
            action: action.kind,
            confirmed: "yes",
        });
        action.keys.forEach((key) => fields.append("selected", key));
        if (action.kind === "reroll") fields.set("table", actionTable);
        try {
            const response = await fetch(props.batchUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "X-CSRFToken": props.csrfToken,
                },
                body: fields,
            });
            if (
                !response.headers
                    .get("content-type")
                    ?.includes("application/json")
            ) {
                throw new Error(
                    response.status === 403 || response.redirected
                        ? "Your session may have expired. Reload the page and try again."
                        : "The tactics could not be updated. Reload the page and try again.",
                );
            }
            const result = await response.json();
            if (!response.ok)
                throw new Error(
                    result.error ||
                        "The tactics could not be updated. Try again.",
                );
            setCards(result.cards);
            setToGenerate(result.toGenerate);
            setTableChoices(result.tableChoices);
            setBonusChoices(result.bonusChoices);
            setTable(
                result.tableChoices.find(
                    (choice: GangTacticsProps["tableChoices"][number]) =>
                        choice.checked,
                )?.value ?? "",
            );
            setSelected(
                (current) =>
                    new Set(
                        [...current].filter((key) =>
                            result.cards.some((card: Card) => card.pk === key),
                        ),
                    ),
            );
            setNotice(result.message);
            setAction(null);
            requestAnimationFrame(() => {
                const print = document.getElementById("tactics-print-action");
                const target = print?.getClientRects().length
                    ? print
                    : document.querySelector<HTMLButtonElement>(
                          ".n26-tactics-overflow-actions button[aria-haspopup=menu]",
                      );
                target?.focus();
            });
        } catch (failure) {
            setError(
                failure instanceof TypeError
                    ? "The tactics could not be updated. Check your connection and try again."
                    : failure instanceof Error
                      ? failure.message
                      : "The tactics could not be updated. Try again.",
            );
        } finally {
            submitting.current = false;
            setPending(false);
        }
    }
    function toggleCard(key: string) {
        setSelected((current) => {
            const next = new Set(current);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    }
    const bonusButton = (
        <Button size="sm" onClick={openBonus} disabled={pending}>
            <Icon name="plus" strokeWidth={1.7} />{" "}
            <span>Generate bonus card</span>
        </Button>
    );
    const inactiveGeneration = (
        <Button
            size="sm"
            aria-label="No tactics awaiting generation"
            title="No tactics awaiting generation"
            aria-expanded={generationOpen}
            onClick={() => setGenerationOpen(!generationOpen)}
        >
            <Icon name="circle-minus" strokeWidth={1.7} />{" "}
            <span className="n26-tactics-generation-label">
                No tactics awaiting generation
            </span>
            <Icon name="chevron-down" strokeWidth={1.7} />
        </Button>
    );
    const selectionActions = [
        {
            label: "All",
            icon: "check-check",
            onClick: () => setSelected(new Set(cards.map((card) => card.pk))),
        },
        { label: "None", icon: "x", onClick: () => setSelected(new Set()) },
    ] as const;
    const changeActions = yours
        ? ([
              { label: "Re-roll", icon: "rotate-cw", kind: "reroll" },
              { label: "Delete", icon: "trash-2", kind: "delete" },
          ] as const)
        : [];
    const menu = (
        <MenuButton
            label="Gang tactics actions"
            title="More actions"
            trigger={<Icon name="ellipsis-vertical" strokeWidth={1.7} />}
        >
            <MenuGroup label={`${selected.size} selected`}>
                {selectionActions.map((item) => (
                    <MenuAction key={item.label} onClick={item.onClick}>
                        <Icon name={item.icon} strokeWidth={1.7} /> {item.label}
                    </MenuAction>
                ))}
            </MenuGroup>
            <MenuSeparator />
            <MenuAction onClick={printSelected}>
                <Icon name="printer" strokeWidth={1.7} /> Print
            </MenuAction>
            {changeActions.map((item) => (
                <MenuAction
                    key={item.kind}
                    disabled={!selected.size || pending}
                    onClick={() => changeSelected(item.kind)}
                    tone={item.kind === "delete" ? "danger" : undefined}
                >
                    <Icon name={item.icon} strokeWidth={1.7} /> {item.label}
                </MenuAction>
            ))}
        </MenuButton>
    );
    const cardItems = cards.map((card) => (
        <li
            key={card.pk}
            className="n26-tactic-item n26-print-tactic-item"
            data-selected={selected.has(card.pk)}
        >
            {!printView && (
                <div className="n26-tactic-actions">
                    <label className="n26-tactic-select">
                        <input
                            type="checkbox"
                            aria-label={`Select ${card.name}`}
                            checked={selected.has(card.pk)}
                            onChange={() => toggleCard(card.pk)}
                        />
                        <span className="sr-only">Select {card.name}</span>
                    </label>
                    {yours && (
                        <span className="n26-tactic-links">
                            <Button
                                size="sm"
                                className="n26-tactic-inline-action"
                                id={`reroll-${card.pk}`}
                                onClick={() => openAction("reroll", [card.pk])}
                            >
                                Re-roll
                            </Button>
                            <span aria-hidden="true">·</span>
                            <Button
                                size="sm"
                                className="n26-tactic-inline-action n26-tactic-inline-danger"
                                id={`delete-${card.pk}`}
                                onClick={() => openAction("delete", [card.pk])}
                            >
                                Delete
                            </Button>
                        </span>
                    )}
                </div>
            )}
            <TacticCard
                card={card}
                selected={selected.has(card.pk)}
                printView={printView}
                onToggle={() => toggleCard(card.pk)}
            />
        </li>
    ));
    return (
        <div
            className={`n26-tactics-island ${printView ? "n26-tactics-print-view" : ""}`}
            style={
                {
                    "--tactic-scale": scale / 100,
                    "--tactic-columns": columns,
                    "--tactic-screen-scale": screenScale,
                } as CSSProperties
            }
        >
            {!printView && (
                <dl
                    className="n26-tactics-figures grid grid-cols-2 gap-2 sm:gap-3"
                    data-tactics-figures
                >
                    <div className="flex flex-col justify-between gap-1 rounded-box border border-box-border p-3 sm:p-4">
                        <dt className="text-xs text-muted sm:text-sm">
                            Current gang tactics
                        </dt>
                        <dd className="text-2xl font-semibold tabular-nums sm:text-3xl text-ink-900 dark:text-ink-100">
                            {cards.length}
                        </dd>
                    </div>
                    <div className="flex flex-col justify-between gap-1 rounded-box border border-box-border p-3 sm:p-4">
                        <dt className="text-xs text-muted sm:text-sm">
                            Tactics to be generated
                        </dt>
                        <dd
                            className={`text-2xl font-semibold tabular-nums sm:text-3xl ${toGenerate ? "text-green-700 dark:text-green-400" : "text-ink-900 dark:text-ink-100"}`}
                        >
                            {toGenerate}
                        </dd>
                    </div>
                </dl>
            )}
            {notice && !printView && (
                <p
                    className="text-sm text-green-700 dark:text-green-400 mb-4"
                    role="status"
                >
                    {notice}
                </p>
            )}
            {printView ? (
                <div className="n26-tactics-print-toolbar">
                    <ButtonLink href={props.rollUrl}>
                        Back to gang tactics
                    </ButtonLink>
                    <Field label="Print scale (%)" htmlFor="tactic-print-scale">
                        <Input
                            id="tactic-print-scale"
                            type="number"
                            min={25}
                            max={200}
                            value={scaleInput}
                            onChange={(event) =>
                                setScaleInput(event.target.value)
                            }
                            onBlur={() => setScaleInput(String(scale))}
                        />
                    </Field>
                    <Field
                        label="Paper orientation"
                        htmlFor="tactic-orientation"
                    >
                        <NativeSelect
                            id="tactic-orientation"
                            value={orientation}
                            onChange={(event) =>
                                setOrientation(event.target.value)
                            }
                        >
                            <option value="portrait">Portrait</option>
                            <option value="landscape">Landscape</option>
                        </NativeSelect>
                    </Field>
                    <p className="text-sm text-muted">
                        A4 preview · 76 × 111 mm cards at 100%.
                    </p>
                    <style media="print">{`@page n26-tactics { size: A4 ${orientation}; }`}</style>
                    <Button variant="primary" onClick={() => window.print()}>
                        <Icon name="printer" strokeWidth={1.7} /> Print
                    </Button>
                </div>
            ) : (
                <>
                    <div className="n26-tactics-controls">
                        {yours && (
                            <div className="n26-tactics-inactive n26-tactics-inactive-wide">
                                {toGenerate === 0 && inactiveGeneration}
                                {bonusButton}
                            </div>
                        )}
                        {yours && (toGenerate > 0 || generationOpen) && (
                            <form
                                method="post"
                                action={props.rollUrl}
                                className={`flex flex-col gap-4 ${toGenerate === 0 ? "n26-tactics-generation-disabled" : ""}`}
                            >
                                <input
                                    type="hidden"
                                    name="csrfmiddlewaretoken"
                                    value={props.csrfToken}
                                />
                                <FieldErrors
                                    errors={props.errors.__all__ ?? []}
                                />
                                <div className="n26-tactics-sets">
                                    <RadioCards
                                        legend="Choose gang tactics set"
                                        min="12rem"
                                        errors={props.errors.table}
                                    >
                                        {tableChoices.map((choice) => (
                                            <RadioCard
                                                key={choice.value}
                                                name="table"
                                                value={choice.value}
                                                label={choice.label}
                                                description={choice.description}
                                                reason={choice.description}
                                                checked={table === choice.value}
                                                disabled={
                                                    choice.full ||
                                                    toGenerate === 0
                                                }
                                                onChange={() =>
                                                    setTable(choice.value)
                                                }
                                            />
                                        ))}
                                    </RadioCards>
                                </div>
                                <div className="n26-tactics-generation">
                                    <div className="n26-tactics-all">
                                        <p className="font-semibold">
                                            Generate all
                                        </p>
                                        <Button
                                            type="submit"
                                            name="how"
                                            value="all"
                                            variant="success"
                                            disabled={
                                                pending || toGenerate === 0
                                            }
                                        >
                                            Roll all ({toGenerate})
                                        </Button>
                                    </div>
                                    <div className="n26-tactics-number">
                                        <div className="w-44">
                                            <Field
                                                label="Number to generate"
                                                htmlFor="tactics-count"
                                                errors={props.errors.count}
                                            >
                                                <Input
                                                    type="number"
                                                    key={toGenerate}
                                                    id="tactics-count"
                                                    name="count"
                                                    min={1}
                                                    max={toGenerate}
                                                    defaultValue={
                                                        toGenerate === 0
                                                            ? "0"
                                                            : props.count
                                                    }
                                                    disabled={toGenerate === 0}
                                                />
                                            </Field>
                                        </div>
                                        <Button
                                            type="submit"
                                            name="how"
                                            value="some"
                                            variant="success"
                                            disabled={
                                                pending || toGenerate === 0
                                            }
                                        >
                                            Roll
                                        </Button>
                                    </div>
                                </div>
                            </form>
                        )}
                        {cards.length > 0 && (
                            <div className="n26-tactics-batch">
                                <div className="n26-tactics-selection">
                                    {selectionActions.map((item) => (
                                        <Button
                                            key={item.label}
                                            size="sm"
                                            onClick={item.onClick}
                                        >
                                            <Icon
                                                name={item.icon}
                                                strokeWidth={1.7}
                                            />{" "}
                                            {item.label}
                                        </Button>
                                    ))}
                                </div>
                                <div className="n26-tactics-selected-actions">
                                    <span
                                        className="text-sm text-muted"
                                        role="status"
                                    >
                                        {selected.size} selected
                                    </span>
                                    <Button
                                        size="sm"
                                        id="tactics-print-action"
                                        onClick={printSelected}
                                        title={
                                            selected.size
                                                ? "Preview selected cards for printing"
                                                : "Preview all cards for printing"
                                        }
                                    >
                                        <Icon
                                            name="printer"
                                            strokeWidth={1.7}
                                        />{" "}
                                        Print
                                    </Button>
                                    {changeActions.length > 0 && (
                                        <div className="n26-tactics-direct-actions">
                                            {changeActions.map((item) => (
                                                <Button
                                                    key={item.kind}
                                                    size="sm"
                                                    disabled={
                                                        !selected.size ||
                                                        pending
                                                    }
                                                    onClick={() =>
                                                        changeSelected(
                                                            item.kind,
                                                        )
                                                    }
                                                >
                                                    <Icon
                                                        name={item.icon}
                                                        strokeWidth={1.7}
                                                    />{" "}
                                                    {item.label}
                                                </Button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </>
            )}
            <section
                className="n26-tactics-collection"
                aria-label="Gang tactics"
            >
                {!printView && (
                    <div className="n26-tactics-heading">
                        {yours && (
                            <div className="n26-tactics-inactive n26-tactics-inactive-narrow">
                                {toGenerate === 0 && inactiveGeneration}
                                {bonusButton}
                            </div>
                        )}
                        <h2 className="text-lg font-semibold">
                            Gang tactics{" "}
                            <span className="ml-2 text-sm font-normal text-muted">
                                {cards.length}
                            </span>
                        </h2>
                        <div className="n26-tactics-view-controls">
                            <label className="n26-tactics-size-control">
                                <Icon name="zoom-out" strokeWidth={1.7} />
                                <input
                                    type="range"
                                    min="3"
                                    max="7"
                                    step="1"
                                    value={10 - columns}
                                    aria-label="Card size"
                                    aria-valuetext={`${columns} cards across`}
                                    onChange={(event) =>
                                        setColumns(
                                            10 - Number(event.target.value),
                                        )
                                    }
                                />
                                <Icon name="zoom-in" strokeWidth={1.7} />
                            </label>
                            <div
                                className="n26-tactics-layout"
                                role="group"
                                aria-label="Card layout"
                            >
                                {(
                                    [
                                        ["grid", "Grid", "layout-grid"],
                                        [
                                            "carousel",
                                            "Carousel",
                                            "gallery-horizontal",
                                        ],
                                    ] as const
                                ).map(([value, label, icon]) => (
                                    <Button
                                        key={value}
                                        size="sm"
                                        aria-label={label}
                                        title={label}
                                        aria-pressed={layout === value}
                                        onClick={() => chooseLayout(value)}
                                    >
                                        <Icon name={icon} strokeWidth={1.7} />
                                    </Button>
                                ))}
                            </div>
                            {cards.length > 0 && (
                                <div className="n26-tactics-overflow-actions">
                                    {menu}
                                </div>
                            )}
                        </div>
                    </div>
                )}
                {!printView && layout === "carousel" && cards.length > 0 && (
                    <nav
                        className="n26-tactic-indicators"
                        aria-label="Choose a card"
                    >
                        {cards.slice(0, lastStart + 1).map((card, index) => (
                            <button
                                key={card.pk}
                                type="button"
                                aria-label={`Show card ${index + 1}: ${card.name}`}
                                aria-current={
                                    active === index ? "true" : undefined
                                }
                                onClick={() => show(index)}
                            />
                        ))}
                    </nav>
                )}
                <div
                    className={`n26-tactic-frame ${!printView && layout === "carousel" ? "n26-tactic-carousel" : ""}`}
                >
                    {!printView &&
                        layout === "carousel" &&
                        cards.length > 0 && (
                            <Button
                                className="n26-tactic-previous"
                                aria-label="Previous card"
                                disabled={active === 0}
                                onClick={() => show(active - 1)}
                            >
                                <Icon name="chevron-left" strokeWidth={1.7} />
                            </Button>
                        )}
                    {printView ? (
                        <PrintPreview
                            orientation={orientation}
                            scale={scale}
                            items={cardItems}
                        />
                    ) : (
                        <>
                            <ul
                                ref={track}
                                className="n26-tactic-grid n26-print-tactic-grid"
                                data-dragging={dragging || undefined}
                                onKeyDown={(event) => {
                                    if (
                                        layout !== "carousel" ||
                                        (event.target as HTMLElement).closest(
                                            "input, a, button",
                                        )
                                    )
                                        return;
                                    if (event.key === "ArrowRight") {
                                        event.preventDefault();
                                        show(Math.min(lastStart, active + 1));
                                    }
                                    if (event.key === "ArrowLeft") {
                                        event.preventDefault();
                                        show(Math.max(0, active - 1));
                                    }
                                }}
                                tabIndex={
                                    layout === "carousel" && !printView
                                        ? 0
                                        : undefined
                                }
                                onScroll={() => {
                                    const el = track.current;
                                    if (
                                        layout !== "carousel" ||
                                        !el?.children.length
                                    )
                                        return;
                                    const first = el.children[0] as HTMLElement;
                                    const step =
                                        first.offsetWidth +
                                        parseFloat(getComputedStyle(el).gap);
                                    setActive(
                                        Math.max(
                                            0,
                                            Math.min(
                                                lastStart,
                                                el.scrollLeft >=
                                                    el.scrollWidth -
                                                        el.clientWidth -
                                                        1
                                                    ? lastStart
                                                    : Math.round(
                                                          el.scrollLeft / step,
                                                      ),
                                            ),
                                        ),
                                    );
                                }}
                            >
                                {cardItems}
                            </ul>
                        </>
                    )}

                    {!printView &&
                        layout === "carousel" &&
                        cards.length > 0 && (
                            <Button
                                className="n26-tactic-next"
                                aria-label="Next card"
                                disabled={active === lastStart}
                                onClick={() => show(active + 1)}
                            >
                                <Icon name="chevron-right" strokeWidth={1.7} />
                            </Button>
                        )}
                </div>
                {!cards.length && (
                    <p className="text-muted">
                        No gang tactics yet.
                        {yours && toGenerate > 0 ? " Roll for them above." : ""}
                    </p>
                )}
                {cards.length > 0 && (
                    <p className="n26-tactics-disclaimer text-xs text-muted">
                        All text is provided for reference only. Please consult
                        the official Necromunda Skirmish books/journals for
                        official wording.
                    </p>
                )}
            </section>
            {bonusOpen && (
                <Dialog
                    title="Generate bonus card"
                    lead="Draw extra tactics from any set. Bonus cards do not count against what the gang's Leader and Champions allow. The gang's log records the draw."
                    pending={pending}
                    onDismiss={() => {
                        if (!pending) setBonusOpen(false);
                    }}
                    onSubmit={(event) => {
                        event.preventDefault();
                        void submitBonus();
                    }}
                >
                    <Field label="Draw from" htmlFor="tactic-bonus-table">
                        <NativeSelect
                            id="tactic-bonus-table"
                            value={bonusTable}
                            disabled={pending}
                            onChange={(event) =>
                                setBonusTable(event.target.value)
                            }
                        >
                            {bonusChoices.map((choice) => (
                                <option
                                    key={choice.value}
                                    value={choice.value}
                                    disabled={choice.full}
                                >
                                    {choice.label}
                                </option>
                            ))}
                        </NativeSelect>
                    </Field>
                    <Field label="Number to draw" htmlFor="tactic-bonus-count">
                        <Input
                            type="number"
                            id="tactic-bonus-count"
                            min={1}
                            value={bonusCount}
                            disabled={pending}
                            onChange={(event) =>
                                setBonusCount(event.target.value)
                            }
                        />
                    </Field>
                    {error && (
                        <p
                            role="alert"
                            className="text-red-600 dark:text-red-400"
                        >
                            {error}
                        </p>
                    )}
                    <FormActions>
                        <Button
                            disabled={pending}
                            onClick={() => setBonusOpen(false)}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            variant="success"
                            disabled={pending || !bonusTable || !bonusCount}
                        >
                            {pending ? "Drawing…" : "Draw"}
                        </Button>
                    </FormActions>
                </Dialog>
            )}
            {action && (
                <Dialog
                    title={`${action.kind === "delete" ? "Delete" : "Re-roll"} ${action.keys.length === 1 ? cards.find((card) => card.pk === action.keys[0])?.name : `${action.keys.length} gang tactics`}`}
                    lead={
                        action.kind === "delete"
                            ? "These tactics can be generated again. The gang's log records the deletion."
                            : "Roll new tactics to replace the selected cards. The gang's log records the re-roll."
                    }
                    pending={pending}
                    returnFocusId={action.returnFocusId}
                    onDismiss={() => {
                        if (!pending) setAction(null);
                    }}
                    onSubmit={(event) => {
                        event.preventDefault();
                        void submitAction();
                    }}
                >
                    <ul className="text-sm list-disc pl-5">
                        {cards
                            .filter((card) => action.keys.includes(card.pk))
                            .map((card) => (
                                <li key={card.pk}>{card.name}</li>
                            ))}
                    </ul>
                    {action.kind === "reroll" && (
                        <Field
                            label={
                                action.keys.length === 1
                                    ? "Choose gang tactics set"
                                    : "Re-roll all selected cards from"
                            }
                            htmlFor="tactic-reroll-table"
                        >
                            <NativeSelect
                                id="tactic-reroll-table"
                                value={actionTable}
                                disabled={pending}
                                onChange={(event) =>
                                    setActionTable(event.target.value)
                                }
                            >
                                {rerollChoices(action.keys).map((choice) => (
                                    <option
                                        key={choice.value}
                                        value={choice.value}
                                        disabled={choice.full}
                                    >
                                        {choice.label}
                                    </option>
                                ))}
                            </NativeSelect>
                        </Field>
                    )}
                    {action.kind === "reroll" && action.keys.length > 1 && (
                        <p className="text-sm text-muted">
                            Every selected card is re-rolled on this set. To use
                            different sets, select and re-roll the cards for
                            each set separately.
                        </p>
                    )}
                    {error && (
                        <p
                            role="alert"
                            className="text-red-600 dark:text-red-400"
                        >
                            {error}
                        </p>
                    )}
                    <FormActions>
                        <Button
                            disabled={pending}
                            onClick={() => setAction(null)}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            variant="success"
                            disabled={
                                pending ||
                                (action.kind === "reroll" && !actionTable)
                            }
                        >
                            {pending
                                ? "Saving…"
                                : action.kind === "delete"
                                  ? "Delete"
                                  : "Re-roll"}
                        </Button>
                    </FormActions>
                </Dialog>
            )}
        </div>
    );
}
