import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type MouseEvent,
} from "react";
import {
    Alert,
    Breadcrumbs,
    Button,
    ButtonLink,
    CatalogueFrame,
    EquipmentRow,
    equipmentDraft,
    type EquipmentDraft,
    EquipmentRail,
    GangFigures,
    UserLink,
    WorkflowLayout,
    EquipmentModel,
    EquipmentBudget,
    QuickSwitcher,
    type EquipmentPurchase,
} from "../../ui";
import { Command } from "./Command";
import {
    blankValues,
    panelDraft,
    type EquipDraft,
    type EquipOutcome,
    type EquipProps,
} from "./types";
import { isEquipPage } from "./validate";
const kinds = [
    "sell",
    "reassign",
    "fit",
    "detach",
    "refund",
    "remove",
    "accessorise",
    "rechoose",
];

export function Equip(initial: EquipProps) {
    const [page, setPage] = useState(initial);
    const [purchaseDrafts, setPurchaseDrafts] = useState<
        Record<string, EquipmentDraft>
    >({});
    const [draft, setDraft] = useState<EquipDraft | null>(() =>
        initial.dialog ? panelDraft(initial, initial.dialog) : null,
    );
    const [generation, setGeneration] = useState(0);
    const [expanded, setExpanded] = useState(initial.owned);
    const [openRows, setOpenRows] = useState<Set<string>>(
        () => new Set(initial.owned ? [initial.owned] : []),
    );
    const [frozen, setFrozen] = useState(false);
    const [tallyMode, setTallyMode] = useState(false);
    const tallyActive = useRef(false);
    const tallyQueue = useRef<EquipDraft[]>([]);
    const [queueNotice, setQueueNotice] = useState("");
    const [loading, setLoading] = useState(false);
    const [notice, setNotice] = useState("");
    const [retry, setRetry] = useState("");
    const read = useRef<AbortController | null>(null);
    const root = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLElement | null>(null);
    const heading = useRef<HTMLHeadingElement>(null);
    const returnFocus = useRef(false);
    const stopTallyQueue = useCallback(() => {
        tallyActive.current = false;
        setTallyMode(false);
        if (tallyQueue.current.length) {
            setQueueNotice(
                `${tallyQueue.current.length} queued counter ${tallyQueue.current.length === 1 ? "change was" : "changes were"} not sent. Resolve the earlier change before adding them again.`,
            );
            tallyQueue.current = [];
        }
    }, []);
    useEffect(() => {
        if (!returnFocus.current) return;
        returnFocus.current = false;
        if (trigger.current?.isConnected) trigger.current.focus();
        else heading.current?.focus();
    }, [generation]);
    const refreshPanel = useCallback(
        async (url: string) => {
            read.current?.abort();
            const controller = new AbortController();
            read.current = controller;
            setLoading(true);
            setNotice("");
            setRetry(url);
            try {
                const target = new URL(url, window.location.href);
                const endpoint = new URL(
                    initial.displayHref,
                    window.location.href,
                );
                endpoint.search = target.search;
                const response = await fetch(endpoint, {
                    credentials: "same-origin",
                    headers: { Accept: "application/json" },
                    signal: controller.signal,
                });
                if (!response.ok)
                    throw new Error(
                        response.status === 401
                            ? "Sign in again to view this equipment."
                            : "The equipment details could not be loaded. Try again.",
                    );
                const data: unknown = await response.json();
                if (
                    !data ||
                    typeof data !== "object" ||
                    !("page" in data) ||
                    !isEquipPage(data.page)
                )
                    throw new Error(
                        "The equipment details could not be loaded. Try again.",
                    );
                if (controller.signal.aborted) return;
                setPage(data.page);
                setDraft(
                    data.page.dialog
                        ? panelDraft(data.page, data.page.dialog)
                        : null,
                );
                setGeneration((value) => value + 1);
                window.history.replaceState(window.history.state, "", target);
                setRetry("");
            } catch (error) {
                if (!controller.signal.aborted)
                    setNotice(
                        error instanceof Error &&
                            error.message ===
                                "Sign in again to view this equipment."
                            ? error.message
                            : "The equipment details could not be loaded. Try again.",
                    );
            } finally {
                if (!controller.signal.aborted) setLoading(false);
            }
        },
        [initial.displayHref],
    );
    useEffect(() => () => read.current?.abort(), []);
    useEffect(() => {
        const restore = () => {
            if (!frozen) {
                const owned =
                    new URLSearchParams(window.location.search).get("owned") ||
                    "";
                setExpanded(owned);
                setOpenRows(new Set(owned ? [owned] : []));
                void refreshPanel(window.location.href);
            }
        };
        window.addEventListener("popstate", restore);
        return () => window.removeEventListener("popstate", restore);
    }, [frozen, refreshPanel]);
    function open(event: MouseEvent<HTMLDivElement>) {
        if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        )
            return;
        const anchor = (event.target as Element).closest<HTMLAnchorElement>(
            "a[href]",
        );
        if (!anchor) return;
        const url = new URL(anchor.href, window.location.href);
        if (
            url.origin !== window.location.origin ||
            url.pathname !==
                new URL(page.action, window.location.href).pathname ||
            !kinds.some((kind) => url.searchParams.has(kind))
        )
            return;
        event.preventDefault();
        if (frozen || tallyActive.current || loading) return;
        const current = new URLSearchParams(window.location.search);
        for (const [name, value] of [
            ["section", current.get("section") || ""],
            ["owned", expanded],
        ]) {
            if (value) url.searchParams.set(name, value);
            else url.searchParams.delete(name);
        }
        const menu = anchor.closest('[role="menu"]');
        trigger.current =
            menu?.parentElement?.querySelector<HTMLButtonElement>(
                'button[aria-haspopup="menu"]',
            ) || anchor;
        void refreshPanel(url.href);
    }
    function navigationValues() {
        const params = new URLSearchParams(window.location.search);
        return {
            ...blankValues(page),
            section: params.get("section") || "",
            owned: expanded,
            request_key: crypto.randomUUID(),
        };
    }
    function buy(
        purchase: EquipmentPurchase,
        paid: string,
        selection: string[],
        parts: Array<{ key: string; paid: string }>,
    ) {
        if (frozen || tallyActive.current || loading) return;
        trigger.current = document.activeElement as HTMLElement;
        const surcharge = purchase.choices
            .flatMap((group) => group.options)
            .filter((option) => selection.includes(option.key))
            .reduce((sum, option) => sum + option.surcharge, 0);
        const payment =
            paid.trim() === "" ? "" : String(Number(paid) + surcharge);
        setDraft({
            auto: true,
            question: null,
            dialog: null,
            values: {
                ...navigationValues(),
                action: "buy",
                thing: purchase.key,
                display_name: purchase.name,
                display_details: JSON.stringify([
                    ...purchase.choices
                        .flatMap((group) => group.options)
                        .filter((option) => selection.includes(option.key))
                        .map((option) => option.name),
                    ...parts.map(
                        (part) =>
                            `${purchase.parts.find((option) => option.key === part.key)?.name || "Weapon profile"}: ${part.paid || "quoted price"}${part.paid ? "¢" : ""}`,
                    ),
                ]),
                paid: payment,
                selection: JSON.stringify(selection),
                parts: JSON.stringify(parts),
            },
        });
        setGeneration((value) => value + 1);
    }
    function settled(outcome: EquipOutcome) {
        setPage(outcome.page);
        if (tallyActive.current && tallyQueue.current.length) {
            setDraft(tallyQueue.current.shift()!);
            setGeneration((value) => value + 1);
            return;
        }
        tallyActive.current = false;
        setTallyMode(false);
        setFrozen(false);
        setNotice("");
        if (outcome.confirmation) {
            const question = outcome.confirmation;
            const values = {
                ...navigationValues(),
                ...Object.fromEntries(question.carry),
                confirmed: question.confirm_value,
                rate: question.checkbox
                    ? question.checkbox.checked
                        ? question.checkbox.value
                        : ""
                    : new URLSearchParams(question.carry).get("rate") || "",
            };
            setDraft({ auto: false, dialog: null, question, values });
        } else {
            setDraft(null);
            window.history.replaceState(
                window.history.state,
                "",
                outcome.page.listingHref,
            );
            returnFocus.current = true;
        }
        setGeneration((value) => value + 1);
    }
    function dismiss() {
        if (frozen) return;
        returnFocus.current = true;
        setDraft(null);
        setGeneration((value) => value + 1);
        window.history.replaceState(window.history.state, "", page.listingHref);
    }
    return (
        <div
            ref={root}
            onClick={open}
            onClickCapture={(event) => {
                if (
                    (frozen || tallyActive.current) &&
                    (event.target as Element).closest("a[href]")
                )
                    event.preventDefault();
            }}
            onSubmitCapture={(event) => {
                if (
                    (frozen || tallyActive.current) &&
                    !(event.target as Element).closest(
                        "dialog, [data-equip-command]",
                    )
                )
                    event.preventDefault();
            }}
        >
            <WorkflowLayout
                fullWidth={!!page.model}
                title={page.model?.name || "Equip"}
                trailing={
                    page.model ? (
                        <QuickSwitcher {...page.model.switcher} />
                    ) : undefined
                }
                headingRef={heading}
                lead={
                    page.model?.role ||
                    (page.model
                        ? undefined
                        : "Buy equipment for the stash, manage it here or move it to a model.")
                }
                breadcrumb={
                    <Breadcrumbs
                        items={[
                            { label: <UserLink {...page.owner} /> },
                            { label: page.gangName, href: page.gangHref },
                            { label: page.model?.name || "Equip" },
                        ]}
                    />
                }
                actions={<GangFigures data={page.figures} />}
                footer={null}
            >
                {page.model && (
                    <EquipmentModel
                        model={page.model}
                        csrfToken={page.csrfToken}
                        frozen={frozen || loading}
                        countersFrozen={loading || (frozen && !tallyMode)}
                        onTally={(assignment, change, name) => {
                            if ((frozen && !tallyActive.current) || loading)
                                return;
                            trigger.current =
                                document.activeElement as HTMLElement;
                            const step: EquipDraft = {
                                auto: true,
                                question: null,
                                dialog: null,
                                values: {
                                    ...navigationValues(),
                                    action: "tally",
                                    assignment,
                                    change: String(change),
                                    display_name: name,
                                    display_details: JSON.stringify([
                                        `Recorded counter change: ${change > 0 ? "+" : ""}${change}.`,
                                    ]),
                                },
                            };
                            if (tallyActive.current) {
                                tallyQueue.current.push(step);
                                return;
                            }
                            tallyActive.current = true;
                            setTallyMode(true);
                            setQueueNotice("");
                            setDraft(step);
                            setGeneration((value) => value + 1);
                        }}
                    />
                )}
                {page.messages.map((message, index) => (
                    <Alert key={`${generation}:${index}`} tone={message.tone}>
                        {message.text}
                    </Alert>
                ))}
                {queueNotice && !draft && (
                    <Alert tone="warning">{queueNotice}</Alert>
                )}
                {notice && (
                    <Alert tone="error">
                        {notice}{" "}
                        {retry && (
                            <Button
                                size="sm"
                                onClick={() => void refreshPanel(retry)}
                            >
                                Try again
                            </Button>
                        )}{" "}
                        <ButtonLink href={page.signInHref} size="sm">
                            Sign in
                        </ButtonLink>
                    </Alert>
                )}
                {loading && <p role="status">Loading equipment details…</p>}
                <div className="mt-6 grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-[11rem_minmax(0,1fr)]">
                    <aside className="flex flex-col gap-4 self-start">
                        <EquipmentRail tabs={page.scopeTabs} />
                        {page.model && (
                            <EquipmentBudget
                                model={page.model}
                                tradePointsHref={page.tradePointsHref}
                            />
                        )}
                        {page.scope === "all" && (
                            <div className="self-start rounded-box border border-box-border p-3">
                                <p className="text-sm font-medium">
                                    Every item in the library
                                </p>
                                <p className="mt-0.5 text-xs text-muted">
                                    Includes equipment outside the gang's lists.
                                    Equipment on those lists uses their prices.
                                    Other equipment uses the Trading Post price,
                                    or its standard price if it is absent from
                                    the Trading Post.
                                </p>
                            </div>
                        )}
                        {page.postIsShut && page.tradePointsHref && (
                            <div className="self-start rounded-box border border-box-border p-3">
                                <p className="text-sm font-medium">
                                    Not tracking trade points
                                </p>
                                <p className="mt-0.5 text-xs text-muted">
                                    Start a Trading Post visit to track trade
                                    points.
                                </p>
                                {page.foundingBlocksVisit ? (
                                    <>
                                        <Button
                                            size="xs"
                                            disabled
                                            aria-describedby="equip-visit-reason"
                                        >
                                            Set up Trading Post visit →
                                        </Button>
                                        <p
                                            id="equip-visit-reason"
                                            className="mt-1 text-xs text-muted"
                                        >
                                            Complete Spend founding TP first.
                                            You can have only one of these
                                            actions open at a time.
                                        </p>
                                    </>
                                ) : (
                                    <ButtonLink
                                        href={page.tradePointsHref}
                                        size="xs"
                                        variant="primary"
                                    >
                                        Set up Trading Post visit →
                                    </ButtonLink>
                                )}
                            </div>
                        )}
                        {!page.postIsShut &&
                            !page.visitingTradingPost &&
                            !page.model?.budget &&
                            page.tradePointsHref && (
                                <ButtonLink
                                    href={page.tradePointsHref}
                                    size="sm"
                                    variant="text"
                                >
                                    Track TP spend by starting an action →
                                </ButtonLink>
                            )}
                    </aside>
                    <CatalogueFrame
                        {...page}
                        key={page.scope}
                        noun="item"
                        plural="items"
                        sectionLabel="Equipment sections"
                        filters={page.scope !== "stash"}
                        categoriesOpen={!page.model}
                        empty={
                            page.scope === "stash"
                                ? "Nothing in the stash yet."
                                : page.model
                                  ? "No equipment lists yet. Choose Unrestricted to browse the library."
                                  : "No equipment lists yet. Choose Unrestricted to browse the library, or In stash to manage what the gang holds."
                        }
                        renderEntry={(entry) => (
                            <EquipmentRow
                                entry={entry}
                                expanded={openRows.has(entry.key)}
                                disabled={frozen || loading}
                                onExpand={() => {
                                    const opening = !openRows.has(entry.key);
                                    setOpenRows((previous) => {
                                        const next = new Set(previous);
                                        if (opening) next.add(entry.key);
                                        else next.delete(entry.key);
                                        return next;
                                    });
                                    const next = opening
                                        ? entry.key
                                        : expanded === entry.key
                                          ? ""
                                          : expanded;
                                    setExpanded(next);
                                    const url = new URL(window.location.href);
                                    if (next)
                                        url.searchParams.set("owned", next);
                                    else url.searchParams.delete("owned");
                                    window.history.replaceState(
                                        window.history.state,
                                        "",
                                        url,
                                    );
                                }}
                                draft={
                                    purchaseDrafts[entry.key] ??
                                    equipmentDraft(entry)
                                }
                                onDraftChange={(update) =>
                                    setPurchaseDrafts((previous) => ({
                                        ...previous,
                                        [entry.key]: update(
                                            previous[entry.key] ??
                                                equipmentDraft(entry),
                                        ),
                                    }))
                                }
                                ownedLabel={
                                    page.model ? "equipped" : "in stash"
                                }
                                onBuy={buy}
                            />
                        )}
                    />
                </div>
            </WorkflowLayout>
            <Command
                key={generation}
                page={page}
                draft={draft}
                onSettled={settled}
                onPage={setPage}
                onDismiss={dismiss}
                onFrozen={setFrozen}
                onQueueBlocked={stopTallyQueue}
                queueNotice={queueNotice}
            />
        </div>
    );
}
