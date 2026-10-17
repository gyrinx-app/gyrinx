import type {
    BadgeMark,
    CountedName,
    IncomeTooltipProps,
    SvgNode,
} from "../../ui";

export type Column = { token: string; label: string };
export type LabelColumn = Column & { colours: Record<string, string> };
export type Gang = {
    id: string;
    name: string;
    type: string;
    artwork: string;
    owner: { name: string; href: string; badge: string | null } | null;
    colour: string;
    href: string;
    rating: number;
    credits: number | null;
    wealth: number;
    creditsHref: string;
    removeHref: string;
    overBudget: boolean;
    sortValues: Record<string, string | number | null>;
    labels: string[];
    assets: { label: string; names: CountedName[] }[];
    rolls: { label: string; href: string }[];
    counters: ({
        id: string;
        name: string;
        value: number;
        adjustHref: string;
        income: IncomeTooltipProps | null;
    } | null)[];
};
export type CampaignGangsProps = {
    href: string;
    sort: string;
    group: string;
    defaultGroup: string;
    counters: Column[];
    labels: LabelColumn[];
    gangs: Gang[];
    badges: Record<string, BadgeMark>;
    artwork: Record<string, SvgNode | null>;
    focusCounter?: string;
};
export type View = { sort: string; group: string };
export const BASE_COLUMNS: Column[] = [
    { token: "name", label: "Gang" },
    { token: "rating", label: "Rating" },
    { token: "credits", label: "Credits" },
    { token: "wealth", label: "Wealth" },
];
export function sortColumns(props: CampaignGangsProps) {
    return [
        ...BASE_COLUMNS,
        ...props.counters,
        { token: "type", label: "Gang type" },
        { token: "owner", label: "Player" },
        ...props.labels,
    ];
}
export function readView(props: CampaignGangsProps, search: string): View {
    const query = new URLSearchParams(search);
    const supplied = query.get("sort") ?? "name";
    const descending = supplied.startsWith("-");
    let key = supplied.replace(/^-/, "");
    const legacy = /^(counter|label)-(0|[1-9]\d*)$/.exec(key);
    if (legacy)
        key =
            (legacy[1] === "counter" ? props.counters : props.labels)[
                Number(legacy[2])
            ]?.token ?? "";
    const sort = sortColumns(props).some((column) => column.token === key)
        ? `${descending ? "-" : ""}${key}`
        : "name";
    let group = query.get("group") ?? props.defaultGroup;
    const oldGroup = /^label-(0|[1-9]\d*)$/.exec(group);
    if (oldGroup) group = props.labels[Number(oldGroup[1])]?.token ?? "";
    return {
        sort,
        group: props.labels.some((column) => column.token === group)
            ? group
            : "",
    };
}
export function viewHref(href: string, view: View, hash?: string) {
    const url = new URL(href, window.location.href);
    url.searchParams.set("sort", view.sort);
    url.searchParams.set("group", view.group);
    if (hash !== undefined) url.hash = hash;
    return url.pathname + url.search + url.hash;
}
export function actionHref(href: string, view: View, back?: string) {
    const url = new URL(href, window.location.href);
    if (back !== undefined) url.searchParams.set("back", back);
    else {
        url.searchParams.set("sort", view.sort);
        url.searchParams.set("group", view.group);
    }
    return url.pathname + url.search + url.hash;
}
function compare(a: string | number, b: string | number) {
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
export function tableGroups(props: CampaignGangsProps, view: View) {
    const key = view.sort.replace(/^-/, "");
    const direction = view.sort.startsWith("-") ? -1 : 1;
    const gangs = [...props.gangs].sort((a, b) => {
        const av = a.sortValues[key] ?? null,
            bv = b.sortValues[key] ?? null;
        const tie =
            compare(a.sortValues.name!, b.sortValues.name!) ||
            compare(a.id, b.id);
        if (av === null) return bv === null ? tie : 1;
        if (bv === null) return -1;
        return direction * compare(av, bv) || tie;
    });
    const groupedIndex = props.labels.findIndex(
        (column) => column.token === view.group,
    );
    if (groupedIndex < 0) return [{ id: "all", label: "", colour: "", gangs }];
    const buckets = new Map<string, Gang[]>();
    for (const gang of gangs) {
        const label = gang.labels[groupedIndex] || "";
        buckets.set(label, [...(buckets.get(label) ?? []), gang]);
    }
    const groupToken = props.labels[groupedIndex].token;
    return [...buckets.keys()]
        .sort((a, b) =>
            a && b
                ? compare(
                      buckets.get(a)![0].sortValues[groupToken]!,
                      buckets.get(b)![0].sortValues[groupToken]!,
                  )
                : a
                  ? -1
                  : b
                    ? 1
                    : 0,
        )
        .map((label) => ({
            id: `value:${label}`,
            label: label || "Not set",
            colour: props.labels[groupedIndex].colours[label] ?? "",
            gangs: buckets.get(label)!,
        }));
}
