import { mount as mountRoot } from "../../runtime/mount";
import {
    RecordTableControls,
    type ListingFilter,
    type RecordTableControlsProps,
} from "./RecordTableControls";

export function filterListing(
    table: HTMLElement,
    props: Pick<RecordTableControlsProps, "query" | "noun" | "singular">,
    filter: ListingFilter,
) {
    const query = filter.query.trim().toLowerCase();
    const answered = props.query.toLowerCase();
    let shown = 0;
    for (const row of table.querySelectorAll<HTMLElement>(
        "[data-record-row]",
    )) {
        if (row.closest("[data-record-table]") !== table) continue;
        const matchesType =
            filter.types === null ||
            filter.types.includes(row.dataset.recordType || "");
        const matchesSearch =
            !query ||
            query === answered ||
            (row.dataset.recordSearch || "").includes(query);
        const visible = matchesType && matchesSearch;
        row.hidden = !visible;
        row.style.display = visible ? "" : "none";
        if (visible) shown += 1;
    }
    const count = table.querySelector<HTMLElement>("[data-record-count]");
    if (count) count.textContent = String(shown);
    const noun = table.querySelector<HTMLElement>("[data-record-noun]");
    if (noun) noun.textContent = shown === 1 ? props.singular : props.noun;
    const empty = table.querySelector<HTMLElement>("[data-record-empty]");
    if (empty) empty.hidden = shown !== 0;
}

export function mount(element: HTMLElement, props: RecordTableControlsProps) {
    const table = element.closest<HTMLElement>("[data-record-table]");
    if (!table) throw new Error("Listing controls require a record table");
    const onFilter = (filter: ListingFilter) =>
        filterListing(table, props, filter);
    onFilter({ query: props.query, types: null });
    return mountRoot(element, RecordTableControls, { ...props, onFilter });
}
