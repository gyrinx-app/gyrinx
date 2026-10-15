import {
    Fragment,
    useEffect,
    useId,
    useRef,
    useState,
    type MouseEvent,
} from "react";
import {
    ActionMenu,
    Artwork,
    Badge,
    ButtonLink,
    ColorSwatch,
    Icon,
    IncomeTooltip,
    Link,
    NativeSelect,
    Table,
    UserLink,
} from "../../ui";
import {
    BASE_COLUMNS,
    actionHref,
    readView,
    sortColumns,
    tableGroups,
    viewHref,
    type CampaignGangsProps,
    type Gang,
    type View,
} from "./table";

function ordinaryClick(event: MouseEvent<HTMLAnchorElement>) {
    return (
        event.button === 0 &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.shiftKey &&
        !event.altKey
    );
}

export function CampaignGangs(
    props: CampaignGangsProps & {
        onOpenDialog: (href: string) => Promise<void>;
    },
) {
    const [view, setView] = useState<View>({
        sort: props.sort,
        group: props.group,
    });
    const [error, setError] = useState("");
    const [pending, setPending] = useState("");
    const opening = useRef(false);
    const alive = useRef(true);
    const initialised = useRef(false);
    const counterLinks = useRef(new Map<string, HTMLAnchorElement>());
    const id = useId();
    const columns = [...BASE_COLUMNS, ...props.counters];
    const sorts = sortColumns(props);
    const groups = tableGroups(props, view);
    const groupedIndex = props.labels.findIndex(
        (column) => column.token === view.group,
    );
    const back = viewHref(props.href, view, "gangs");
    useEffect(() => {
        if (props.focusCounter)
            counterLinks.current
                .get(props.focusCounter)
                ?.focus({ preventScroll: true });
    }, [props.focusCounter]);
    useEffect(() => {
        const restore = () => setView(readView(props, window.location.search));
        window.addEventListener("popstate", restore);
        const query = new URLSearchParams(window.location.search);
        if (
            !initialised.current &&
            (query.has("sort") || query.has("group")) &&
            (query.get("sort") !== props.sort ||
                query.get("group") !== props.group)
        ) {
            window.history.replaceState(
                { ...window.history.state, htmx: false },
                "",
                viewHref(window.location.href, {
                    sort: props.sort,
                    group: props.group,
                }),
            );
        }
        if (
            new URL(window.location.href).pathname ===
                new URL(props.href, window.location.href).pathname &&
            !query.has("starting") &&
            !query.has("roll")
        ) {
            window.history.replaceState(
                { ...window.history.state, htmx: false },
                "",
                window.location.href,
            );
        }
        initialised.current = true;
        alive.current = true;
        return () => {
            alive.current = false;
            window.removeEventListener("popstate", restore);
        };
    }, [props]);
    function change(next: View) {
        if (opening.current) return;
        // Dialog responses mark history for HTMX; table views are restored by React.
        const state = { ...window.history.state, htmx: false };
        window.history.replaceState(state, "", window.location.href);
        window.history.pushState(
            state,
            "",
            viewHref(window.location.href, next),
        );
        window.dispatchEvent(new Event("n26:location-changed"));
        setView(next);
    }
    async function open(event: MouseEvent<HTMLAnchorElement>, href: string) {
        if (!ordinaryClick(event)) return;
        event.preventDefault();
        if (opening.current) return;
        opening.current = true;
        setPending(href);
        setError("");
        try {
            await props.onOpenDialog(href);
        } catch {
            if (alive.current)
                setError(
                    "The form could not load. Reload the page and try again.",
                );
        } finally {
            opening.current = false;
            if (alive.current) setPending("");
        }
    }
    function gangRows(gang: Gang, groupId?: string) {
        const gangId = `${id}-gang-${gang.id}`;
        const headers = (column?: number | "actions") =>
            [gangId, column === undefined ? "" : `${id}-col-${column}`, groupId]
                .filter(Boolean)
                .join(" ");
        const details = [
            ...props.labels.flatMap((label, index) =>
                index === groupedIndex
                    ? []
                    : [{ label: label.label, text: gang.labels[index] }],
            ),
            ...gang.assets,
        ];
        return (
            <tbody
                key={gang.id}
                className="border-b border-box-border last:border-b-0 [&>tr:last-child>*]:pb-3! max-md:block"
            >
                <tr className="border-b-0! max-md:hover:bg-transparent! max-md:grid max-md:grid-cols-3 max-md:[&>td]:py-2!">
                    <th
                        id={gangId}
                        scope="rowgroup"
                        headers={[`${id}-col-0`, groupId]
                            .filter(Boolean)
                            .join(" ")}
                        className="w-64 min-w-48 max-w-64 align-middle font-normal! whitespace-normal! [overflow-wrap:anywhere] max-md:col-span-2 max-md:row-start-1 max-md:w-auto max-md:min-w-0 max-md:max-w-none"
                    >
                        <div className="flex flex-col">
                            <span className="font-semibold text-ink-900 dark:text-ink-100">
                                <Link href={gang.href} tone="current">
                                    <ColorSwatch color={gang.colour} />
                                    {gang.name}
                                </Link>
                            </span>
                            <span className="text-xs text-muted">
                                {gang.type}
                                {props.artwork[gang.artwork] && (
                                    <Artwork
                                        node={props.artwork[gang.artwork]!}
                                    />
                                )}
                                {gang.owner && (
                                    <>
                                        {" "}
                                        ·{" "}
                                        <UserLink
                                            name={gang.owner.name}
                                            href={gang.owner.href}
                                            badge={
                                                gang.owner.badge
                                                    ? props.badges[
                                                          gang.owner.badge
                                                      ]
                                                    : null
                                            }
                                        />
                                    </>
                                )}
                            </span>
                        </div>
                    </th>
                    <td
                        headers={headers(1)}
                        className="align-middle tabular-nums whitespace-nowrap max-md:block"
                    >
                        <span className="block text-xs font-medium text-muted md:hidden">
                            Rating
                        </span>
                        {gang.rating}¢
                    </td>
                    <td
                        headers={headers(2)}
                        className="align-middle tabular-nums whitespace-nowrap max-md:block"
                    >
                        <span className="block text-xs font-medium text-muted md:hidden">
                            Credits
                        </span>
                        {gang.credits === null ? (
                            <span className="text-muted">—</span>
                        ) : gang.creditsHref ? (
                            <Link
                                href={actionHref(gang.creditsHref, view, back)}
                            >
                                {gang.credits}¢
                            </Link>
                        ) : (
                            `${gang.credits}¢`
                        )}
                    </td>
                    <td
                        headers={headers(3)}
                        className="align-middle tabular-nums whitespace-nowrap max-md:block"
                    >
                        <span className="block text-xs font-medium text-muted md:hidden">
                            Wealth
                        </span>
                        {gang.wealth}¢
                    </td>
                    {gang.counters.map((counter, index) => {
                        const href = counter?.adjustHref
                            ? actionHref(counter.adjustHref, view, back)
                            : "";
                        return (
                            <td
                                key={props.counters[index].token}
                                headers={headers(index + 4)}
                                className="align-middle tabular-nums whitespace-nowrap max-md:block"
                            >
                                <span className="block text-xs font-medium text-muted whitespace-normal [overflow-wrap:anywhere] md:hidden">
                                    {props.counters[index].label}
                                </span>
                                {counter ? (
                                    <span className="inline-flex items-center gap-2">
                                        {counter.income ? (
                                            <IncomeTooltip
                                                {...counter.income}
                                            />
                                        ) : (
                                            <span className="tabular-nums">
                                                {counter.value}
                                            </span>
                                        )}
                                        {href && (
                                            <ButtonLink
                                                ref={(element) => {
                                                    if (element)
                                                        counterLinks.current.set(
                                                            counter.id,
                                                            element,
                                                        );
                                                    else
                                                        counterLinks.current.delete(
                                                            counter.id,
                                                        );
                                                }}
                                                id={`${gangId}-counter-${index}`}
                                                href={href}
                                                size="sm"
                                                variant="text"
                                                className="py-0!"
                                                aria-label={`Edit ${counter.name} for ${gang.name}`}
                                                aria-disabled={pending === href}
                                                onClick={(event) =>
                                                    void open(event, href)
                                                }
                                            >
                                                <Icon
                                                    name="pencil"
                                                    className="size-3.5"
                                                />
                                            </ButtonLink>
                                        )}
                                    </span>
                                ) : (
                                    <span className="text-muted">—</span>
                                )}
                            </td>
                        );
                    })}
                    <td
                        headers={headers("actions")}
                        className="w-0 text-right align-middle max-md:col-start-3 max-md:row-start-1 max-md:block max-md:w-auto max-md:justify-self-end"
                    >
                        {gang.removeHref && (
                            <ActionMenu
                                label={`Actions for ${gang.name}`}
                                variant="ghost"
                                align="end"
                                items={[
                                    {
                                        label: "Remove from campaign",
                                        href: actionHref(gang.removeHref, view),
                                        tone: "danger",
                                        separatorBefore: false,
                                    },
                                ]}
                            />
                        )}
                    </td>
                </tr>
                {(gang.overBudget ||
                    details.length > 0 ||
                    gang.rolls.length > 0) && (
                    <tr className="border-b-0! max-md:hover:bg-transparent! max-md:block">
                        <td
                            headers={headers()}
                            colSpan={columns.length + 1}
                            className="pt-0! pb-3! whitespace-normal! max-md:block"
                        >
                            <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1.5 text-xs">
                                {gang.overBudget && <Badge>Over budget</Badge>}
                                {details.map((detail, index) => (
                                    <span
                                        key={index}
                                        className="inline-flex min-w-0 max-w-full flex-wrap gap-x-2 [overflow-wrap:anywhere]"
                                    >
                                        <span className="text-muted">
                                            {detail.label}
                                        </span>
                                        <span className="min-w-0 break-words">
                                            {detail.text || (
                                                <span className="text-muted">
                                                    —
                                                </span>
                                            )}
                                        </span>
                                    </span>
                                ))}
                                {gang.rolls.map((roll) => {
                                    const href = actionHref(roll.href, view);
                                    return (
                                        <ButtonLink
                                            key={roll.href}
                                            href={href}
                                            size="sm"
                                            variant="text"
                                            className="py-0! text-xs!"
                                            aria-disabled={pending === href}
                                            onClick={(event) =>
                                                void open(event, href)
                                            }
                                        >
                                            <span className="flex items-center gap-1">
                                                {roll.label}
                                                <Icon
                                                    name="arrow-right"
                                                    className="size-3.5"
                                                />
                                            </span>
                                        </ButtonLink>
                                    );
                                })}
                            </div>
                        </td>
                    </tr>
                )}
            </tbody>
        );
    }
    return (
        <>
            <div className="flex flex-wrap items-end gap-3 border-b border-box-border px-4 py-3">
                <label className="flex min-w-0 max-w-full flex-col gap-1 text-xs text-muted">
                    Sort by
                    <NativeSelect
                        controlSize="sm"
                        disabled={Boolean(pending)}
                        value={view.sort}
                        onChange={(event) =>
                            change({ ...view, sort: event.target.value })
                        }
                    >
                        {sorts.flatMap((column) => [
                            <option key={column.token} value={column.token}>
                                {column.label} (ascending)
                            </option>,
                            <option
                                key={`-${column.token}`}
                                value={`-${column.token}`}
                            >
                                {column.label} (descending)
                            </option>,
                        ])}
                    </NativeSelect>
                </label>
                {props.labels.length > 0 && (
                    <label className="flex min-w-0 max-w-full flex-col gap-1 text-xs text-muted">
                        View groups by
                        <NativeSelect
                            controlSize="sm"
                            disabled={Boolean(pending)}
                            value={view.group}
                            onChange={(event) =>
                                change({ ...view, group: event.target.value })
                            }
                        >
                            <option value="">No grouping</option>
                            {props.labels.map((column) => (
                                <option key={column.token} value={column.token}>
                                    {column.label}
                                </option>
                            ))}
                        </NativeSelect>
                    </label>
                )}
            </div>
            {error && (
                <p
                    role="alert"
                    className="px-4 py-3 text-sm text-red-600 dark:text-red-400"
                >
                    {error}
                </p>
            )}
            {props.gangs.length === 0 ? (
                <p className="p-4 text-sm text-muted">
                    No gangs in this campaign yet.
                </p>
            ) : (
                <Table className="max-md:block">
                    <thead className="max-md:hidden">
                        <tr>
                            {columns.map((column, index) => {
                                const selected =
                                    view.sort.replace(/^-/, "") ===
                                    column.token;
                                const descending =
                                    selected && view.sort.startsWith("-");
                                const next = {
                                    ...view,
                                    sort:
                                        view.sort === column.token
                                            ? `-${column.token}`
                                            : column.token,
                                };
                                return (
                                    <th
                                        key={column.token}
                                        id={`${id}-col-${index}`}
                                        scope="col"
                                        aria-sort={
                                            selected
                                                ? descending
                                                    ? "descending"
                                                    : "ascending"
                                                : "none"
                                        }
                                    >
                                        <a
                                            href={viewHref(
                                                props.href,
                                                next,
                                                "gangs",
                                            )}
                                            className="inline-flex items-center gap-1 text-current focus-ring"
                                            aria-disabled={Boolean(pending)}
                                            onClick={(event) => {
                                                if (ordinaryClick(event)) {
                                                    event.preventDefault();
                                                    change(next);
                                                }
                                            }}
                                        >
                                            {column.label}
                                            {selected && (
                                                <Icon
                                                    name={
                                                        descending
                                                            ? "arrow-down"
                                                            : "arrow-up"
                                                    }
                                                    className="size-3"
                                                />
                                            )}
                                        </a>
                                    </th>
                                );
                            })}
                            <th
                                id={`${id}-col-actions`}
                                scope="col"
                                className="w-0"
                            >
                                <span className="sr-only">Actions</span>
                            </th>
                        </tr>
                    </thead>
                    {groups.map((group) => {
                        const groupId = `${id}-group-${encodeURIComponent(group.id)}`;
                        return (
                            <Fragment key={group.id}>
                                {group.label && (
                                    <tbody className="max-md:block">
                                        <tr className="max-md:block">
                                            <th
                                                id={groupId}
                                                colSpan={columns.length + 1}
                                                className="bg-ink-500/5 py-2! text-sm [overflow-wrap:anywhere] max-md:block max-md:w-full max-md:whitespace-normal!"
                                                style={
                                                    group.colour
                                                        ? {
                                                              borderLeft: `3px solid ${group.colour}`,
                                                          }
                                                        : undefined
                                                }
                                            >
                                                <ColorSwatch
                                                    color={group.colour}
                                                />
                                                {group.label}{" "}
                                                <span className="font-normal text-muted">
                                                    · {group.gangs.length} gang
                                                    {group.gangs.length !== 1 &&
                                                        "s"}
                                                </span>
                                            </th>
                                        </tr>
                                    </tbody>
                                )}
                                {group.gangs.map((gang) =>
                                    gangRows(
                                        gang,
                                        group.label ? groupId : undefined,
                                    ),
                                )}
                            </Fragment>
                        );
                    })}
                </Table>
            )}
            <p className="sr-only" role="status" aria-live="polite">
                Sorted by{" "}
                {
                    sorts.find(
                        (column) =>
                            column.token === view.sort.replace(/^-/, ""),
                    )?.label
                }
                , {view.sort.startsWith("-") ? "descending" : "ascending"}.
                {view.group
                    ? ` Grouped by ${props.labels.find((column) => column.token === view.group)?.label}.`
                    : " No grouping."}
            </p>
        </>
    );
}
