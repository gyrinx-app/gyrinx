import { useEffect, useId, useRef, useState, type MouseEvent } from "react";
import {
    ActionMenu,
    IncomeTooltip,
    Link,
    SortableTable,
    useCampaignDialogRequests,
    runCampaignDialog,
    type TableView,
} from "../../ui";
import {
    assetGroups,
    GROUPS,
    readView,
    viewHref,
    type CampaignAssetsProps,
} from "./table";

export function CampaignAssets(
    props: CampaignAssetsProps & {
        onOpenDialog: (href: string) => Promise<void>;
    },
) {
    const [view, setView] = useState<TableView>({
        sort: props.sort,
        group: props.group,
    });
    const [search, setSearch] = useState(window.location.search);
    const [error, setError] = useState("");
    const [opening, setOpening] = useState(false);
    const openingRef = useRef(false);
    const alive = useRef(true);
    const { pending, requests } = useCampaignDialogRequests();
    const id = useId();
    useEffect(() => {
        alive.current = true;
        function restore() {
            if (props.href) setView(readView(window.location.search));
            setSearch(window.location.search);
        }
        window.addEventListener("popstate", restore);
        window.addEventListener("n26:location-changed", restore);
        return () => {
            alive.current = false;
            window.removeEventListener("popstate", restore);
            window.removeEventListener("n26:location-changed", restore);
        };
    }, [props.href]);
    const hrefFor = (href: string) => viewHref(href, view, search);
    function change(next: TableView) {
        if (openingRef.current || requests.current.size) return;
        setView(next);
        if (props.href) {
            const state = { ...window.history.state, htmx: false };
            window.history.replaceState(state, "", window.location.href);
            window.history.pushState(
                state,
                "",
                viewHref(window.location.href, next),
            );
            window.dispatchEvent(new Event("n26:location-changed"));
        }
    }
    async function open(event: MouseEvent<HTMLTableCellElement>) {
        const link = (event.target as Element).closest<HTMLAnchorElement>(
            "a[href]",
        );
        if (
            !link ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        )
            return;
        const href = link.getAttribute("href")!;
        const action = props.entries
            .flatMap((entry) => entry.actions)
            .find((action) => action.dialog && hrefFor(action.href) === href);
        if (!action) return;
        event.preventDefault();
        if (openingRef.current || requests.current.size) return;
        openingRef.current = true;
        setOpening(true);
        setError("");
        try {
            await runCampaignDialog(() => props.onOpenDialog(href));
        } catch {
            if (alive.current)
                setError(
                    "The form could not load. Reload the page and try again.",
                );
        } finally {
            openingRef.current = false;
            if (alive.current) setOpening(false);
        }
    }
    const columns = [
        { token: "name", label: props.label },
        { token: "income", label: "Income", className: "text-right" },
        { token: "holder", label: "Held by" },
        { token: "boon", label: "Boon", sortable: false },
        {
            token: "actions",
            label: "Actions",
            sortable: false,
            hiddenLabel: true,
            className: "w-0",
        },
    ];
    return (
        <SortableTable
            id={id}
            label={`${props.plural} inventory`}
            view={view}
            columns={columns}
            groupOptions={GROUPS}
            groups={assetGroups(props, view)}
            onViewChange={change}
            viewHref={(next) =>
                props.href ? viewHref(window.location.href, next) : "#"
            }
            disabled={pending || opening}
            error={error}
            empty={`No ${props.plural.toLowerCase()} yet.`}
            renderRows={(entries, groupId) => (
                <tbody key={groupId ?? "all"}>
                    {entries.map((entry) => {
                        const rowId = `${id}-entry-${entry.id}`;
                        const headers = (index: number) =>
                            [
                                rowId,
                                `${id}-col-${index === 4 ? "actions" : index}`,
                                groupId,
                            ]
                                .filter(Boolean)
                                .join(" ");
                        return (
                            <tr key={entry.id}>
                                <th
                                    id={rowId}
                                    scope="row"
                                    headers={[`${id}-col-0`, groupId]
                                        .filter(Boolean)
                                        .join(" ")}
                                    className="min-w-32 max-w-48 whitespace-normal! [overflow-wrap:anywhere]"
                                >
                                    <Link
                                        href={hrefFor(entry.href)}
                                        tone="current"
                                        className="font-semibold text-ink-900 dark:text-ink-100"
                                    >
                                        {entry.name}
                                    </Link>
                                    {entry.assetName && (
                                        <span className="block text-xs font-normal text-muted">
                                            {entry.assetName}
                                        </span>
                                    )}
                                </th>
                                <td
                                    headers={headers(1)}
                                    className="text-right tabular-nums whitespace-nowrap"
                                >
                                    <IncomeTooltip {...entry.income} />
                                </td>
                                <td
                                    headers={headers(2)}
                                    className="w-1/3 min-w-40 max-w-64 [overflow-wrap:anywhere]"
                                >
                                    {entry.held ? (
                                        <Link href={entry.holderHref}>
                                            {entry.holder}
                                        </Link>
                                    ) : (
                                        <span className="text-muted">
                                            Unclaimed
                                        </span>
                                    )}
                                </td>
                                <td
                                    headers={headers(3)}
                                    className="min-w-32 max-w-64 break-words text-sm [overflow-wrap:anywhere]"
                                >
                                    {entry.boon || "—"}
                                </td>
                                <td
                                    headers={headers(4)}
                                    className="w-12 text-right"
                                    onClick={(event) => void open(event)}
                                >
                                    {entry.actions.length > 0 && (
                                        <ActionMenu
                                            label={`Actions for ${entry.name}`}
                                            variant="ghost"
                                            align="end"
                                            items={entry.actions.map(
                                                (action) => ({
                                                    ...action,
                                                    href: hrefFor(action.href),
                                                }),
                                            )}
                                        />
                                    )}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            )}
        />
    );
}
