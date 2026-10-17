import { Fragment, type ReactNode } from "react";
import cotton from "../generated/cotton.json";
import { ColorSwatch, Icon, NativeSelect, Table } from "./index";

export type TableView = { sort: string; group: string };
export type TableColumn = {
    token: string;
    label: string;
    className?: string;
    sortable?: boolean;
    hiddenLabel?: boolean;
};
export type TableGroup<Row> = {
    id: string;
    label: string;
    colour?: string;
    countLabel?: string;
    rows: Row[];
};

/** Controlled table presentation; callers prepare rows, order, groups and URLs. */
export function SortableTable<Row>({
    id,
    label,
    view,
    columns,
    sortOptions = columns.filter((column) => column.sortable !== false),
    groupOptions = [],
    groups,
    onViewChange,
    viewHref,
    renderRows,
    disabled = false,
    mobileCards = false,
    error = "",
    empty = "No entries yet.",
}: {
    id: string;
    label: string;
    view: TableView;
    columns: TableColumn[];
    sortOptions?: TableColumn[];
    groupOptions?: { token: string; label: string }[];
    groups: TableGroup<Row>[];
    onViewChange: (view: TableView) => void;
    viewHref: (view: TableView) => string;
    renderRows: (rows: Row[], groupId?: string) => ReactNode;
    disabled?: boolean;
    mobileCards?: boolean;
    error?: string;
    empty?: string;
}) {
    const groupRecipe = mobileCards
        ? cotton.sortableGroup.mobile
        : cotton.sortableGroup.default;
    const grouped = groupOptions.find((option) => option.token === view.group);
    const sorted = sortOptions.find(
        (option) => option.token === view.sort.replace(/^-/, ""),
    );
    return (
        <div role="region" aria-label={label}>
            <div className="flex flex-wrap items-end gap-3 border-b border-box-border px-4 py-3">
                <label className="flex min-w-0 max-w-full flex-col gap-1 text-xs text-muted">
                    Sort by
                    <NativeSelect
                        controlSize="sm"
                        disabled={disabled}
                        value={view.sort}
                        onChange={(event) =>
                            onViewChange({ ...view, sort: event.target.value })
                        }
                    >
                        {sortOptions.flatMap((column) => [
                            <option key={column.token} value={column.token}>
                                {column.label} (ascending)
                            </option>,
                            <option
                                key={`-${column.token}`}
                                value={`-${column.token}`}
                            >
                                {column.label} (descending)
                            </option>,
                        ])}
                    </NativeSelect>
                </label>
                {groupOptions.length > 0 && (
                    <label className="flex min-w-0 max-w-full flex-col gap-1 text-xs text-muted">
                        View groups by
                        <NativeSelect
                            controlSize="sm"
                            disabled={disabled}
                            value={view.group}
                            onChange={(event) =>
                                onViewChange({
                                    ...view,
                                    group: event.target.value,
                                })
                            }
                        >
                            <option value="">No grouping</option>
                            {groupOptions.map((option) => (
                                <option key={option.token} value={option.token}>
                                    {option.label}
                                </option>
                            ))}
                        </NativeSelect>
                    </label>
                )}
            </div>
            {error && (
                <p
                    role="alert"
                    className="px-4 py-3 text-sm text-red-600 dark:text-red-400"
                >
                    {error}
                </p>
            )}
            {groups.some((group) => group.rows.length) ? (
                <Table className={mobileCards ? "max-md:block" : ""}>
                    <thead className={mobileCards ? "max-md:hidden" : ""}>
                        <tr>
                            {columns.map((column, index) => {
                                const selected =
                                    view.sort.replace(/^-/, "") ===
                                    column.token;
                                const descending =
                                    selected && view.sort.startsWith("-");
                                const next = {
                                    ...view,
                                    sort:
                                        view.sort === column.token
                                            ? `-${column.token}`
                                            : column.token,
                                };
                                return (
                                    <th
                                        key={column.token}
                                        id={`${id}-col-${column.token === "actions" ? "actions" : index}`}
                                        scope="col"
                                        className={
                                            column.hiddenLabel
                                                ? `relative ${column.className ?? ""}`
                                                : column.className
                                        }
                                        aria-sort={
                                            column.sortable === false
                                                ? undefined
                                                : selected
                                                  ? descending
                                                      ? "descending"
                                                      : "ascending"
                                                  : "none"
                                        }
                                    >
                                        {column.sortable === false ? (
                                            <span
                                                className={
                                                    column.hiddenLabel
                                                        ? "sr-only"
                                                        : ""
                                                }
                                            >
                                                {column.label}
                                            </span>
                                        ) : (
                                            <a
                                                href={viewHref(next)}
                                                className="inline-flex items-center gap-1 text-current focus-ring"
                                                aria-disabled={disabled}
                                                onClick={(event) => {
                                                    if (
                                                        event.button === 0 &&
                                                        !event.metaKey &&
                                                        !event.ctrlKey &&
                                                        !event.shiftKey &&
                                                        !event.altKey
                                                    ) {
                                                        event.preventDefault();
                                                        if (!disabled)
                                                            onViewChange(next);
                                                    }
                                                }}
                                            >
                                                {column.label}
                                                {selected && (
                                                    <Icon
                                                        name={
                                                            descending
                                                                ? "arrow-down"
                                                                : "arrow-up"
                                                        }
                                                        className="size-3"
                                                    />
                                                )}
                                            </a>
                                        )}
                                    </th>
                                );
                            })}
                        </tr>
                    </thead>
                    {groups.map((group) => {
                        const groupId = `${id}-group-${encodeURIComponent(group.id)}`;
                        return (
                            <Fragment key={group.id}>
                                {group.label && (
                                    <tbody className={groupRecipe[0]}>
                                        <tr className={groupRecipe[1]}>
                                            <th
                                                id={groupId}
                                                colSpan={columns.length}
                                                scope="rowgroup"
                                                className={groupRecipe[2]}
                                                style={
                                                    group.colour
                                                        ? {
                                                              borderLeft: `3px solid ${group.colour}`,
                                                          }
                                                        : undefined
                                                }
                                            >
                                                <ColorSwatch
                                                    color={group.colour ?? ""}
                                                />
                                                {group.label}{" "}
                                                {group.countLabel && (
                                                    <span
                                                        className={
                                                            groupRecipe[3]
                                                        }
                                                    >
                                                        · {group.countLabel}
                                                    </span>
                                                )}
                                            </th>
                                        </tr>
                                    </tbody>
                                )}
                                {renderRows(
                                    group.rows,
                                    group.label ? groupId : undefined,
                                )}
                            </Fragment>
                        );
                    })}
                </Table>
            ) : (
                <p className="p-4 text-sm text-muted">{empty}</p>
            )}
            <p className="sr-only" role="status" aria-live="polite">
                Sorted by {sorted?.label},{" "}
                {view.sort.startsWith("-") ? "descending" : "ascending"}.
                {grouped ? ` Grouped by ${grouped.label}.` : " No grouping."}
            </p>
        </div>
    );
}

export function compareTableValues(a: string | number, b: string | number) {
    if (typeof a === "string" && typeof b === "string") {
        const left = Array.from(a),
            right = Array.from(b);
        for (let i = 0; i < Math.min(left.length, right.length); i++) {
            const difference =
                left[i].codePointAt(0)! - right[i].codePointAt(0)!;
            if (difference) return difference;
        }
        return left.length - right.length;
    }
    return a < b ? -1 : a > b ? 1 : 0;
}
