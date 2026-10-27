import { useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
    ActionBar,
    Button,
    FilterMenu,
    SearchBar,
    Toggle,
    type FilterOption,
} from "../../ui";

export type RecordTableControlsProps = {
    action: string;
    query: string;
    noun: string;
    singular: string;
    typeOptions: FilterOption[];
    mineOnly?: boolean | null;
};

export type ListingFilter = { query: string; types: string[] | null };

export function RecordTableControls({
    action,
    query: initialQuery,
    noun,
    typeOptions,
    mineOnly: initialMineOnly = null,
    onFilter,
}: RecordTableControlsProps & { onFilter: (filter: ListingFilter) => void }) {
    const [query, setQuery] = useState(initialQuery);
    const [types, setTypes] = useState<string[] | null>(null);
    const [mineOnly, setMineOnly] = useState(initialMineOnly);
    const form = useRef<HTMLFormElement>(null);

    function search(value: string) {
        setQuery(value);
        onFilter({ query: value, types });
    }

    return (
        <form
            ref={form}
            action={action || undefined}
            method="get"
            onSubmit={action ? undefined : (event) => event.preventDefault()}
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
            className="flex flex-wrap items-center gap-3"
        >
            <div className="flex w-full min-w-0 max-w-xl basis-96 grow items-center gap-2">
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
            </div>
            {mineOnly === false && (
                <input type="hidden" name="everyone" value="1" />
            )}
            {(typeOptions.length > 1 || mineOnly !== null) && (
                <ActionBar
                    surface={false}
                    spaced={false}
                    aria-label="Filters"
                    role="group"
                >
                    {typeOptions.length > 1 && (
                        <FilterMenu
                            label="Type"
                            options={typeOptions}
                            onApply={(values) => {
                                setTypes(values);
                                onFilter({ query, types: values });
                            }}
                        />
                    )}
                    {mineOnly !== null && (
                        <Toggle
                            label={`Your ${noun} only`}
                            checked={mineOnly}
                            onCheckedChange={(checked) => {
                                // The GET must read the new scope before navigation.
                                flushSync(() => setMineOnly(checked));
                                form.current?.requestSubmit();
                            }}
                        />
                    )}
                </ActionBar>
            )}
        </form>
    );
}
