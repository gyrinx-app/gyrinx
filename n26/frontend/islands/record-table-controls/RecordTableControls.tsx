import { useState } from "react";
import { Button, FilterMenu, SearchBar, type FilterOption } from "../../ui";

export type RecordTableControlsProps = {
    action: string;
    query: string;
    noun: string;
    singular: string;
    typeOptions: FilterOption[];
};

export type ListingFilter = { query: string; types: string[] | null };

export function RecordTableControls({
    action,
    query: initialQuery,
    noun,
    typeOptions,
    onFilter,
}: RecordTableControlsProps & { onFilter: (filter: ListingFilter) => void }) {
    const [query, setQuery] = useState(initialQuery);
    const [types, setTypes] = useState<string[] | null>(null);

    function search(value: string) {
        setQuery(value);
        onFilter({ query: value, types });
    }

    return (
        <div className="flex flex-col gap-3">
            <form
                action={action || undefined}
                method="get"
                onSubmit={
                    action ? undefined : (event) => event.preventDefault()
                }
                onKeyDown={(event) => {
                    if (
                        action &&
                        event.key === "Enter" &&
                        event.target instanceof HTMLInputElement &&
                        event.target.type === "search"
                    ) {
                        event.preventDefault();
                        event.currentTarget.requestSubmit();
                    }
                }}
                className="flex items-center gap-2"
            >
                <div className="min-w-0 flex-1">
                    <SearchBar
                        value={query}
                        onChange={search}
                        label={`Search ${noun}`}
                    />
                </div>
                <input type="hidden" name="q" value={query} />
                {action && (
                    <Button type="submit" variant="primary">
                        Search
                    </Button>
                )}
            </form>
            {typeOptions.length > 1 && (
                <div>
                    <FilterMenu
                        label="Type"
                        options={typeOptions}
                        onApply={(values) => {
                            setTypes(values);
                            onFilter({ query, types: values });
                        }}
                    />
                </div>
            )}
        </div>
    );
}
