import { useState } from "react";
import {
    FilterMenu,
    Link,
    SearchBar,
    Table,
    type FilterOption,
} from "../../ui";

type FacetName = "scope" | "effect" | "carried";

export type ModifierRow = {
    pk: string;
    label: string;
    url: string;
    notes: string[];
    facets: Record<FacetName, string> & { search: string };
};

export type ModifierListProps = {
    rows: ModifierRow[];
    scopeOptions: FilterOption[];
    effectOptions: FilterOption[];
    carriedOptions: FilterOption[];
};

export function ModifierList({
    rows,
    scopeOptions,
    effectOptions,
    carriedOptions,
}: ModifierListProps) {
    const facets: Array<{
        name: FacetName;
        label: string;
        options: FilterOption[];
    }> = [
        { name: "scope", label: "Reaches", options: scopeOptions },
        { name: "effect", label: "Does", options: effectOptions },
        { name: "carried", label: "Carried", options: carriedOptions },
    ];
    const [query, setQuery] = useState("");
    const [selected, setSelected] = useState<Record<FacetName, string[]>>(
        () =>
            Object.fromEntries(
                facets.map((facet) => [
                    facet.name,
                    facet.options.map((option) => option.value),
                ]),
            ) as Record<FacetName, string[]>,
    );
    const wanted = query.trim().toLowerCase();
    const shown = rows.filter(
        (row) =>
            (!wanted || row.facets.search.includes(wanted)) &&
            facets.every((facet) =>
                selected[facet.name].includes(row.facets[facet.name]),
            ),
    );

    return (
        <div className="flex flex-col gap-3">
            <SearchBar
                value={query}
                onChange={setQuery}
                label="Search modifiers"
            />
            {facets.some((facet) => facet.options.length > 1) && (
                <div className="flex flex-wrap items-center gap-2">
                    {facets.map(
                        (facet) =>
                            facet.options.length > 1 && (
                                <FilterMenu
                                    key={facet.name}
                                    label={facet.label}
                                    options={facet.options}
                                    onApply={(values) =>
                                        setSelected((previous) => ({
                                            ...previous,
                                            [facet.name]: values,
                                        }))
                                    }
                                />
                            ),
                    )}
                </div>
            )}
            <p role="status" className="text-sm text-muted">
                <span className="font-semibold text-ink-900 tabular-nums dark:text-ink-100">
                    {shown.length}
                </span>{" "}
                of {rows.length} modifiers
            </p>
            <Table className="table-fixed">
                <tbody>
                    {shown.map((row) => (
                        <tr key={row.pk}>
                            <td className="w-2/5 min-w-0 align-top whitespace-normal">
                                <Link
                                    href={row.url}
                                    className="break-words whitespace-normal"
                                >
                                    {row.label}
                                </Link>
                            </td>
                            <td className="w-3/5 break-words whitespace-normal text-muted">
                                {row.notes.join(" · ")}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </Table>
            {!shown.length && (
                <p className="py-6 text-center text-sm text-muted">
                    No modifiers match that.
                </p>
            )}
        </div>
    );
}
