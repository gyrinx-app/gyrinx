import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
    Timeline as TimelineIcon,
    Undo2,
    Redo2,
    History,
    ChevronDown,
    GitFork,
    RotateCwFadingClock,
    Camera,
    SunMoon,
    Menu as MenuIcon,
    Plus,
    ArrowRight,
    Dices,
} from "lucide-react";
import { Button, Icon } from "./controls.jsx";
import cotton from "./cotton.json";
import * as M from "./history-model.js";
import { base, fullDate, localDate } from "./history-format.js";
import {
    UserLink,
    GangLink,
    Menu,
    Modal,
    Select,
    Input,
    PageHeader,
    SearchBar,
    Snapshot,
    DateFilters,
    useHistoryIndexes,
} from "./history-ui.jsx";
import {
    BranchTimeline,
    Timeline,
    CampaignHistory,
} from "./history-timeline.jsx";
import { loadDemoHistory } from "./history-demo.js";
const C = cotton.history;
function App() {
    const [root, setRoot] = useState(loadDemoHistory),
        [params, setParams] = useState(
            () => new URLSearchParams(location.search),
        ),
        [draft, setDraft] = useState(() =>
            Object.fromEntries(new URLSearchParams(location.search)),
        ),
        [graph, setGraph] = useState(
            () =>
                new URLSearchParams(location.search).get("view") === "timeline",
        ),
        [modal, setModal] = useState(null),
        [notice, setNotice] = useState(""),
        [error, setError] = useState(""),
        [cloneName, setCloneName] = useState("");
    const [dark, setDark] = useState(
        () => localStorage.getItem("gyrinx-history-theme") === "dark",
    );
    const viewer = params.get("viewer") === "mira" ? "mira" : "louis",
        route = location.pathname;
    const campaign = route === `${base}campaign/`,
        rollPage = route === `${base}campaign/roll/`;
    const snapshotMatch = route.match(
            /^\/history\/gang\/([^/]+)\/snapshots\/([^/]+)\/$/,
        ),
        sheetMatch = route.match(/^\/history\/gang\/([^/]+)\/sheet\/$/),
        gangMatch = route.match(/^\/history\/gang\/([^/]+)\/$/);
    const detail = route.match(
        /^\/history\/(users|models|battles)\/([^/]+)\/$/,
    );
    const ownGang = Object.keys(M.gangs).find(
        (id) => M.gangs[id].owner === viewer,
    );
    const gangId =
        snapshotMatch?.[1] ||
        sheetMatch?.[1] ||
        gangMatch?.[1] ||
        (campaign || rollPage ? ownGang : "nightshade");
    const indexes = useHistoryIndexes(root);
    const gang = M.gangs[gangId],
        state = M.historyFor(root, gangId);
    const clone = M.allClones(root).find((c) => c.id === gangId);
    const selected =
        snapshotMatch && state
            ? M.version(state, snapshotMatch[2]) ||
              state.journal.find((e) => e.id === snapshotMatch[2])
            : null;
    const staticPage = !!snapshotMatch,
        livePage = !!sheetMatch || !!clone,
        owns = state && M.ownerOf(state) === viewer;
    const snapshot =
        clone?.snapshot ||
        selected?.snapshot ||
        (state ? M.current(state) : null);
    const viewerQuery = () => `viewer=${viewer}`;
    const withViewer = (url) =>
        `${url}${url.includes("?") ? "&" : "?"}${viewerQuery()}`;
    const historyUrl = (id = gangId) => withViewer(`${base}gang/${id}/`);
    const snapshotUrl = (e) =>
        withViewer(`${base}gang/${e.gang}/snapshots/${e.id}/`);
    const permalink = (e) =>
        `${withViewer(e.gang ? `${base}gang/${e.gang}/?entry=${encodeURIComponent(e.id)}` : `${base}campaign/?entry=${encodeURIComponent(e.id)}`)}${graph && !campaign ? "&view=timeline" : ""}#entry-${e.id}`;
    const versionTarget = (e) => (e.type === "restore" ? e.id : e.to || e.id);
    const [roll, setRoll] = useState({
        reason: "",
        dice: "2",
        source: "generate",
        results: "",
        modifier: "",
        gang: ownGang,
        battle: "",
        outcome: "",
    });
    useEffect(() => {
        document.querySelector("#history-root").classList.toggle("dark", dark);
        localStorage.setItem("gyrinx-history-theme", dark ? "dark" : "light");
    }, [dark]);
    useEffect(() => {
        const pop = () => {
            const next = new URLSearchParams(location.search);
            setParams(next);
            setDraft(Object.fromEntries(next));
        };
        window.addEventListener("popstate", pop);
        window.addEventListener("hashchange", pop);
        return () => {
            window.removeEventListener("popstate", pop);
            window.removeEventListener("hashchange", pop);
        };
    }, []);
    function clearDeepLink() {
        if (!params.has("entry") && !location.hash.startsWith("#entry-"))
            return;
        const next = new URLSearchParams(params);
        next.delete("entry");
        next.delete("page");
        history.replaceState(
            null,
            "",
            `${route}${next.size ? `?${next}` : ""}`,
        );
        setParams(next);
        setDraft((d) => {
            const copy = { ...d };
            delete copy.entry;
            return copy;
        });
    }
    function handleInteraction(e) {
        if (e.target.closest("button, summary, input, select, textarea"))
            clearDeepLink();
    }
    function save(next, message, destination) {
        clearDeepLink();
        setRoot(next);
        setNotice(message);
        setModal(null);
        try {
            localStorage.setItem(M.STORAGE_KEY, JSON.stringify(next));
            setError("");
        } catch {
            setError(
                "Browser storage is full. Changes will last until this page is closed.",
            );
            return;
        }
        if (destination) location.assign(withViewer(destination));
    }
    function changeGang(id, fn, message, destination) {
        try {
            save(M.updateGang(root, id, fn), message, destination);
        } catch (e) {
            setError(e.message);
        }
    }
    function open(type, entry) {
        if (entry.type === "restore") return;
        const s = M.historyFor(root, entry.gang);
        if (!s || M.ownerOf(s) !== viewer) return;
        if (type === "highlight") {
            changeGang(
                entry.gang,
                (s) => M.highlight(s, entry.id, viewer),
                M.isHighlighted(s, entry.id, viewer)
                    ? "Highlight removed."
                    : "Action highlighted.",
            );
            return;
        }
        setCloneName(`${entry.snapshot.name} (copy)`);
        setModal({ type, entry });
    }
    function restoreEntry(entry) {
        changeGang(
            entry.gang,
            (s) =>
                M.restore(
                    s,
                    versionTarget(entry),
                    viewer,
                    entry.when,
                    entry.id,
                ),
            "Gang restored.",
        );
    }
    function cloneEntry(entry) {
        try {
            const next = M.updateGang(root, entry.gang, (s) =>
                M.cloneVersion(
                    s,
                    versionTarget(entry),
                    cloneName,
                    viewer,
                    entry.when,
                ),
            );
            const made = M.historyFor(next, entry.gang).clones.at(-1);
            save(next, "Gang cloned.", `${base}gang/${made.id}/`);
        } catch (e) {
            setError(e.message);
        }
    }
    function redoAction() {
        if (M.children(state).length > 1) {
            setModal({ type: "redo" });
            return;
        }
        changeGang(
            gangId,
            (s) => M.redo(s, undefined, viewer),
            "Action redone.",
        );
    }
    function applyFilters(e) {
        e.preventDefault();
        const next = new URLSearchParams();
        if (viewer === "mira") next.set("viewer", viewer);
        for (const [k, v] of Object.entries(draft))
            if (v && !["entry", "page", "viewer"].includes(k)) next.set(k, v);
        history.pushState(null, "", `${route}?${next}`);
        setParams(next);
    }
    function setFilter(k, v) {
        setDraft((d) => ({ ...d, [k]: v }));
    }
    const all = campaign
        ? M.entries(root, true)
        : state
          ? M.entries(state)
          : [];
    const filterKeys = [
        "q",
        "kind",
        "player",
        "gang",
        "model",
        "battle",
        "from_date",
        "to_date",
        "state",
    ];
    const narrowed = filterKeys.some((k) => params.get(k));
    const filtered = all.filter((e) => {
        const s = e.gang ? M.historyFor(root, e.gang) : null;
        const index = indexes.get(e.gang);
        const inactive = index?.versions.has(e.id) && !index.active.has(e.id);
        const marked = s && M.isHighlighted(s, e.id, viewer);
        const q = (params.get("q") || "").toLowerCase();
        return (
            (!q ||
                [
                    e.description,
                    e.outcome,
                    e.model,
                    e.battle,
                    M.people[e.actor]?.name,
                    M.gangs[e.gang]?.name,
                ]
                    .join(" ")
                    .toLowerCase()
                    .includes(q)) &&
            (!params.get("kind") || e.category === params.get("kind")) &&
            (!params.get("player") || e.actor === params.get("player")) &&
            (!params.get("gang") || e.gang === params.get("gang")) &&
            (!params.get("model") || e.model === params.get("model")) &&
            (!params.get("battle") || e.battle === params.get("battle")) &&
            (!params.get("from_date") ||
                localDate(e.when) >= params.get("from_date")) &&
            (!params.get("to_date") ||
                localDate(e.when) <= params.get("to_date")) &&
            (!params.get("state") ||
                (params.get("state") === "highlighted"
                    ? marked
                    : params.get("state") === "undone"
                      ? inactive
                      : !inactive))
        );
    });
    const linked =
        params.get("entry") ||
        (location.hash.startsWith("#entry-") ? location.hash.slice(7) : null);
    const linkedIndex = filtered.findIndex((e) => e.id === linked);
    const shown = filtered;
    useEffect(() => {
        if (!linked) return;
        const el = document
            .querySelector("#history-root")
            .shadowRoot.getElementById(`entry-${linked}`);
        if (el) {
            el.scrollIntoView({ block: "center" });
            el.focus({ preventScroll: true });
        }
    }, [linked]);
    function jumpToEntry(id) {
        const next = new URLSearchParams(params);
        if (!filtered.some((entry) => entry.id === id)) {
            for (const key of filterKeys) next.delete(key);
        }
        next.delete("page");
        next.set("entry", id);
        history.pushState(null, "", `${route}?${next}#entry-${id}`);
        setParams(next);
        setDraft(Object.fromEntries(next));
        requestAnimationFrame(() => {
            const target = document
                .querySelector("#history-root")
                .shadowRoot.getElementById(`entry-${id}`);
            target?.scrollIntoView({ block: "center" });
            target?.focus({ preventScroll: true });
        });
    }
    const canHighlight = campaign ? !!ownGang : owns;
    const stateOptions = [
        ["", "All activity"],
        ["active", "Active"],
        ["undone", "Undone"],
        ...(canHighlight ? [["highlighted", "Highlighted"]] : []),
    ];
    const kinds = [
        ["", "All actions"],
        ["model", "Models"],
        ["kit", "Equipment"],
        ["credits", "Credits"],
        ["gang", "Gang changes"],
        ["history", "Restores"],
        ["dice", "Dice rolls"],
        ...(campaign ? [["campaign", "Campaign activity"]] : []),
    ];
    const models = [...new Set(all.map((e) => e.model).filter(Boolean))];
    const currentEntry = state ? M.version(state) : null;
    const topControls =
        owns && !staticPage && !clone && !rollPage && !detail ? (
            <div className="history-top-controls">
                <div className="flex flex-wrap items-center gap-2">
                    <Button
                        variant="default"
                        icon={Undo2}
                        disabled={!currentEntry.parent}
                        onClick={() =>
                            changeGang(
                                gangId,
                                (s) => M.undo(s, viewer),
                                "Action undone.",
                            )
                        }
                    >
                        Undo
                    </Button>
                    <Button
                        variant="default"
                        icon={Redo2}
                        disabled={!M.children(state).length}
                        onClick={redoAction}
                    >
                        Redo
                    </Button>
                    <Button
                        variant="default"
                        icon={Plus}
                        onClick={() =>
                            changeGang(
                                gangId,
                                (s) => M.generateDemoActions(s, 10, viewer),
                                "10 demo actions generated.",
                            )
                        }
                    >
                        Generate demo actions
                    </Button>
                    {campaign && (
                        <span className="text-sm text-muted">{gang.name}</span>
                    )}
                </div>
                {!campaign && (
                    <dl className="current-figures">
                        <div>
                            <dt>Rating</dt>
                            <dd data-testid="current-rating">
                                {M.current(state).rating}
                            </dd>
                        </div>
                        <div>
                            <dt>Credits</dt>
                            <dd>{M.current(state).credits}¢</dd>
                        </div>
                    </dl>
                )}
            </div>
        ) : null;
    const snapshotActions =
        selected && owns && selected.type !== "restore" ? (
            <>
                <Button
                    variant="primary"
                    icon={RotateCwFadingClock}
                    onClick={() => open("restore", selected)}
                >
                    Restore this version
                </Button>
                <Button
                    variant="default"
                    icon={GitFork}
                    onClick={() => open("clone", selected)}
                >
                    Clone this version
                </Button>
            </>
        ) : null;
    const rollLink = (
        <a
            className={cotton.button.primary}
            href={withViewer(`${base}campaign/roll/`)}
        >
            <Icon icon={Dices} size={16} />
            Log a dice roll
        </a>
    );
    function submitRoll(e) {
        e.preventDefault();
        setError("");
        try {
            const count = roll.dice === "D66" ? 2 : Number(roll.dice),
                results =
                    roll.source === "record"
                        ? roll.results
                              .split(/[\s,]+/)
                              .filter(Boolean)
                              .map(Number)
                        : undefined;
            const modifier = Number(roll.modifier) || 0;
            if (!Number.isInteger(modifier))
                throw Error("Enter a whole-number modifier.");
            const args = {
                reason: roll.reason,
                count,
                results,
                outcome: roll.outcome,
                battle: roll.battle,
                actor: viewer,
            };
            if (!roll.gang) {
                const temporary = M.addRoll(M.historyFor(root, ownGang), args);
                const e = {
                    ...temporary.versions.at(-1),
                    gang: undefined,
                    snapshot: undefined,
                    parent: undefined,
                    diceMode: roll.dice === "D66" ? "D66" : undefined,
                    modifier,
                };
                save(
                    {
                        ...root,
                        campaignRolls: [...(root.campaignRolls || []), e],
                    },
                    "Dice roll recorded.",
                    `${base}campaign/?entry=${e.id}`,
                );
            } else {
                const next = M.updateGang(root, roll.gang, (s) => {
                    const changed = M.addRoll(s, args);
                    Object.assign(changed.versions.at(-1), {
                        diceMode: roll.dice === "D66" ? "D66" : undefined,
                        modifier,
                    });
                    return changed;
                });
                const e = M.version(M.historyFor(next, roll.gang));
                save(
                    next,
                    "Dice roll recorded.",
                    `${base}campaign/?entry=${e.id}`,
                );
            }
        } catch (err) {
            setError(err.message);
        }
    }
    return (
        <div
            className={`history-page ${dark ? "dark" : ""}`}
            onClickCapture={handleInteraction}
            onChangeCapture={handleInteraction}
        >
            <header className={C.nav.root}>
                <div className={C.nav.inner}>
                    <a href={base} className={C.nav.brand}>
                        <img
                            src="/static/history/logo.svg"
                            width="24"
                            height="24"
                            alt=""
                        />
                        <span className="hidden sm:inline">Gyrinx</span>
                    </a>
                    <div className="history-nav-switcher">
                        <a
                            href={
                                campaign || rollPage
                                    ? withViewer(`${base}campaign/`)
                                    : historyUrl()
                            }
                        >
                            {campaign || rollPage
                                ? "The Ash Road"
                                : clone?.name || gang?.name || "Gangs"}
                        </a>
                        <Menu
                            label="Switch gang or campaign"
                            icon={ChevronDown}
                        >
                            <a href={historyUrl("nightshade")}>
                                Nightshade Coven
                            </a>
                            <a href={historyUrl("iron")}>Iron Vultures</a>
                            <a href={withViewer(`${base}campaign/`)}>
                                The Ash Road
                            </a>
                        </Menu>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                        <Button
                            icon={SunMoon}
                            aria-label="Toggle theme"
                            title="Toggle theme"
                            aria-pressed={dark}
                            onClick={() => setDark(!dark)}
                        />
                        <Menu label="Account menu" text={viewer}>
                            <button
                                onClick={() =>
                                    location.assign(`${route}?viewer=louis`)
                                }
                            >
                                Preview as louis
                            </button>
                            <button
                                onClick={() =>
                                    location.assign(`${route}?viewer=mira`)
                                }
                            >
                                Preview as mira
                            </button>
                        </Menu>
                        <span className="h-6 w-px bg-ink-700" />
                        <Menu label="Open navigation menu" icon={MenuIcon}>
                            <a href={historyUrl("nightshade")}>Gang history</a>
                            <a href={withViewer(`${base}campaign/`)}>
                                Campaign log
                            </a>
                            <a href={withViewer(`${base}campaign/roll/`)}>
                                Log a dice roll
                            </a>
                        </Menu>
                    </div>
                </div>
            </header>
            <main className="n26-site-container pt-4 pb-10" id="content">
                <div
                    className={`history-column ${staticPage || livePage ? "history-sheet" : ""}`}
                >
                    <PageHeader
                        title={
                            rollPage
                                ? "Log a dice roll"
                                : staticPage || livePage
                                  ? snapshot?.name || "Snapshot unavailable"
                                  : detail
                                    ? detail[1] === "users"
                                        ? M.people[detail[2]]?.name
                                        : detail[1] === "battles"
                                          ? "The Sump Crossing"
                                          : detail[2].replaceAll("-", " ")
                                    : campaign
                                      ? "Log"
                                      : "History"
                        }
                        lead={
                            rollPage
                                ? "Generate a roll or record a result you already rolled. Add an outcome note after saving."
                                : staticPage
                                  ? selected
                                      ? `Snapshot from ${fullDate(selected.when)}.`
                                      : "This snapshot could not be found."
                                  : clone
                                    ? `Cloned from the ${fullDate(clone.sourceWhen || M.version(M.historyFor(root, clone.gang), clone.source).when)} version.`
                                    : livePage
                                      ? M.version(state).type === "restore"
                                          ? `Restored to the ${fullDate(M.version(state).sourceWhen)} version.`
                                          : gang.house
                                      : detail
                                        ? ""
                                        : `Everything done ${campaign ? "in The Ash Road" : `to ${gang.name}`}, newest first.`
                        }
                        actions={
                            staticPage
                                ? snapshotActions
                                : !detail && !clone
                                  ? rollPage
                                      ? null
                                      : rollLink
                                  : null
                        }
                    >
                        <UserLink
                            id={
                                campaign || rollPage
                                    ? "mira"
                                    : clone?.owner || gang?.owner || viewer
                            }
                        />
                        <span>/</span>
                        {campaign || rollPage ? (
                            <>
                                <a href={withViewer(`${base}campaign/`)}>
                                    Campaigns
                                </a>
                                <span>/</span>
                                <a href={withViewer(`${base}campaign/`)}>
                                    The Ash Road
                                </a>
                            </>
                        ) : (
                            <a href={historyUrl(clone?.gang || gangId)}>
                                {clone?.name || gang?.name}
                            </a>
                        )}
                        <span>/</span>
                        <span aria-current="page">
                            {rollPage
                                ? "Log a dice roll"
                                : staticPage
                                  ? "Snapshot"
                                  : livePage
                                    ? "Gang"
                                    : detail
                                      ? "Details"
                                      : campaign
                                        ? "Log"
                                        : "History"}
                        </span>
                    </PageHeader>
                    {!campaign &&
                        !staticPage &&
                        !livePage &&
                        !rollPage &&
                        !detail && (
                            <div className="timeline-view-control">
                                <Button
                                    variant="default"
                                    icon={graph ? History : TimelineIcon}
                                    aria-pressed={graph}
                                    onClick={() => {
                                        const next = new URLSearchParams(
                                            params,
                                        );
                                        next.delete("entry");
                                        if (!graph)
                                            next.set("view", "timeline");
                                        else next.delete("view");
                                        history.replaceState(
                                            null,
                                            "",
                                            `${route}${next.size ? `?${next}` : ""}`,
                                        );
                                        setParams(next);
                                        setGraph((v) => !v);
                                    }}
                                >
                                    {graph ? "History" : "Timeline"}
                                </Button>
                            </div>
                        )}
                    {topControls}
                    {notice && (
                        <p className="history-notice" role="status">
                            {notice}
                        </p>
                    )}
                    {error && (
                        <p className={cotton.error} role="alert">
                            {error}
                        </p>
                    )}
                    {rollPage ? (
                        <form className="roll-form" onSubmit={submitRoll}>
                            <section className="flex flex-col gap-4">
                                <h2>The roll</h2>
                                <Input
                                    label="Reason *"
                                    value={roll.reason}
                                    onChange={(v) =>
                                        setRoll((r) => ({ ...r, reason: v }))
                                    }
                                    required
                                    maxLength={200}
                                    placeholder="e.g. Rare trade availability"
                                />
                                <Select
                                    label="Dice *"
                                    value={roll.dice}
                                    onChange={(v) =>
                                        setRoll((r) => ({ ...r, dice: v }))
                                    }
                                    options={[
                                        "1",
                                        "2",
                                        "3",
                                        "4",
                                        "5",
                                        "6",
                                        "D66",
                                    ].map((v) => [
                                        v,
                                        v === "D66" ? "D66" : `${v}D6`,
                                    ])}
                                />
                                <p className="text-sm text-muted">
                                    D66 uses two D6s, one for tens and one for
                                    units.
                                </p>
                                <Select
                                    label="Roll source"
                                    value={roll.source}
                                    onChange={(v) =>
                                        setRoll((r) => ({ ...r, source: v }))
                                    }
                                    options={[
                                        ["generate", "Generate a roll"],
                                        ["record", "Record a result"],
                                    ]}
                                />
                                {roll.source === "record" && (
                                    <Input
                                        label="Dice results *"
                                        value={roll.results}
                                        onChange={(v) =>
                                            setRoll((r) => ({
                                                ...r,
                                                results: v,
                                            }))
                                        }
                                        placeholder="e.g. 4, 2"
                                        required
                                    />
                                )}
                                <Input
                                    label="Modifier"
                                    type="number"
                                    step="1"
                                    value={roll.modifier}
                                    onChange={(v) =>
                                        setRoll((r) => ({ ...r, modifier: v }))
                                    }
                                />
                            </section>
                            <section className="flex flex-col gap-4">
                                <h2>Related to</h2>
                                <p className="text-sm text-muted">
                                    Optionally link this roll to a gang or
                                    battle in this campaign.
                                </p>
                                <Select
                                    label="Gang"
                                    value={roll.gang}
                                    onChange={(v) =>
                                        setRoll((r) => ({ ...r, gang: v }))
                                    }
                                    options={[
                                        ["", "No gang"],
                                        ...Object.entries(M.gangs)
                                            .filter(
                                                ([, g]) => g.owner === viewer,
                                            )
                                            .map(([id, g]) => [id, g.name]),
                                    ]}
                                />
                                <Select
                                    label="Battle"
                                    value={roll.battle}
                                    onChange={(v) =>
                                        setRoll((r) => ({ ...r, battle: v }))
                                    }
                                    options={[
                                        ["", "No battle"],
                                        [
                                            "The Sump Crossing",
                                            "The Sump Crossing",
                                        ],
                                    ]}
                                />
                                <Input
                                    label="Outcome"
                                    value={roll.outcome}
                                    onChange={(v) =>
                                        setRoll((r) => ({ ...r, outcome: v }))
                                    }
                                />
                            </section>
                            <footer>
                                <a
                                    href={withViewer(`${base}campaign/`)}
                                    className={cotton.button.default}
                                >
                                    Cancel
                                </a>
                                <Button variant="success" type="submit">
                                    Record roll
                                </Button>
                            </footer>
                        </form>
                    ) : staticPage || livePage ? (
                        snapshot ? (
                            <>
                                <div className="snapshot-banner">
                                    <Icon
                                        icon={staticPage ? Camera : History}
                                        size={16}
                                    />
                                    <span>
                                        {staticPage
                                            ? "Static snapshot"
                                            : clone
                                              ? "Cloned gang"
                                              : "Current gang"}
                                    </span>
                                    <a href={historyUrl(clone?.gang || gangId)}>
                                        View history
                                        <Icon icon={ArrowRight} size={13} />
                                    </a>
                                </div>
                                <Snapshot snapshot={snapshot} />
                            </>
                        ) : (
                            <p>No snapshot is available for this action.</p>
                        )
                    ) : detail ? (
                        <section className="detail-section">
                            {detail[1] === "users" ? (
                                <>
                                    <UserLink id={detail[2]} />
                                    <h2>Gangs</h2>
                                    <GangLink
                                        id={
                                            detail[2] === "louis"
                                                ? "nightshade"
                                                : "iron"
                                        }
                                    />
                                </>
                            ) : detail[1] === "battles" ? (
                                <>
                                    <p>
                                        Iron Vultures won against Nightshade
                                        Coven.
                                    </p>
                                    <a
                                        href={withViewer(
                                            `${base}campaign/?battle=The+Sump+Crossing`,
                                        )}
                                    >
                                        View battle activity
                                    </a>
                                </>
                            ) : (
                                <p>
                                    {[
                                        ...M.current(root).models,
                                        ...M.current(M.historyFor(root, "iron"))
                                            .models,
                                    ].find(
                                        (m) =>
                                            m.name
                                                .toLowerCase()
                                                .replaceAll(" ", "-") ===
                                            detail[2],
                                    )?.status || "Active"}
                                </p>
                            )}
                        </section>
                    ) : (
                        <>
                            <form
                                onSubmit={applyFilters}
                                className={
                                    campaign
                                        ? "campaign-log-filters"
                                        : "gang-log-filters"
                                }
                                aria-label="History filters"
                            >
                                {campaign ? (
                                    <>
                                        <div className="campaign-filter-grid">
                                            <Select
                                                label="Player or arbitrator"
                                                value={draft.player || ""}
                                                onChange={(v) =>
                                                    setFilter("player", v)
                                                }
                                                options={[
                                                    ["", "All players"],
                                                    ...Object.entries(
                                                        M.people,
                                                    ).map(([id, p]) => [
                                                        id,
                                                        p.name,
                                                    ]),
                                                ]}
                                            />
                                            <Select
                                                label="Gang"
                                                value={draft.gang || ""}
                                                onChange={(v) =>
                                                    setFilter("gang", v)
                                                }
                                                options={[
                                                    ["", "All gangs"],
                                                    ...Object.entries(
                                                        M.gangs,
                                                    ).map(([id, g]) => [
                                                        id,
                                                        g.name,
                                                    ]),
                                                ]}
                                            />
                                            <Select
                                                label="Action type"
                                                value={draft.kind || ""}
                                                onChange={(v) =>
                                                    setFilter("kind", v)
                                                }
                                                options={kinds}
                                            />
                                            <DateFilters
                                                values={draft}
                                                onChange={setFilter}
                                            />
                                        </div>
                                        <div className="supplementary-filters">
                                            <Select
                                                label="Show"
                                                compact
                                                value={draft.state || ""}
                                                onChange={(v) =>
                                                    setFilter("state", v)
                                                }
                                                options={stateOptions}
                                            />
                                            <Select
                                                label="Battle"
                                                compact
                                                value={draft.battle || ""}
                                                onChange={(v) =>
                                                    setFilter("battle", v)
                                                }
                                                options={[
                                                    ["", "Any battle"],
                                                    [
                                                        "The Sump Crossing",
                                                        "The Sump Crossing",
                                                    ],
                                                ]}
                                            />
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <SearchBar
                                            value={draft.q || ""}
                                            onChange={(v) => setFilter("q", v)}
                                        />
                                        <div className="gang-filter-grid">
                                            <Select
                                                label="Kind of act"
                                                compact
                                                value={draft.kind || ""}
                                                onChange={(v) =>
                                                    setFilter("kind", v)
                                                }
                                                options={kinds}
                                            />
                                            <Select
                                                label="Model"
                                                compact
                                                value={draft.model || ""}
                                                onChange={(v) =>
                                                    setFilter("model", v)
                                                }
                                                options={[
                                                    ["", "Any model"],
                                                    ...models.map((v) => [
                                                        v,
                                                        v,
                                                    ]),
                                                ]}
                                            />
                                            <Select
                                                label="Show"
                                                compact
                                                value={draft.state || ""}
                                                onChange={(v) =>
                                                    setFilter("state", v)
                                                }
                                                options={stateOptions}
                                            />
                                        </div>
                                        <DateFilters
                                            values={draft}
                                            onChange={setFilter}
                                        />
                                    </>
                                )}
                                <div className="filter-submit">
                                    <Button type="submit" variant="default">
                                        {campaign ? "Apply filters" : "Filter"}
                                    </Button>
                                    {narrowed && (
                                        <a
                                            href={withViewer(route)}
                                            className="text-sm"
                                        >
                                            {campaign
                                                ? "Clear filters"
                                                : "Clear"}
                                        </a>
                                    )}
                                    <span className="text-sm text-muted">
                                        {filtered.length} of {all.length}{" "}
                                        entries
                                    </span>
                                </div>
                            </form>
                            {linked && linkedIndex < 0 && (
                                <p role="status">
                                    The linked action is not in this filtered
                                    history.{" "}
                                    <a href={withViewer(route)}>
                                        Show all activity
                                    </a>
                                </p>
                            )}
                            {campaign ? (
                                <CampaignHistory
                                    entries={filtered}
                                    root={root}
                                    viewer={viewer}
                                    linked={linked}
                                    permalink={permalink}
                                    snapshotUrl={snapshotUrl}
                                    onAction={open}
                                    onRestoreTarget={jumpToEntry}
                                />
                            ) : graph ? (
                                <BranchTimeline
                                    entries={filtered}
                                    root={root}
                                    viewer={viewer}
                                    linked={linked}
                                    permalink={permalink}
                                    snapshotUrl={snapshotUrl}
                                    onAction={open}
                                    onRestoreTarget={jumpToEntry}
                                />
                            ) : (
                                <Timeline
                                    shown={shown}
                                    root={root}
                                    viewer={viewer}
                                    linked={linked}
                                    permalink={permalink}
                                    snapshotUrl={snapshotUrl}
                                    onAction={open}
                                    onRestoreTarget={jumpToEntry}
                                />
                            )}
                        </>
                    )}
                    <footer className="history-footer">
                        <a href={withViewer(base)}>Gang history</a>
                        <a href={withViewer(`${base}campaign/`)}>
                            Campaign log
                        </a>
                        <span>Local prototype</span>
                    </footer>
                </div>
            </main>
            {modal && (
                <Modal
                    title={
                        modal.type === "restore"
                            ? "Restore this version"
                            : modal.type === "clone"
                              ? "Clone this version"
                              : "Choose an action to redo"
                    }
                    onClose={() => setModal(null)}
                >
                    {modal.type === "redo" ? (
                        <div className="branch-choices">
                            {M.children(state).map((e) => (
                                <button
                                    key={e.id}
                                    onClick={() =>
                                        changeGang(
                                            gangId,
                                            (s) => M.redo(s, e.id, viewer),
                                            "Action redone.",
                                        )
                                    }
                                >
                                    <strong>{e.description}</strong>
                                    <span>{fullDate(e.when)}</span>
                                </button>
                            ))}
                        </div>
                    ) : modal.type === "restore" ? (
                        <>
                            <p>
                                Restore the gang to the{" "}
                                {fullDate(modal.entry.when)} version.
                            </p>
                            <dl className="snapshot-figures">
                                <div>
                                    <dt>Rating</dt>
                                    <dd>{modal.entry.snapshot.rating}</dd>
                                </div>
                                <div>
                                    <dt>Credits</dt>
                                    <dd>{modal.entry.snapshot.credits}¢</dd>
                                </div>
                                <div>
                                    <dt>Models</dt>
                                    <dd>
                                        {modal.entry.snapshot.models.length}
                                    </dd>
                                </div>
                            </dl>
                            <p className="text-sm text-muted">
                                Later actions remain in history and are marked
                                as undone by this restore.
                            </p>
                            <footer>
                                <Button
                                    variant="default"
                                    onClick={() => setModal(null)}
                                >
                                    Cancel
                                </Button>
                                <Button
                                    icon={RotateCwFadingClock}
                                    variant="success"
                                    onClick={() => restoreEntry(modal.entry)}
                                >
                                    Restore this version
                                </Button>
                            </footer>
                        </>
                    ) : (
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                cloneEntry(modal.entry);
                            }}
                        >
                            <p>
                                Create a gang from the{" "}
                                {fullDate(modal.entry.when)} version.
                            </p>
                            <Input
                                label="Gang name"
                                value={cloneName}
                                onChange={setCloneName}
                                required
                                maxLength={120}
                            />
                            <footer>
                                <Button
                                    variant="default"
                                    onClick={() => setModal(null)}
                                >
                                    Cancel
                                </Button>
                                <Button
                                    icon={GitFork}
                                    variant="success"
                                    type="submit"
                                >
                                    Clone this version
                                </Button>
                            </footer>
                        </form>
                    )}
                </Modal>
            )}
        </div>
    );
}
const host = document.querySelector("#history-root"),
    shadow = host.attachShadow({ mode: "open" }),
    style = document.createElement("link");
style.rel = "stylesheet";
style.href = host.dataset.themeUrl;
shadow.append(style);
const root = document.createElement("div");
shadow.append(root);
createRoot(root).render(<App />);
