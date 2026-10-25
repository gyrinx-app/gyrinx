import { useRef } from "react";
import { FilterMenu, type FilterMenuSize, type FilterOption } from "../../ui";

export type FilterMenuIslandProps = {
    label: string;
    name: string;
    options: FilterOption[];
    selected: string[];
    selectAll: boolean;
    applyLabel: string;
    cancelLabel: string;
    size: FilterMenuSize;
    align: "start" | "end";
    width: number;
};

/** The cotton filter menu: OK tells the page, and a matching reset restores every tick. */
export function FilterMenuIsland({ name, ...props }: FilterMenuIslandProps) {
    const root = useRef<HTMLDivElement>(null);
    return (
        <div ref={root} className="contents">
            <FilterMenu
                {...props}
                name={name}
                onApply={(values) => {
                    root.current?.dispatchEvent(
                        new CustomEvent("filter-apply", {
                            bubbles: true,
                            detail: { name, values: values.slice() },
                        }),
                    );
                }}
            />
        </div>
    );
}
