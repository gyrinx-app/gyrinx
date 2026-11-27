import * as M from "./campaign-model.js";
import React, { useEffect, useState } from "react";
import {
    ChevronDown,
    Dices,
    Menu as MenuIcon,
    Share2,
    SunMoon,
} from "lucide-react";
import { Button } from "./controls.jsx";
import { Menu } from "./surface-controls.jsx";
import { Cotton } from "./campaign-cotton.jsx";
import templates from "./campaign-base.json";
import { campaignDescription } from "./campaign-data.js";
import {
    gangTypes,
    territories,
    territoryNames,
    gangIncome,
} from "./campaign-fixtures.js";

export function CampaignCard({
    title,
    action,
    children,
    className = "",
    headingControl,
}) {
    return (
        <Cotton
            name={headingControl ? "managementSection" : "section"}
            bindings={{ SECTION_TITLE: title, SECTION_CLASS: className }}
            slots={{
                actions: action,
                content: children,
                "heading-control": headingControl,
            }}
        />
    );
}
export function CampaignFrame({ children }) {
    return (
        <>
            <style>
                {templates.layoutStyle.replaceAll(":root", ".cp-page")}
            </style>
            <Cotton name="layout" slots={{ content: children }} />
        </>
    );
}
export function CampaignNavigation({ state, dark, setDark, navigate }) {
    return (
        <Cotton
            name="nav"
            slots={{
                switcher: (
                    <Menu
                        label="Switch campaign"
                        icon={ChevronDown}
                        text={
                            <span
                                className="cp-nav-campaign-name"
                                title={state.name}
                            >
                                {state.name}
                            </span>
                        }
                    >
                        <a href="/campaign/">{state.name}</a>
                    </Menu>
                ),
                actions: (
                    <>
                        <Button
                            icon={SunMoon}
                            title="Toggle theme"
                            aria-label="Toggle theme"
                            onClick={() => setDark(!dark)}
                        />
                        <Menu label="Open account menu" text="louis">
                            <button onClick={() => navigate("dashboard")}>
                                Campaign dashboard
                            </button>
                            <a href="/gang/">Gang demo</a>
                        </Menu>
                    </>
                ),
                navigation: (
                    <Menu label="Open navigation menu" icon={MenuIcon}>
                        <button onClick={() => navigate("dashboard")}>
                            Campaigns
                        </button>
                        <button onClick={() => navigate("schedule")}>
                            Phases & cycles
                        </button>
                        <button onClick={() => navigate("battles")}>
                            Battles
                        </button>
                        <a href="/gang/">Gangs</a>
                    </Menu>
                ),
            }}
        />
    );
}
export function CampaignSubpageHeader({ state, tab, navigate }) {
    const title =
        {
            schedule: "Phases & cycles",
            battles: "Battles",
            activity: "Campaign log",
        }[tab] || state.name;
    return (
        <>
            <Cotton
                name="header"
                bindings={{ PAGE_TITLE: title }}
                slots={{
                    breadcrumb: (
                        <Cotton
                            name="editBreadcrumbs"
                            bindings={{
                                CAMPAIGN_NAME: state.name,
                                PAGE_NAME: title,
                            }}
                        />
                    ),
                    actions: (
                        <Button
                            variant="default"
                            onClick={() => navigate("dashboard")}
                        >
                            Back to campaign
                        </Button>
                    ),
                }}
            />
        </>
    );
}
export function CampaignActivity({ state, all = false }) {
    return (
        <ol className="divide-y divide-box-border text-sm">
            {(all ? state.entries : state.entries.slice(0, 8)).map((e) => (
                <li key={e.id} className="py-3 first:pt-0">
                    <div className="text-xs text-muted mb-1">
                        louis ·{" "}
                        {e.cycleName ||
                            state.cycles.find((c) => c.id === e.cycle)?.name}
                    </div>
                    <p>{e.text}</p>
                </li>
            ))}
        </ol>
    );
}
export function CampaignPeriod({ state, rewardTable, navigate }) {
    const cycle = state.cycles.find((c) => c.id === state.currentCycle),
        phase = state.phases.find((p) => p.id === state.currentPhase),
        countdown = M.phaseCountdown(state),
        automaticLabel = M.automaticChangeLabel(state, { showTimeZone: false }),
        startedDate = !state.ended && M.cycleStartedDate(state, cycle);
    const scheduleUrl = new URL(location.href);
    scheduleUrl.searchParams.set("view", "schedule");
    function openSchedule(e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        navigate("schedule");
    }
    return (
        <div className="cp-period" aria-label="Current campaign period">
            <div className="cp-period-facts">
                <div>
                    <div className="text-xs text-muted mb-1">Phase</div>
                    <h3 className="text-xl font-semibold">
                        <a
                            href={scheduleUrl.href}
                            onClick={openSchedule}
                            className="text-accent-text hover:underline"
                        >
                            {state.ended ? "Post-campaign" : phase.name}
                        </a>
                    </h3>
                    {!state.ended && phase.description && (
                        <p className="text-sm text-muted mt-1">
                            {phase.description}
                        </p>
                    )}
                    {countdown && (
                        <p className="text-xs text-muted mt-2">{`${countdown.cycles} ${countdown.cycles === 1 ? "cycle" : "cycles"} until next phase: ${countdown.phase.name}`}</p>
                    )}
                </div>
                <div>
                    <div className="text-xs text-muted mb-1">
                        {state.ended
                            ? "Campaign complete"
                            : `Cycle ${cycle.number}${state.limit === null ? " · No cycle limit" : ` of ${state.limit}`}`}
                    </div>
                    <h3 className="text-xl font-semibold">
                        <a
                            href={scheduleUrl.href}
                            onClick={openSchedule}
                            className="text-accent-text hover:underline"
                        >
                            {state.ended
                                ? `${state.cycles.length} ${state.cycles.length === 1 ? "cycle" : "cycles"}`
                                : cycle.name}
                        </a>
                    </h3>
                    {automaticLabel && (
                        <p className="text-xs text-muted mt-1">
                            {automaticLabel}
                        </p>
                    )}
                    {startedDate && (
                        <p className="text-xs text-muted mt-1">{startedDate}</p>
                    )}
                    {!state.ended && cycle.description && (
                        <p className="text-sm text-muted mt-1">
                            {cycle.description}
                        </p>
                    )}
                </div>
            </div>
            <details className="cp-period-effects">
                <summary className="cursor-pointer text-sm font-medium">
                    Effects and battle rewards
                </summary>
                <div className="cp-period-effects-body space-y-4">
                    <section className="space-y-3" aria-label="From the phase">
                        <h4 className="text-sm font-semibold">
                            From the phase · {phase.name}
                        </h4>
                        <p className="text-sm">
                            {phase.effects || "No additional phase effects."}
                        </p>
                        {rewardTable}
                    </section>
                    <section
                        className="border-t border-box-border pt-4 space-y-2"
                        aria-label="From the cycle"
                    >
                        <h4 className="text-sm font-semibold">
                            From the cycle · {cycle.name}
                        </h4>
                        <p className="text-sm">
                            {cycle.effects ||
                                "No additional cycle effects or battle rewards."}
                        </p>
                    </section>
                </div>
            </details>
        </div>
    );
}
function CampaignGangs({ state }) {
    return (
        <Cotton
            name="gangs"
            slots={{
                bodies: state.gangs.map((g) => (
                    <Cotton
                        key={g.id}
                        name="gangBody"
                        bindings={{
                            GANG_NAME: g.name,
                            GANG_TYPE: gangTypes[g.id] || "Custom gang",
                            OWNER: g.owner,
                            GANG_COLOUR: g.colour,
                            RATING: g.rating,
                            CREDITS: g.credits,
                            WEALTH: g.rating + g.credits,
                            REPUTATION: g.reputation,
                            INCOME: gangIncome(g.id),
                            TERRITORIES: territoryNames(g.id) || "—",
                        }}
                    />
                )),
            }}
        />
    );
}
function CampaignAssets({ state }) {
    return (
        <Cotton
            name="assets"
            bindings={{
                ASSET_HELD: territories.filter((t) => t[1]).length,
                ASSET_UNCLAIMED: territories.filter((t) => !t[1]).length,
            }}
            slots={{
                entries: territories.map(([name, holder, income]) => (
                    <Cotton
                        key={name}
                        name={holder ? "assetRow" : "unclaimedAssetRow"}
                        bindings={{
                            ASSET_NAME: name,
                            ASSET_INCOME: income || "—",
                            ASSET_HOLDER:
                                state.gangs.find((g) => g.id === holder)
                                    ?.name || "Unclaimed",
                        }}
                    />
                )),
            }}
        />
    );
}
function CampaignDescription() {
    const [expanded, setExpanded] = useState(false);
    return (
        <>
            <div
                id="campaign-description-text"
                className="space-y-3 text-sm text-muted"
            >
                {(expanded
                    ? campaignDescription
                    : campaignDescription.slice(0, 1)
                ).map((text) => (
                    <p key={text}>{text}</p>
                ))}
            </div>
            <div className="mt-3">
                <Button
                    variant="text"
                    aria-expanded={expanded}
                    aria-controls="campaign-description-text"
                    onClick={() => setExpanded(!expanded)}
                >
                    {expanded ? "Hide description" : "Read full description"}
                </Button>
            </div>
        </>
    );
}
function useMediaQuery(value) {
    const [matches, setMatches] = useState(() => matchMedia(value).matches);
    useEffect(() => {
        const query = matchMedia(value);
        const update = () => setMatches(query.matches);
        query.addEventListener("change", update);
        update();
        return () => query.removeEventListener("change", update);
    }, [value]);
    return matches;
}
export function CampaignDashboard({
    state,
    arbitrator,
    navigate,
    setModal,
    reopen,
    onShare,
    battles,
    rewardTable,
}) {
    const mobile = useMediaQuery("(max-width: 767px)");
    const actionsInHeading = useMediaQuery(
        `(min-width: ${arbitrator ? 768 : 640}px) and (max-width: 1199px)`,
    );
    const duration =
        state.limit === null
            ? "Unlimited"
            : `Fixed · ${state.cycles.length} scheduled ${state.cycles.length === 1 ? "cycle" : "cycles"}`;
    const status = M.campaignStatus(state);
    const metadata = (
        <Cotton name="metadata" bindings={{ CAMPAIGN_DURATION: duration }} />
    );
    const actions = (
        <div className="cp-period-actions" aria-label="Campaign actions">
            {arbitrator && !state.ended && (
                <Button
                    variant="primary"
                    onClick={() => setModal({ kind: "end-cycle" })}
                >
                    {M.endCycleLabel(state)}
                </Button>
            )}
            {arbitrator && state.ended && (
                <Button variant="primary" onClick={reopen}>
                    Reopen campaign
                </Button>
            )}
            {arbitrator && (
                <Button variant="default" onClick={() => navigate("schedule")}>
                    Edit
                </Button>
            )}
            <Button
                variant="default"
                icon={Dices}
                title="Log a dice roll"
                aria-label="Log a dice roll"
                onClick={() => setModal({ kind: "roll" })}
            />
            <Menu label="More actions">
                <button onClick={() => navigate("schedule")}>
                    {arbitrator
                        ? "Manage phases & cycles"
                        : "View phases & cycles"}
                </button>
            </Menu>
        </div>
    );
    return (
        <Cotton
            name="campaign"
            bindings={{
                CAMPAIGN_NAME: state.name,
                CAMPAIGN_CLASS: arbitrator
                    ? "cp-campaign-arbitrator"
                    : "cp-campaign-player",
                CAMPAIGN_NAME_CLASS:
                    state.name.length > 60
                        ? "cp-campaign-name-long cp-campaign-name-longer"
                        : state.name.length > 30
                          ? "cp-campaign-name-long"
                          : "",
                CAMPAIGN_DURATION: duration,
                GANG_COUNT: state.gangs.length,
                GANG_NOUN: state.gangs.length === 1 ? "gang" : "gangs",
                BATTLE_COUNT: state.battles.length,
                CYCLE_COUNT: state.cycles.length,
            }}
            slots={{
                "arbitrator-line": (
                    <p className="cp-campaign-byline text-sm text-muted mt-2">
                        <span>
                            <span>Arbitrator</span>: louis
                        </span>
                        <span
                            className="cp-campaign-status"
                            data-status={status.key}
                        >
                            <span aria-hidden="true">·</span>
                            {status.label}
                            <Cotton name="statusDot" />
                        </span>
                    </p>
                ),
                metadata: !mobile && metadata,
                description: mobile ? (
                    <details className="cp-campaign-mobile-info">
                        <summary className="cursor-pointer text-sm font-medium">
                            Campaign information
                        </summary>
                        <div className="cp-period-effects-body space-y-4">
                            {metadata}
                            <div className="space-y-3 text-sm text-muted">
                                {campaignDescription.map((text) => (
                                    <p key={text}>{text}</p>
                                ))}
                            </div>
                        </div>
                    </details>
                ) : (
                    <CampaignDescription />
                ),
                breadcrumb: (
                    <Cotton
                        name="breadcrumbs"
                        bindings={{ CAMPAIGN_NAME: state.name }}
                    />
                ),
                arbitrator: <span>louis</span>,
                share: (
                    <Button
                        icon={Share2}
                        title="Share campaign"
                        aria-label="Share campaign"
                        onClick={onShare}
                    />
                ),
                actions: !actionsInHeading && actions,
                "heading-actions": actionsInHeading && actions,
                period: (
                    <CampaignPeriod
                        state={state}
                        rewardTable={rewardTable}
                        navigate={navigate}
                    />
                ),
                gangs: <CampaignGangs state={state} />,
                assets: <CampaignAssets state={state} />,
                battles,
                "battles-actions": !state.ended && (
                    <Button
                        variant="primary"
                        onClick={() => setModal({ kind: "battle" })}
                    >
                        Record a battle
                    </Button>
                ),
                activity: <CampaignActivity state={state} />,
                "log-actions": (
                    <>
                        <Button
                            variant="default"
                            icon={Dices}
                            onClick={() => setModal({ kind: "roll" })}
                        >
                            Log a dice roll
                        </Button>
                        <Button
                            variant="default"
                            onClick={() => navigate("activity")}
                        >
                            Full log
                        </Button>
                    </>
                ),
                players: (
                    <Cotton
                        name="table"
                        slots={{
                            content: (
                                <>
                                    <thead>
                                        <tr>
                                            <th>Player</th>
                                            <th className="text-right">
                                                Invitation
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {state.gangs.map((g) => (
                                            <tr key={g.id}>
                                                <td className="font-semibold">
                                                    {g.owner}
                                                </td>
                                                <td className="text-right">
                                                    <Cotton name="acceptedBadge" />
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </>
                            ),
                        }}
                    />
                ),
            }}
        />
    );
}
export function CampaignBattles({ battles, state, onView }) {
    return (
        <ul className="divide-y divide-box-border">
            {battles.length ? (
                battles.map((b) => {
                    const participants = [...b.participants].sort((a, z) =>
                            a === b.winner ? -1 : z === b.winner ? 1 : 0,
                        ),
                        first = state.gangs.find(
                            (g) => g.id === participants[0],
                        ),
                        second = state.gangs.find(
                            (g) => g.id === participants[1],
                        );
                    return (
                        <React.Fragment key={b.id}>
                            <Cotton
                                name="battleRow"
                                rootProps={{
                                    onClick: (e) => {
                                        if (e.target.closest("a")) {
                                            e.preventDefault();
                                            onView(b);
                                        }
                                    },
                                }}
                                bindings={{
                                    BATTLE_TITLE: b.name,
                                    BATTLE_RESULT:
                                        b.winner === "draw"
                                            ? "Draw"
                                            : "Victory",
                                    BATTLE_DATE: "",
                                    BATTLE_DATE_LABEL: "",
                                    FIRST_GANG: first.name,
                                    SECOND_GANG: second.name,
                                    FIRST_COLOUR: first.colour,
                                    SECOND_COLOUR: second.colour,
                                }}
                                slots={{
                                    winner:
                                        b.winner !== "draw" ? (
                                            <Cotton name="trophy" />
                                        ) : null,
                                    period: (
                                        <p className="mt-2 text-xs text-muted">
                                            {b.cycleName} · {b.phaseName}
                                        </p>
                                    ),
                                }}
                            />
                        </React.Fragment>
                    );
                })
            ) : (
                <li className="p-4 text-sm text-muted">
                    No battles in this cycle yet.
                </li>
            )}
        </ul>
    );
}
