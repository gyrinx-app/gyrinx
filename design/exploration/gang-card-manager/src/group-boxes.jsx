import React, { useLayoutEffect, useState } from "react";
import { groupColour } from "./card-manager-model.js";
import { groupBoxShapes } from "./group-box-geometry.js";

export function GroupBoxes({
    saved,
    grid,
    onEditGroup,
    showLabels = true,
    fitMembers = false,
}) {
    const [shapes, setShapes] = useState([]);
    useLayoutEffect(() => {
        const element = grid.current;
        if (!element) return;
        let active = true;
        const measure = () => {
            if (!active) return;
            const cells = [...element.children]
                .filter(
                    (cell) =>
                        cell.matches(".gang-card, .gang-panel-stack") &&
                        cell.getClientRects().length,
                )
                .map((cell) => ({
                    id: (
                        cell.dataset.flip ||
                        cell.querySelector("[data-flip]")?.dataset.flip
                    )?.slice(5),
                    left: cell.offsetLeft,
                    right: cell.offsetLeft + cell.offsetWidth,
                    top: cell.offsetTop,
                    bottom: cell.offsetTop + cell.offsetHeight,
                }));
            const rowTops = [...new Set(cells.map((cell) => cell.top))].sort(
                (a, b) => a - b,
            );
            const rowBottoms = rowTops.map((top) =>
                Math.max(
                    ...cells.filter((c) => c.top === top).map((c) => c.bottom),
                ),
            );
            const card = element.querySelector(".callout-frame");
            const style = card && getComputedStyle(card);
            const bevels = style
                ? {
                      topBevel: parseFloat(style.borderTopRightRadius),
                      bottomBevel: parseFloat(style.borderBottomRightRadius),
                  }
                : {};
            const next = saved
                .filter(
                    (group) => group.children && group.showBox && !group.hidden,
                )
                .flatMap((group) => {
                    const ids = new Set(
                        group.children.map((child) => child.id),
                    );
                    // A pet shares its owner's group and remains its own roster card.
                    const members = cells.filter(
                        (cell) =>
                            ids.has(cell.id) ||
                            ids.has(cell.id?.split("-pet-")[0]),
                    );
                    const rows = rowTops.flatMap((top, row) => {
                        const membersHere = members.filter(
                            (cell) => cell.top === top,
                        );
                        return membersHere.length
                            ? [
                                  {
                                      row,
                                      left:
                                          Math.min(
                                              ...membersHere.map((c) => c.left),
                                          ) - 6,
                                      right:
                                          Math.max(
                                              ...membersHere.map(
                                                  (c) => c.right,
                                              ),
                                          ) + 6,
                                      top: top - 14,
                                      bottom:
                                          (fitMembers
                                              ? Math.max(
                                                    ...membersHere.map(
                                                        (cell) => cell.bottom,
                                                    ),
                                                )
                                              : rowBottoms[row]) + 6,
                                  },
                              ]
                            : [];
                    });
                    return groupBoxShapes(rows, bevels).map((shape, index) => ({
                        ...shape,
                        id: `${group.id}-${index}`,
                        groupId: group.id,
                        colour: group.colour,
                        label: showLabels && index === 0 ? group.name : null,
                    }));
                });
            setShapes((previous) =>
                JSON.stringify(previous) === JSON.stringify(next)
                    ? previous
                    : next,
            );
        };
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(element);
        [...element.children].forEach((cell) => observer.observe(cell));
        document.fonts.ready.then(measure);
        return () => {
            active = false;
            observer.disconnect();
        };
    }, [saved, grid, showLabels, fitMembers]);
    return (
        <div className="gang-group-boxes">
            {shapes.map((shape) => (
                <div
                    key={shape.id}
                    className="gang-group-box"
                    data-roster-group={shape.groupId}
                    data-rows={shape.rows}
                    data-open-left={shape.openLeft}
                    data-open-right={shape.openRight}
                    style={{
                        left: shape.left,
                        top: shape.top,
                        width: shape.width,
                        height: shape.height,
                        "--group-colour": groupColour(shape.colour),
                    }}
                >
                    <svg
                        width={shape.width}
                        height={shape.height}
                        aria-hidden="true"
                    >
                        {shape.colour !== "none" && (
                            <path
                                className="gang-group-box-fill"
                                d={shape.fillPath}
                                fill="currentColor"
                                fillOpacity="0.05"
                            />
                        )}
                        <path
                            className="gang-group-box-outline"
                            d={shape.path}
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1"
                        />
                        {shape.dottedPath && (
                            <path
                                className="gang-group-box-dots"
                                d={shape.dottedPath}
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1"
                                strokeDasharray="1 3"
                                strokeLinecap="round"
                            />
                        )}
                    </svg>
                    {shape.label && (
                        <button
                            type="button"
                            className="gang-group-box-label"
                            aria-label={`Edit group ${shape.label}`}
                            title={shape.label}
                            onClick={() => onEditGroup(shape.groupId)}
                            style={{
                                left: shape.labelLeft + 10,
                                maxWidth: shape.width - shape.labelLeft - 24,
                            }}
                        >
                            {shape.label}
                        </button>
                    )}
                </div>
            ))}
        </div>
    );
}
