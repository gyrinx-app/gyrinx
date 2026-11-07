import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import cotton from "../generated/cotton.json";
import { useAnchoredPlacement, useDismiss } from "./anchoredPanel";
import { Glyph } from "./glyph";
import { HelpPopover } from "./HelpPopover";
import { Tooltip } from "./Tooltip";

export type GangFiguresData = {
    items: Array<{
        short: string;
        label: string;
        value: string;
        absent: string;
        href: string;
    }>;
    roster: {
        count: number;
        rating: number;
        groups: Array<{ profile: string; category: string; count: number }>;
        models: Array<{ name: string; rating: number }>;
    };
};

function RosterBreakdown({ roster }: { roster: GangFiguresData["roster"] }) {
    const recipe = cotton.gangFigures;
    const id = useId();
    const root = useRef<HTMLSpanElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const tabs = useRef<Array<HTMLButtonElement | null>>([]);
    const focusRequested = useRef(false);
    const [open, setOpen] = useState(false);
    const [tab, setTab] = useState(0);
    useDismiss(root, trigger, open, () => setOpen(false));
    const style = useAnchoredPlacement({
        open,
        trigger,
        panel,
        width: "content",
        minWidth: "18rem",
        gap: 4,
        clampHeight: true,
    });
    useEffect(() => {
        if (open && focusRequested.current) {
            tabs.current[tab]?.focus();
            focusRequested.current = false;
        }
    }, [open, tab]);

    function changeTab(event: KeyboardEvent<HTMLButtonElement>) {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        let next: number;
        if (event.key === "ArrowRight" || event.key === "ArrowLeft")
            next = 1 - tab;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = 1;
        else return;
        event.preventDefault();
        setTab(next);
        tabs.current[next]?.focus();
    }
    const label = `Roster breakdown: ${roster.count} ${roster.count === 1 ? "model" : "models"} in the gang`;
    return (
        <span ref={root} className="shrink-0">
            <Tooltip label="Models in the gang">
                <button
                    ref={trigger}
                    type="button"
                    className={cotton.buttonSmall.default}
                    aria-label={label}
                    aria-haspopup="dialog"
                    aria-expanded={open}
                    aria-controls={open ? id : undefined}
                    onKeyDown={(event) => {
                        if (event.altKey || event.ctrlKey || event.metaKey)
                            return;
                        if (
                            event.key === "ArrowDown" ||
                            event.key === "ArrowUp"
                        ) {
                            event.preventDefault();
                            focusRequested.current = true;
                            setOpen(true);
                            if (open) tabs.current[tab]?.focus();
                        }
                    }}
                    onClick={(event) => {
                        focusRequested.current = event.detail === 0;
                        setOpen(!open);
                    }}
                >
                    <span className="flex items-center gap-1">
                        <Glyph
                            name="users"
                            className="size-4.5"
                            strokeWidth={1.4}
                        />
                        <span className="tabular-nums">{roster.count}</span>
                        <Glyph
                            name="chevron-down"
                            className="size-3"
                            strokeWidth={2.5}
                        />
                    </span>
                </button>
            </Tooltip>
            {open && (
                <div
                    ref={panel}
                    id={id}
                    role="dialog"
                    aria-label="Roster breakdown"
                    className={`${cotton.actionMenu.panel} fixed`}
                    style={style}
                >
                    <div className={recipe.rosterBody}>
                        <div
                            className={recipe.tabList}
                            role="tablist"
                            aria-label="Roster breakdown"
                        >
                            {["Profiles", "Ratings"].map((name, index) => (
                                <button
                                    key={name}
                                    ref={(node) => {
                                        tabs.current[index] = node;
                                    }}
                                    type="button"
                                    role="tab"
                                    id={`${id}-tab-${index}`}
                                    aria-selected={tab === index}
                                    aria-controls={`${id}-panel`}
                                    tabIndex={tab === index ? 0 : -1}
                                    className={`${recipe.tab} ${tab === index ? recipe.tabActive : recipe.tabInactive}`}
                                    onClick={() => setTab(index)}
                                    onKeyDown={changeTab}
                                >
                                    {name}
                                </button>
                            ))}
                        </div>
                        <div
                            id={`${id}-panel`}
                            role="tabpanel"
                            tabIndex={0}
                            aria-labelledby={`${id}-tab-${tab}`}
                            className={`${recipe.tabPanel} focus-ring`}
                        >
                            <table className={recipe.table}>
                                <caption className="sr-only">
                                    {tab === 0
                                        ? "Models by profile"
                                        : "Model ratings"}
                                </caption>
                                <thead className="sr-only">
                                    <tr>
                                        {(tab === 0
                                            ? ["Profile", "Rank", "Models"]
                                            : ["Model", "Rating"]
                                        ).map((name) => (
                                            <th key={name} scope="col">
                                                {name}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {tab === 0
                                        ? roster.groups.map((group, index) => (
                                              <tr key={index}>
                                                  <td className={recipe.name}>
                                                      {group.profile}
                                                  </td>
                                                  <td
                                                      className={
                                                          recipe.category
                                                      }
                                                  >
                                                      {group.category}
                                                  </td>
                                                  <td className={recipe.number}>
                                                      {group.count}
                                                  </td>
                                              </tr>
                                          ))
                                        : roster.models.map((model, index) => (
                                              <tr key={index}>
                                                  <td className={recipe.name}>
                                                      {model.name}
                                                  </td>
                                                  <td className={recipe.number}>
                                                      {model.rating}¢
                                                  </td>
                                              </tr>
                                          ))}
                                </tbody>
                                <tfoot>
                                    <tr className={recipe.totalRow}>
                                        <td
                                            className={recipe.totalLabel}
                                            colSpan={tab === 0 ? 2 : 1}
                                        >
                                            Total
                                        </td>
                                        <td className={recipe.totalNumber}>
                                            {tab === 0
                                                ? roster.count
                                                : `${roster.rating}¢`}
                                        </td>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>
                    </div>
                </div>
            )}
        </span>
    );
}

export function GangFigures({ data }: { data: GangFiguresData }) {
    const recipe = cotton.gangFigures;
    return (
        <div className={recipe.root}>
            <RosterBreakdown roster={data.roster} />
            <div className={`${recipe.wealth} min-w-0`}>
                <div className={recipe.scroll}>
                    <dl
                        className={recipe.list}
                        aria-label="Gang figures"
                        aria-live="polite"
                        aria-atomic="true"
                    >
                        {data.items.map((item, index) => (
                            <div
                                key={item.short}
                                className={
                                    index === 0
                                        ? recipe.firstFigure
                                        : recipe.figure
                                }
                            >
                                <dt className={recipe.label}>
                                    <HelpPopover
                                        label={item.label}
                                        triggerContent={item.short}
                                    >
                                        <p>{item.label}</p>
                                        {item.absent && <p>{item.absent}</p>}
                                    </HelpPopover>
                                </dt>
                                <dd
                                    className={
                                        item.absent
                                            ? recipe.absent
                                            : recipe.value
                                    }
                                >
                                    {item.href ? (
                                        <a
                                            href={item.href}
                                            className={cotton.linkCurrent[0]}
                                            aria-label={
                                                item.absent || undefined
                                            }
                                        >
                                            <span
                                                className={
                                                    cotton.linkCurrent[1]
                                                }
                                            >
                                                {item.value}
                                            </span>
                                        </a>
                                    ) : (
                                        item.value
                                    )}
                                </dd>
                            </div>
                        ))}
                    </dl>
                </div>
            </div>
        </div>
    );
}
