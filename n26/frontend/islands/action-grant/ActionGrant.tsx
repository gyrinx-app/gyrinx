import { useState } from "react";
import { Button, Input } from "../../ui";

export type GrantRow = {
    pk: string;
    name: string;
    gang: string;
    granted: boolean;
};

export type ActionGrantProps = { rows: GrantRow[] };

export function ActionGrant({ rows }: ActionGrantProps) {
    const [search, setSearch] = useState("");
    const [selected, setSelected] = useState<Set<string>>(() => new Set());
    const query = search.trim().toLowerCase();
    const shown = rows.filter((row) =>
        `${row.gang} ${row.name}`.toLowerCase().includes(query),
    );
    const shownIds = new Set(shown.map((row) => row.pk));

    return (
        <div className="rounded-box border border-box-border p-4">
            <label
                htmlFor="grant-filter"
                className="block text-sm font-semibold"
            >
                Find fighter entries
            </label>
            <Input
                id="grant-filter"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                    if (event.key === "Enter") event.preventDefault();
                }}
                placeholder="Search by entry or gang type"
                className="mt-2"
            />
            <div className="mt-3 flex gap-2">
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                        setSelected((old) => {
                            const next = new Set(old);
                            shown
                                .filter((row) => !row.granted)
                                .forEach((row) => next.add(row.pk));
                            return next;
                        })
                    }
                >
                    Select shown
                </Button>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelected(new Set())}
                >
                    Clear selection
                </Button>
            </div>
            <div className="mt-4 max-h-96 divide-y divide-box-border overflow-y-auto">
                {rows.map((row) => (
                    <label
                        key={row.pk}
                        hidden={!shownIds.has(row.pk)}
                        style={{
                            display: shownIds.has(row.pk) ? undefined : "none",
                        }}
                        className={`flex items-center gap-3 py-2 ${row.granted ? "text-muted" : ""}`}
                    >
                        <input
                            type="checkbox"
                            name="profiles"
                            value={row.pk}
                            checked={selected.has(row.pk)}
                            disabled={row.granted}
                            onChange={(event) =>
                                setSelected((old) => {
                                    const next = new Set(old);
                                    if (event.target.checked) next.add(row.pk);
                                    else next.delete(row.pk);
                                    return next;
                                })
                            }
                            className="size-4 accent-[var(--color-accent)]"
                        />
                        <span className="min-w-0">
                            <span className="font-medium">{row.name}</span>{" "}
                            <span className="text-sm text-muted">
                                {row.gang}
                            </span>
                        </span>
                        {row.granted && (
                            <span className="ml-auto text-xs text-muted">
                                Already granted
                            </span>
                        )}
                    </label>
                ))}
                {shown.length === 0 && (
                    <p className="py-2 text-sm text-muted">
                        No fighter entries match that.
                    </p>
                )}
            </div>
        </div>
    );
}
