import * as M from "./history-model.js";
import { localDate } from "./history-format.js";

// Reserve horizontal intervals, rather than entire lanes, so separated routes
// can share a row without overlapping nodes or their connecting segments.
export function graphLayout(root, entries) {
    const chronological = [...entries].reverse();
    const rank = new Map(chronological.map((e, i) => [e.id, i]));
    const points = new Map(),
        junctions = new Map(),
        edges = [];
    let nextBand = 0;
    const columns = new Map(),
        dates = [];
    let cursor = 40,
        dayStart = 40,
        previousDay = null;
    for (const entry of chronological) {
        const day = localDate(entry.when);
        if (day !== previousDay) {
            if (previousDay) cursor = Math.max(cursor, dayStart + 112);
            dayStart = cursor;
            dates.push({ when: entry.when, x: cursor });
            previousDay = day;
        }
        columns.set(entry.id, cursor);
        cursor += 48;
    }
    const x = (id) => columns.get(id);
    for (const state of [root, ...Object.values(root.otherHistories || {})]) {
        const own = chronological.filter((e) => e.gang === state.gangId);
        if (!own.length) continue;
        const mainY = 72 + nextBand * 64;
        const occupied = [];
        function reserve(start, end) {
            start = Number.isFinite(start) ? start : Math.max(0, end - 1);
            let lane = occupied.findIndex((intervals) =>
                intervals.every(([a, b]) => end < a || start > b),
            );
            if (lane < 0) {
                lane = occupied.length;
                occupied.push([]);
            }
            occupied[lane].push([start, end]);
            return mainY + (lane + 1) * 64;
        }
        const active = M.ancestry(state);
        const restoreLanes = new Map();
        function place(groups) {
            for (const group of groups) {
                const actions = own.filter((e) => group.ids.includes(e.id));
                if (!actions.length) {
                    place(group.children);
                    continue;
                }
                const closing = own.find(
                    (e) =>
                        e.type === "restore" &&
                        (e.id === group.id ||
                            (e.restoreTarget === group.anchor &&
                                group.ids.includes(e.parent))),
                );
                const end = Math.max(
                    ...actions.map((e) => rank.get(e.id)),
                    closing ? rank.get(closing.id) : -1,
                );
                const y = reserve(rank.get(group.anchor), end);
                if (closing) restoreLanes.set(closing.id, y);
                for (const entry of actions)
                    points.set(entry.id, {
                        entry,
                        x: x(entry.id),
                        y,
                        inactive: true,
                    });
                place(group.children);
            }
        }
        place(M.timelineGroups(state));
        for (const entry of own.filter((e) => active.has(e.id))) {
            if (entry.type === "restore")
                junctions.set(entry.id, {
                    entry,
                    x: x(entry.id),
                    y: mainY,
                    junction: true,
                });
            else
                points.set(entry.id, {
                    entry,
                    x: x(entry.id),
                    y: mainY,
                    inactive: false,
                });
        }
        for (const entry of own.filter((e) => e.type === "restore")) {
            const parent = points.get(entry.parent);
            const y =
                restoreLanes.get(entry.id) ||
                (parent?.y > mainY
                    ? parent.y
                    : reserve(
                          rank.get(entry.restoreTarget),
                          rank.get(entry.id),
                      ));
            points.set(entry.id, {
                entry,
                x: x(entry.id),
                y,
                inactive: !active.has(entry.id),
            });
            if (!junctions.has(entry.id))
                junctions.set(entry.id, {
                    entry,
                    x: x(entry.id),
                    y: mainY,
                    junction: true,
                });
        }
        // A cancelled restore no longer rejoins canonical history. Its former
        // junction follows the abandoned continuation, or gets its own free lane.
        for (const entry of own.filter(
            (e) => e.type === "restore" && !active.has(e.id),
        )) {
            const symbol = points.get(entry.id);
            const continuation = own.find(
                (e) =>
                    e.parent === entry.id &&
                    e.type !== "restore" &&
                    points.get(e.id)?.inactive &&
                    points.get(e.id).y !== symbol.y,
            );
            const junction = junctions.get(entry.id);
            junction.y = continuation
                ? points.get(continuation.id).y
                : reserve(rank.get(entry.id), rank.get(entry.id));
            junction.inactive = true;
        }
        // Keep non-snapshot records inspectable on the primary line.
        for (const entry of own)
            if (!points.has(entry.id))
                points.set(entry.id, {
                    entry,
                    x: x(entry.id),
                    y: mainY,
                    inactive: false,
                });
        let previous = null;
        for (const entry of own.filter(
            (e) =>
                active.has(e.id) ||
                (e.type !== "restore" && !points.get(e.id)?.inactive),
        )) {
            const destination =
                entry.type === "restore"
                    ? junctions.get(entry.id)
                    : points.get(entry.id);
            if (previous)
                edges.push({
                    from: previous,
                    to: destination,
                    inactive: false,
                });
            previous = destination;
        }
        const latestX = Math.max(...own.map((e) => x(e.id)));
        if (previous && latestX > previous.x)
            edges.push({
                from: previous,
                to: { ...previous, x: latestX },
                inactive: false,
            });
        for (const entry of own) {
            const point = points.get(entry.id);
            if (entry.type === "restore") {
                const parent =
                    junctions.get(entry.parent) ||
                    points.get(entry.parent) ||
                    points.get(entry.restoreTarget) ||
                    junctions.get(entry.restoreTarget);
                if (parent)
                    edges.push({
                        from: parent,
                        to: point,
                        restore: true,
                        inactive: point.inactive,
                    });
                if (point.inactive)
                    edges.push({
                        from: point,
                        to: junctions.get(entry.id),
                        restore: true,
                        inactive: true,
                        undoneRestore: true,
                    });
                else
                    edges.push({
                        from: point,
                        to: junctions.get(entry.id),
                        restore: true,
                        return: true,
                        inactive: false,
                    });
            } else if (point.inactive) {
                const parent =
                    junctions.get(entry.parent) || points.get(entry.parent);
                if (parent)
                    edges.push({ from: parent, to: point, inactive: true });
            }
        }
        nextBand += occupied.length + 2;
    }
    const extras = chronological.filter((e) => !points.has(e.id));
    let previous = null;
    for (const entry of extras) {
        const point = {
            entry,
            x: x(entry.id),
            y: 72 + nextBand * 64,
            inactive: false,
        };
        points.set(entry.id, point);
        if (previous)
            edges.push({ from: previous, to: point, inactive: false });
        previous = point;
    }
    const all = [...points.values(), ...junctions.values()];
    return {
        points: [...points.values()],
        junctions: [...junctions.values()],
        edges,
        dates,
        width: Math.max(560, cursor + 40),
        height: Math.max(220, ...all.map((p) => p.y + 72)),
    };
}
