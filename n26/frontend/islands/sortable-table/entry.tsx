import { useId, useState } from "react";
import { mount as mountRoot } from "../../runtime/mount";
import {
    SortableTable,
    compareTableValues,
    type TableColumn,
    type TableGroup,
    type TableView,
} from "../../ui";

type Row = {
    id: string;
    values: Record<string, string | number>;
    groups?: Record<string, string>;
};
type Props = {
    label: string;
    columns: TableColumn[];
    rows: Row[];
    groupOptions?: { token: string; label: string }[];
    sort: string;
    group: string;
};
export function PlainSortableTable(props: Props) {
    const id = useId();
    const [view, setView] = useState<TableView>({
        sort: props.sort,
        group: props.group,
    });
    const key = view.sort.replace(/^-/, "");
    const direction = view.sort.startsWith("-") ? -1 : 1;
    const rows = [...props.rows].sort(
        (a, b) =>
            direction *
                compareTableValues(a.values[key] ?? "", b.values[key] ?? "") ||
            compareTableValues(a.id, b.id),
    );
    const buckets = new Map<string, Row[]>();
    for (const row of rows) {
        const group = view.group ? (row.groups?.[view.group] ?? "Not set") : "";
        const bucket = buckets.get(group) ?? [];
        bucket.push(row);
        buckets.set(group, bucket);
    }
    const groups: TableGroup<Row>[] = [...buckets]
        .sort(([a], [b]) => compareTableValues(a, b))
        .map(([label, rows]) => ({
            id: label || "all",
            label,
            rows,
            countLabel: String(rows.length),
        }));
    return (
        <SortableTable
            id={id}
            label={props.label}
            columns={props.columns}
            groupOptions={props.groupOptions}
            view={view}
            groups={groups}
            onViewChange={setView}
            viewHref={() => "#"}
            renderRows={(rows, groupId) => (
                <tbody>
                    {rows.map((row) => (
                        <tr key={row.id}>
                            {props.columns.map((column, index) => (
                                <td
                                    key={column.token}
                                    headers={[`${id}-col-${index}`, groupId]
                                        .filter(Boolean)
                                        .join(" ")}
                                    className={column.className}
                                >
                                    {row.values[column.token]}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            )}
        />
    );
}
export function mount(element: HTMLElement, props: Props) {
    return mountRoot(element, PlainSortableTable, props);
}
