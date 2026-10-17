import {
    campaignViewHref,
    compareTableValues,
    type IncomeTooltipProps,
    type TableView,
    type TableGroup,
} from "../../ui";

export type AssetEntry = {
    id: string;
    name: string;
    assetName: string;
    boon: string;
    income: IncomeTooltipProps;
    held: boolean;
    holder: string;
    holderId: string;
    holderHref: string;
    href: string;
    sortValues: { name: string; holder: string; income: number };
    actions: {
        label: string;
        href: string;
        dialog: boolean;
        tone: "default" | "danger";
        separatorBefore: boolean;
    }[];
};
export type CampaignAssetsProps = {
    label: string;
    plural: string;
    typeId: string;
    href: string;
    sort: string;
    group: string;
    entries: AssetEntry[];
};
export const GROUPS = [
    { token: "status", label: "Held or unclaimed" },
    { token: "holder", label: "Holding gang" },
];
export function readView(search: string): TableView {
    const query = new URLSearchParams(search);
    const supplied = query.get("asset_sort") ?? "name";
    const sort = ["name", "income", "holder"].includes(
        supplied.replace(/^-/, ""),
    )
        ? supplied
        : "name";
    const group = query.get("asset_group") ?? "status";
    return {
        sort,
        group: ["", "status", "holder"].includes(group) ? group : "status",
    };
}
export function viewHref(
    href: string,
    view: TableView,
    search = window.location.search,
) {
    const url = new URL(campaignViewHref(href, search), window.location.href);
    url.searchParams.set("asset_sort", view.sort);
    url.searchParams.set("asset_group", view.group);
    return url.pathname + url.search + url.hash;
}
export function assetGroups(
    props: CampaignAssetsProps,
    view: TableView,
): TableGroup<AssetEntry>[] {
    const key = view.sort.replace(/^-/, "") as keyof AssetEntry["sortValues"];
    const direction = view.sort.startsWith("-") ? -1 : 1;
    const entries = [...props.entries].sort((a, b) => {
        if (key === "holder" && a.held !== b.held) return a.held ? 1 : -1;
        return (
            direction *
                compareTableValues(a.sortValues[key], b.sortValues[key]) ||
            compareTableValues(a.sortValues.name, b.sortValues.name) ||
            compareTableValues(a.id, b.id)
        );
    });
    if (!view.group) return [{ id: "all", label: "", rows: entries }];
    const buckets = new Map<string, AssetEntry[]>();
    for (const entry of entries) {
        const key = entry.held
            ? view.group === "holder"
                ? entry.holderId
                : "held"
            : "";
        const bucket = buckets.get(key) ?? [];
        bucket.push(entry);
        buckets.set(key, bucket);
    }
    return [...buckets.keys()]
        .sort((a, b) => {
            if (!a || !b) return a ? 1 : b ? -1 : 0;
            return view.group === "holder"
                ? compareTableValues(
                      buckets.get(a)![0].sortValues.holder,
                      buckets.get(b)![0].sortValues.holder,
                  ) || compareTableValues(a, b)
                : 0;
        })
        .map((key) => {
            const rows = buckets.get(key)!;
            return {
                id: key || "unclaimed",
                label: key
                    ? view.group === "holder"
                        ? rows[0].holder
                        : "Held"
                    : "Unclaimed",
                rows,
                countLabel: `${rows.length} ${rows.length === 1 ? props.label.toLowerCase() : props.plural.toLowerCase()}`,
            };
        });
}
