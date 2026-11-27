import React, {
    useEffect,
    useId,
    useRef,
    useState,
    useLayoutEffect,
    useMemo,
} from "react";
import { X, ArrowRight } from "lucide-react";
import { Button, Icon } from "./controls.jsx";
import { Entry, TimelineNode } from "./history-entry.jsx";
import { fullDate, localDate, dayName, zone } from "./history-format.js";
import { useHistoryIndexes } from "./history-ui.jsx";
import { graphLayout } from "./history-graph.js";
import * as M from "./history-model.js";
export function BranchTimeline({
    entries,
    root,
    viewer,
    linked,
    ...entryProps
}) {
    const layout = useMemo(() => graphLayout(root, entries), [root, entries]);
    const indexes = useHistoryIndexes(root);
    const [selected, setSelected] = useState(null);
    const panel = useRef(null);
    const pinned = useRef(false);
    const hoverTimer = useRef(null);
    const graphHost = useRef(null);
    const markerId = useId().replace(/:/g, "");
    const [popover, setPopover] = useState(null);
    const [anchor, setAnchor] = useState(null);
    const point = layout.points.find((p) => p.entry.id === selected);
    useEffect(() => {
        if (!linked) return;
        setSelected(null);
        requestAnimationFrame(() =>
            graphHost.current
                ?.querySelector(`[data-node-id="${CSS.escape(linked)}"]`)
                ?.scrollIntoView({ block: "nearest", inline: "center" }),
        );
    }, [linked]);
    useLayoutEffect(() => {
        if (!selected || !panel.current) return;
        function positionCard() {
            const node = anchor?.isConnected
                ? anchor
                : graphHost.current?.querySelector(
                      `[data-node-id="${CSS.escape(selected)}"]`,
                  );
            if (!node) return;
            const box = node.getBoundingClientRect();
            const width = Math.min(360, innerWidth - 32);
            const below = Math.max(0, innerHeight - box.bottom - 16),
                above = Math.max(0, box.top - 16);
            const height = panel.current.scrollHeight;
            const useBelow = below >= height || below >= above;
            const room = useBelow ? below : above;
            const maxHeight = Math.max(48, room);
            setPopover({
                position: "fixed",
                width,
                left: Math.max(16, Math.min(box.left, innerWidth - width - 16)),
                top: useBelow
                    ? box.bottom + 8
                    : Math.max(8, box.top - 8 - Math.min(height, maxHeight)),
                maxHeight,
                overflowY: height > maxHeight ? "auto" : "visible",
            });
        }
        positionCard();
        window.addEventListener("resize", positionCard);
        const scroll = graphHost.current?.querySelector(".graph-scroll");
        scroll?.addEventListener("scroll", positionCard);
        return () => {
            window.removeEventListener("resize", positionCard);
            scroll?.removeEventListener("scroll", positionCard);
        };
    }, [selected, root, anchor]);
    const dates = layout.dates.map((d) => ({ ...d, label: dayName(d.when) }));
    function closeCard() {
        clearTimeout(hoverTimer.current);
        pinned.current = false;
        setSelected(null);
    }
    function keepCard() {
        clearTimeout(hoverTimer.current);
    }
    function leaveCard() {
        clearTimeout(hoverTimer.current);
        if (!pinned.current)
            hoverTimer.current = setTimeout(() => setSelected(null), 140);
    }
    useEffect(() => {
        const outside = (e) => {
            const path = e.composedPath();
            if (
                !path.includes(panel.current) &&
                !path.some((n) => n?.classList?.contains("graph-node"))
            )
                closeCard();
        };
        const escape = (e) => {
            if (e.key === "Escape") closeCard();
        };
        document.addEventListener("pointerdown", outside);
        document.addEventListener("keydown", escape);
        return () => {
            clearTimeout(hoverTimer.current);
            document.removeEventListener("pointerdown", outside);
            document.removeEventListener("keydown", escape);
        };
    }, []);
    function choose(id, event, pin = false) {
        keepCard();
        if (pinned.current && !pin) return;
        pinned.current = pin;
        setSelected(id);
        if (event) {
            setAnchor(event.currentTarget);
        }
    }
    return (
        <section
            ref={graphHost}
            className="branch-timeline"
            aria-label="Timeline"
        >
            <p className="timeline-legend">
                <span>Canonical</span>
                <span className="legend-undone">Undone</span>
                <span className="legend-restore">Restored</span>
            </p>
            <p className="text-sm text-muted">
                Oldest to newest. Hover or select a node to inspect its action.
            </p>
            <div
                className="graph-scroll"
                role="region"
                aria-label="Scrollable gang timeline"
                tabIndex={0}
            >
                <div
                    className="graph-canvas"
                    style={{ width: layout.width, height: layout.height }}
                >
                    <div
                        className="graph-date-axis"
                        aria-label="Timeline dates"
                    >
                        {dates.map((d, i) => (
                            <time
                                key={`${d.label}-${i}`}
                                dateTime={localDate(d.when)}
                                title={d.label}
                                style={{
                                    left: d.x - 12,
                                    top: 0,
                                }}
                            >
                                {new Date(d.when).toLocaleDateString("en-GB", {
                                    ...zone,
                                    day: "numeric",
                                    month: "short",
                                })}
                            </time>
                        ))}
                    </div>
                    <svg
                        className="graph-routes"
                        width={layout.width}
                        height={layout.height}
                        aria-hidden="true"
                    >
                        <defs>
                            <marker
                                id={`${markerId}-return`}
                                viewBox="0 0 10 10"
                                refX="8"
                                refY="5"
                                markerWidth="6"
                                markerHeight="6"
                                orient="auto-start-reverse"
                            >
                                <path
                                    d="M2 1 L8 5 L2 9"
                                    fill="none"
                                    stroke="var(--color-accent)"
                                    strokeWidth="1.5"
                                />
                            </marker>
                        </defs>
                        {dates.slice(1).map((d, i) => (
                            <line
                                key={`date-${i}`}
                                className="graph-date-divider"
                                x1={d.x - 18}
                                x2={d.x - 18}
                                y1={32}
                                y2={layout.height}
                            />
                        ))}
                        {layout.edges.map((edge, i) => {
                            const a = edge.from,
                                b = edge.to,
                                diagonal = Math.min(
                                    64,
                                    Math.max(8, (b.x - a.x) / 2),
                                );
                            const path = edge.undoneRestore
                                ? `M${a.x},${a.y + (b.y > a.y ? 8 : -8)} V${b.y + (b.y > a.y ? -4 : 4)}`
                                : edge.return
                                  ? `M${a.x},${a.y - 8} V${b.y + 3}`
                                  : a.y === b.y
                                    ? `M${a.x},${a.y} H${b.x}`
                                    : `M${a.x},${a.y} L${a.x + diagonal},${b.y} H${b.x}`;
                            return (
                                <path
                                    key={i}
                                    d={path}
                                    markerEnd={
                                        edge.return
                                            ? `url(#${markerId}-return)`
                                            : undefined
                                    }
                                    className={`${edge.inactive ? "route-undone" : ""} ${edge.restore ? "route-restore" : ""} ${edge.return ? "route-return" : ""} ${edge.undoneRestore ? "route-restore-undone" : ""}`}
                                />
                            );
                        })}
                    </svg>
                    {[...layout.points, ...layout.junctions].map((p) => {
                        const state = M.historyFor(root, p.entry.gang);
                        const marked =
                            state && M.isHighlighted(state, p.entry.id, viewer);
                        return (
                            <button
                                key={`${p.entry.id}-${p.junction ? "junction" : "action"}`}
                                type="button"
                                data-node-id={
                                    p.junction ? undefined : p.entry.id
                                }
                                data-junction-id={
                                    p.junction ? p.entry.id : undefined
                                }
                                className={`graph-node ${p.junction ? "graph-junction-node" : ""} ${p.inactive ? "graph-undone" : ""} ${p.entry.type === "restore" ? "graph-restore" : ""} ${selected === p.entry.id || linked === p.entry.id ? "graph-selected" : ""}`}
                                style={{ left: p.x - 14, top: p.y - 14 }}
                                aria-label={`${p.junction ? (p.inactive ? "Undone restore: " : "Canonical restore: ") : ""}${p.entry.description} ${fullDate(p.entry.when)}`}
                                aria-expanded={selected === p.entry.id}
                                aria-controls="timeline-action-detail"
                                onMouseEnter={(e) => choose(p.entry.id, e)}
                                onMouseLeave={leaveCard}
                                onFocus={(e) => choose(p.entry.id, e, true)}
                                onClick={(e) => choose(p.entry.id, e, true)}
                                onKeyDown={(e) => {
                                    if (e.key === "Escape") closeCard();
                                    if (e.key === "ArrowDown") {
                                        e.preventDefault();
                                        panel.current
                                            ?.querySelector("summary,a,button")
                                            ?.focus();
                                    }
                                }}
                            >
                                <TimelineNode
                                    restore={
                                        p.entry.type === "restore" &&
                                        !p.junction
                                    }
                                    highlighted={marked}
                                />
                            </button>
                        );
                    })}
                </div>
            </div>
            {point && (
                <div
                    ref={panel}
                    id="timeline-action-detail"
                    role="region"
                    aria-label="Action details"
                    style={popover}
                    className="graph-detail"
                    onMouseEnter={keepCard}
                    onMouseLeave={leaveCard}
                    onPointerDown={() => {
                        pinned.current = true;
                        keepCard();
                    }}
                    onKeyDown={(e) => {
                        if (e.key === "Escape") closeCard();
                    }}
                >
                    <div className="graph-detail-heading">
                        <time dateTime={point.entry.when}>
                            {fullDate(point.entry.when)}
                        </time>
                        <Button
                            variant="ghost"
                            aria-label="Close action details"
                            icon={X}
                            onClick={closeCard}
                        />
                    </div>
                    <ol>
                        <Entry
                            entry={point.entry}
                            historyIndex={indexes.get(point.entry.gang)}
                            floatingMenu
                            root={root}
                            viewer={viewer}
                            {...entryProps}
                            targeted={linked === point.entry.id}
                        />
                    </ol>
                </div>
            )}
            {!entries.length && <p>No activity matches these filters.</p>}
        </section>
    );
}
export function Timeline({ shown, root, linked, ...entryProps }) {
    const indexes = useHistoryIndexes(root);
    const [focus, setFocus] = useState(null);
    const ref = useRef(null);
    const [rails, setRails] = useState([]);
    const trees = useMemo(
        () =>
            [root, ...Object.values(root.otherHistories || {})].flatMap(
                M.timelineGroups,
            ),
        [root],
    );
    const nodes = new Map();
    function index(groups, path = []) {
        for (const group of groups) {
            nodes.set(group.id, { group, path });
            index(group.children, [...path, group.id]);
        }
    }
    index(trees);
    const selected = nodes.get(focus);
    const branches = selected ? selected.group.children : trees;
    const baseIds = selected ? new Set(selected.group.ids) : null;
    const placement = new Map();
    const placeholders = new Map();
    function descendants(g) {
        return [...g.ids, ...g.children.flatMap(descendants)];
    }
    const levels = new Map();
    function place(groups, level) {
        for (const g of groups) {
            for (const id of g.ids) {
                placement.set(id, g.id);
                levels.set(id, level);
            }
            if (level < 2) place(g.children, level + 1);
            else
                for (const child of g.children) {
                    const ids = descendants(child);
                    const first = shown.find((e) => ids.includes(e.id));
                    if (first)
                        placeholders.set(first.id, {
                            child,
                            parent: g,
                            count: ids.length,
                            level,
                        });
                    for (const id of ids) placement.set(id, "hidden");
                }
        }
    }
    place(branches, 1);
    const rows = shown.filter(
        (e) =>
            placeholders.has(e.id) ||
            (placement.get(e.id) !== "hidden" &&
                (!baseIds || baseIds.has(e.id) || placement.has(e.id))),
    );
    const latest = rows.find(
        (e) => !placement.has(e.id) && !placeholders.has(e.id),
    )?.id;
    const days = groupDays(rows);
    function navigate(id) {
        const el = ref.current;
        if (el && !matchMedia("(prefers-reduced-motion: reduce)").matches)
            el.animate(
                [
                    { opacity: 0.3, transform: "translateX(32px)" },
                    { opacity: 1, transform: "translateX(0)" },
                ],
                { duration: 240, easing: "ease-out" },
            );
        setFocus(id);
    }
    useEffect(() => {
        if (!linked) return;
        const containing = [...nodes.values()].find(({ group }) =>
            group.ids.includes(linked),
        );
        setFocus(containing?.path.at(-1) || null);
    }, [linked]);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        function measure() {
            const box = el.getBoundingClientRect();
            const items = [...el.querySelectorAll("[data-lane]")];
            const lanes = [...new Set(items.map((e) => e.dataset.lane))];
            const result = [];
            const full = M.entries(root, true);
            const order = new Map(full.map((e, i) => [e.id, i]));
            const activeRestores = [
                root,
                ...Object.values(root.otherHistories || {}),
            ].flatMap((s) =>
                s.versions.filter(
                    (e) =>
                        e.type === "restore" &&
                        indexes.get(s.gangId).active.has(e.id),
                ),
            );
            for (const lane of lanes) {
                const entries = items.filter((e) => e.dataset.lane === lane);
                const first = entries[0].getBoundingClientRect(),
                    last = entries.at(-1).getBoundingClientRect();
                const lastElement = entries.at(-1);
                const noteElement = lastElement.querySelector(".undone-note");
                const note = noteElement?.getBoundingClientRect();
                const noteMiddle = note
                    ? note.top +
                      Math.min(
                          note.height,
                          parseFloat(
                              getComputedStyle(noteElement).lineHeight,
                          ) || note.height,
                      ) /
                          2
                    : null;
                result.push({
                    lane,
                    x: first.left - box.left - 7,
                    inactive: entries.every(
                        (e) =>
                            e.classList.contains("undone") ||
                            e.classList.contains("nested-branch"),
                    ),
                    top: first.top - box.top + 18,
                    bottom: note
                        ? noteMiddle - box.top
                        : last.bottom - box.top - 0.5,
                    restores:
                        lane === "canonical" &&
                        entries.some((e) => !e.classList.contains("undone"))
                            ? activeRestores.flatMap((action) => {
                                  const start = order.get(action.id),
                                      end = order.get(action.restoreTarget);
                                  const span = entries.filter((e) => {
                                      const row =
                                          full[order.get(e.dataset.entryId)];
                                      const index = order.get(
                                          e.dataset.entryId,
                                      );
                                      return (
                                          row?.gang === action.gang &&
                                          index >= start &&
                                          index <= end
                                      );
                                  });
                                  if (!span.length) return [];
                                  const first = span[0].getBoundingClientRect(),
                                      last = span
                                          .at(-1)
                                          .getBoundingClientRect();
                                  return [
                                      {
                                          top:
                                              span[0].dataset.entryId ===
                                              action.id
                                                  ? first.top - box.top + 18
                                                  : first.top - box.top,
                                          bottom:
                                              span.at(-1).dataset.entryId ===
                                              action.restoreTarget
                                                  ? last.top - box.top + 18
                                                  : last.bottom - box.top,
                                      },
                                  ];
                              })
                            : entries
                                  .filter((e) =>
                                      e.classList.contains("restoration"),
                                  )
                                  .map((e) => {
                                      const r = e.getBoundingClientRect();
                                      return {
                                          top: r.top - box.top + 18,
                                          bottom:
                                              e === lastElement && note
                                                  ? noteMiddle - box.top
                                                  : r.bottom - box.top,
                                      };
                                  }),
                });
            }
            setRails(result);
            if (linked)
                el.querySelector(
                    `[id="entry-${CSS.escape(linked)}"]`,
                )?.scrollIntoView({
                    block: "center",
                });
        }
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(el);
        return () => observer.disconnect();
    }, [shown.map((e) => e.id).join(","), focus, linked, root]);
    const depth = selected ? selected.path.length + 1 : 0;
    return (
        <>
            {selected && (
                <div className="timeline-navigation">
                    <Button
                        onClick={() => navigate(selected.path.at(-1) || null)}
                    >
                        Back
                    </Button>
                    <Button onClick={() => navigate(null)}>
                        Full timeline
                    </Button>
                    <span>Undone timeline · depth {depth}</span>
                </div>
            )}
            <div
                ref={ref}
                className="history-timeline"
                style={{ "--ancestor-space": `${Math.min(depth, 3) * 7}px` }}
            >
                <div className="timeline-rails" aria-hidden="true">
                    {Array.from({ length: Math.min(depth, 3) }, (_, i) => (
                        <i
                            key={`ancestor-${i}`}
                            className={`timeline-rail ancestor ${i > 0 ? "inactive" : ""}`}
                            style={{ left: i * 7, top: 0, bottom: 0 }}
                        />
                    ))}
                    {rails.map((r) => (
                        <i
                            key={r.lane}
                            className={`timeline-rail ${r.lane === "canonical" ? "canonical" : "branch"} ${r.inactive ? "inactive" : ""}`}
                            style={{
                                left: r.x,
                                top: r.top,
                                height: r.bottom - r.top,
                            }}
                        >
                            {r.inactive && <span className="undo-terminal" />}
                        </i>
                    ))}
                    {rails.flatMap((r) =>
                        r.restores.map((segment, i) => (
                            <i
                                key={`${r.lane}-restore-${i}`}
                                className={`timeline-rail restore-rail ${r.inactive ? "inactive" : ""}`}
                                style={{
                                    left: r.x,
                                    top: segment.top,
                                    height: segment.bottom - segment.top,
                                }}
                            />
                        )),
                    )}
                </div>
                {depth > 3 && (
                    <span
                        className="timeline-truncated"
                        title={`${depth - 3} earlier timeline lines hidden`}
                    >
                        …{" "}
                        <span className="sr-only">
                            {depth - 3} earlier timeline lines hidden
                        </span>
                    </span>
                )}
                {days.map((day) => (
                    <section className="history-day" key={day.label}>
                        <h2>{day.label}</h2>
                        <ol>
                            {day.entries.map((e) => {
                                const placeholder = placeholders.get(e.id);
                                if (placeholder)
                                    return (
                                        <li
                                            key={e.id}
                                            className="history-entry nested-branch"
                                            data-lane={placeholder.parent.id}
                                            data-level={placeholder.level}
                                            style={{
                                                "--lane-level":
                                                    placeholder.level,
                                            }}
                                        >
                                            <TimelineNode />
                                            <button
                                                onClick={() =>
                                                    navigate(
                                                        placeholder.parent.id,
                                                    )
                                                }
                                            >
                                                {placeholder.count} nested
                                                undone items{" "}
                                                <Icon
                                                    icon={ArrowRight}
                                                    size={14}
                                                />
                                            </button>
                                        </li>
                                    );
                                return (
                                    <Entry
                                        key={e.id}
                                        entry={e}
                                        historyIndex={indexes.get(e.gang)}
                                        root={root}
                                        {...entryProps}
                                        targeted={linked === e.id}
                                        lane={
                                            placement.get(e.id) || "canonical"
                                        }
                                        level={levels.get(e.id) || 0}
                                        latest={latest === e.id}
                                    />
                                );
                            })}
                        </ol>
                    </section>
                ))}
                {!rows.length && (
                    <p className="text-sm text-muted">
                        No activity matches these filters.
                    </p>
                )}
            </div>
        </>
    );
}

function groupDays(entries) {
    const days = [];
    for (const entry of entries) {
        const label = dayName(entry.when);
        if (days.at(-1)?.label !== label) days.push({ label, entries: [] });
        days.at(-1).entries.push(entry);
    }
    return days;
}

export function CampaignHistory({ entries, root, linked, ...entryProps }) {
    const indexes = useHistoryIndexes(root);
    return (
        <div className="history-timeline campaign-history">
            {groupDays(entries).map((day) => (
                <section className="history-day" key={day.label}>
                    <h2>{day.label}</h2>
                    <ol>
                        {day.entries.map((entry) => (
                            <Entry
                                key={entry.id}
                                entry={entry}
                                root={root}
                                historyIndex={indexes.get(entry.gang)}
                                targeted={linked === entry.id}
                                flat
                                {...entryProps}
                            />
                        ))}
                    </ol>
                </section>
            ))}
            {!entries.length && (
                <p className="text-sm text-muted">
                    No activity matches these filters.
                </p>
            )}
        </div>
    );
}
