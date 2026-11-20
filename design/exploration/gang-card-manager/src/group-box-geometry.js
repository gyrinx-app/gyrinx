// Rows use layout coordinates so hover and reorder transforms cannot bend the outline.
export function groupBoxShapes(rows, { topBevel = 8, bottomBevel = 16 } = {}) {
    const components = [];
    for (const row of rows) {
        const current = components.at(-1);
        const previous = current?.at(-1);
        if (
            previous &&
            row.row === previous.row + 1 &&
            Math.min(previous.right, row.right) >
                Math.max(previous.left, row.left)
        ) {
            current.push(row);
        } else components.push([row]);
    }
    return components.map((component, index) => {
        const first = component[0],
            last = component.at(-1);
        const openLeft = index > 0,
            openRight = index < components.length - 1;
        const points = [
            { x: first.left, y: first.top, side: "top" },
            { x: first.right, y: first.top, side: "right" },
        ];
        for (let i = 0; i < component.length - 1; i++) {
            const a = component[i],
                b = component[i + 1];
            if (a.right === b.right) continue;
            const join = a.right > b.right ? a.bottom : b.top;
            points.push(
                { x: a.right, y: join, side: "right" },
                { x: b.right, y: join, side: "right" },
            );
        }
        points.push(
            { x: last.right, y: last.bottom, side: "bottom" },
            { x: last.left, y: last.bottom, side: "left" },
        );
        for (let i = component.length - 1; i > 0; i--) {
            const a = component[i],
                b = component[i - 1];
            if (a.left === b.left) continue;
            const join = a.left < b.left ? a.top : b.bottom;
            points.push(
                { x: a.left, y: join, side: "left" },
                { x: b.left, y: join, side: "left" },
            );
        }
        const enabled = (side) =>
            !((side === "left" && openLeft) || (side === "right" && openRight));
        const left = Math.min(...component.map((r) => r.left)) - 0.5;
        const top = first.top - 0.5;
        const width = Math.max(...component.map((r) => r.right)) - left + 0.5;
        const height = last.bottom - top + 0.5;
        const corners = points.map((point, i) => {
            const prev = points[(i + points.length - 1) % points.length];
            const next = points[(i + 1) % points.length];
            const dx = point.x - prev.x,
                dy = point.y - prev.y;
            const nx = next.x - point.x,
                ny = next.y - point.y;
            const incoming = Math.hypot(dx, dy),
                outgoing = Math.hypot(nx, ny);
            const bevel =
                enabled(prev.side) && enabled(point.side)
                    ? Math.min(
                          dx > 0 && ny > 0
                              ? topBevel
                              : dy > 0 && nx < 0
                                ? bottomBevel
                                : 0,
                          incoming / 2,
                          outgoing / 2,
                      )
                    : 0;
            return {
                start: [
                    point.x - left - (dx / incoming) * bevel,
                    point.y - top - (dy / incoming) * bevel,
                ],
                end: [
                    point.x - left + (nx / outgoing) * bevel,
                    point.y - top + (ny / outgoing) * bevel,
                ],
            };
        });
        const dotted = [];
        const path = points
            .flatMap((point, i) => {
                if (!enabled(point.side)) return [];
                const start = corners[i].end;
                const next = corners[(i + 1) % corners.length];
                const finish = next.start;
                const length = Math.hypot(
                    finish[0] - start[0],
                    finish[1] - start[1],
                );
                const horizontal =
                    point.side === "top" || point.side === "bottom";
                const dottedStart =
                    horizontal && (point.side === "top" ? openLeft : openRight);
                const dottedEnd =
                    horizontal && (point.side === "top" ? openRight : openLeft);
                const extent = Math.min(24, length / 3);
                const along = (distance) =>
                    start.map(
                        (value, axis) =>
                            value +
                            ((finish[axis] - value) * distance) / length,
                    );
                const solidStart = dottedStart ? along(extent) : start;
                const solidEnd = dottedEnd ? along(length - extent) : finish;
                if (dottedStart)
                    dotted.push(
                        `M ${start.join(" ")} L ${solidStart.join(" ")}`,
                    );
                if (dottedEnd)
                    dotted.push(
                        `M ${solidEnd.join(" ")} L ${finish.join(" ")}`,
                    );
                return [
                    `M ${solidStart.join(" ")} L ${solidEnd.join(" ")}${dottedEnd ? "" : ` L ${next.end.join(" ")}`}`,
                ];
            })
            .join(" ");
        const fillPath =
            corners
                .map(
                    (corner, i) =>
                        `${i === 0 ? "M" : "L"} ${corner.start.join(" ")} L ${corner.end.join(" ")}`,
                )
                .join(" ") + " Z";
        return {
            fillPath,
            dottedPath: dotted.join(" "),
            left,
            top,
            width,
            height,
            path,
            openLeft,
            openRight,
            labelLeft: first.left - left,
            rows: component.length,
        };
    });
}
