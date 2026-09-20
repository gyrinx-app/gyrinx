import { useEffect, useRef, useState } from "react";
import {
    ActionBar,
    Button,
    Link,
    SearchBar,
    StagedBadge,
    Table,
} from "../../ui";

export type AuthoringRow = {
    pk: string;
    label: string;
    qualifier: string;
    url: string;
    notes: string[];
    help: string;
    staged: boolean;
    search: string;
};

export type AuthoringListProps = {
    rows: AuthoringRow[];
    pluralLabel: string;
    bulkActionUrl: string | null;
};

export function AuthoringList({
    rows,
    pluralLabel,
    bulkActionUrl,
}: AuthoringListProps) {
    const [query, setQuery] = useState("");
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const all = useRef<HTMLInputElement>(null);
    const wanted = query.trim().toLowerCase();
    const shown = rows.filter((row) => !wanted || row.search.includes(wanted));
    const checked = shown.filter((row) => selected.has(row.pk)).length;

    useEffect(() => {
        if (all.current)
            all.current.indeterminate = checked > 0 && checked < shown.length;
    }, [checked, shown.length]);

    function select(ids: string[], on: boolean) {
        setSelected((previous) => {
            const next = new Set(previous);
            ids.forEach((id) => {
                if (on) next.add(id);
                else next.delete(id);
            });
            return next;
        });
    }

    const table = (
        <Table>
            <tbody>
                {shown.map((row) => (
                    <tr key={row.pk}>
                        {bulkActionUrl && (
                            <td className="w-0 pr-0">
                                <input
                                    type="checkbox"
                                    aria-label={`Select ${row.label}${row.qualifier ? ` — ${row.qualifier}` : ""}`}
                                    className="size-4 accent-[var(--color-accent)] focus-ring"
                                    checked={selected.has(row.pk)}
                                    onChange={(event) =>
                                        select([row.pk], event.target.checked)
                                    }
                                />
                            </td>
                        )}
                        <td className="whitespace-nowrap">
                            {row.url ? (
                                <Link href={row.url}>{row.label}</Link>
                            ) : (
                                row.label
                            )}
                            {row.qualifier && ` — ${row.qualifier}`}
                            {row.staged && (
                                <>
                                    {" "}
                                    <StagedBadge />
                                </>
                            )}
                        </td>
                        <td className="w-full text-muted">
                            {row.notes.join(" · ")}
                            {row.notes.length > 0 && row.help && " · "}
                            {row.help}
                        </td>
                    </tr>
                ))}
            </tbody>
        </Table>
    );

    return (
        <div className="flex flex-col gap-3">
            <SearchBar
                value={query}
                onChange={setQuery}
                label={`Search ${pluralLabel}`}
            />
            <p role="status" className="text-sm text-muted">
                <span className="font-semibold text-ink-900 tabular-nums dark:text-ink-100">
                    {shown.length}
                </span>{" "}
                of {rows.length} {pluralLabel}
            </p>
            {bulkActionUrl ? (
                <form method="get" action={bulkActionUrl}>
                    <ActionBar
                        trailing={
                            <Button type="submit" variant="primary">
                                Attach a modifier
                            </Button>
                        }
                    >
                        <label className="flex items-center gap-2 text-sm">
                            <input
                                ref={all}
                                type="checkbox"
                                className="size-4 accent-[var(--color-accent)] focus-ring"
                                disabled={!shown.length}
                                checked={
                                    shown.length > 0 && checked === shown.length
                                }
                                onChange={(event) =>
                                    select(
                                        shown.map((row) => row.pk),
                                        event.target.checked,
                                    )
                                }
                            />
                            Select all shown
                        </label>
                        <span className="text-sm text-muted">
                            <span className="font-semibold text-ink-900 tabular-nums dark:text-ink-100">
                                {selected.size}
                            </span>{" "}
                            selected
                        </span>
                    </ActionBar>
                    {/* Selections hidden by the filter still belong to the submitted form. */}
                    {Array.from(selected).map((id) => (
                        <input key={id} type="hidden" name="pk" value={id} />
                    ))}
                    {table}
                </form>
            ) : (
                table
            )}
            {!shown.length && (
                <p className="py-6 text-center text-sm text-muted">
                    No {pluralLabel} match that.
                </p>
            )}
        </div>
    );
}
