import React, { useId, useState } from "react";
import {
    LayoutFreeform,
    ChevronDown,
    Users,
    SunMoon,
    Share2,
    ArrowRight,
    X,
    Menu,
    CircleHelp,
    ExternalLink,
    Flag,
    ListChecks,
    Backpack,
    Cat,
    Skull,
    Wrench,
} from "lucide-react";
import { Button, Icon, useModal } from "./controls.jsx";
import cotton from "./cotton.json";
import * as M from "./card-manager-model.js";
import {
    physical,
    mental,
    archetypes,
    profiles,
    weaponTraits,
} from "./gang-sheet-data.js";
function InfoDialog({ title, children, onClose }) {
    const ref = useModal();
    return (
        <dialog
            ref={ref}
            className={`${cotton.dialog.root} sheet-info-dialog`}
            aria-labelledby="sheet-info-title"
            onCancel={(e) => {
                e.preventDefault();
                onClose();
            }}
        >
            <header>
                <h2 id="sheet-info-title" className={cotton.dialog.title}>
                    {title}
                </h2>
                <Button
                    icon={X}
                    aria-label="Close"
                    title="Close"
                    onClick={onClose}
                />
            </header>
            <div className="sheet-info-content">{children}</div>
            <footer>
                <Button variant="default" onClick={onClose}>
                    Close
                </Button>
            </footer>
        </dialog>
    );
}
function Statline({ model, pet }) {
    const profile = profiles[model.id];
    const stats =
        profile?.stats ||
        (pet
            ? ["6″", "4+", "6+", "3", "3", "1", "3+", "2", "6+"]
            : ["5″", "4+", "4+", "3", "3", "1", "3+", "1", "6+"]);
    const mind = profile?.mind || ["7+", "7+", "7+", "7+"];
    return (
        <div className="gang-statline">
            <table aria-label={`${model.name} characteristics`}>
                <tbody>
                    <tr>
                        {physical.map((name) => (
                            <th scope="col" key={name}>
                                {name}
                            </th>
                        ))}
                    </tr>
                    <tr>
                        {stats.map((value, i) => (
                            <td key={i}>{value}</td>
                        ))}
                    </tr>
                    <tr className="gang-book-header">
                        {mental.map((name) => (
                            <th scope="col" key={name}>
                                {name}
                            </th>
                        ))}
                        <th scope="col" colSpan={4}>
                            Type
                        </th>
                        <th scope="col">XP</th>
                    </tr>
                    <tr className="gang-book-values">
                        {mind.map((value, i) => (
                            <td key={i}>{value}</td>
                        ))}
                        <td colSpan={4}>
                            {pet
                                ? "Fighter (Beast, Pet)"
                                : model.subtypes?.includes("Vehicle")
                                  ? "Vehicle"
                                  : `Fighter (${archetypes[model.rank] || "Ganger"})`}
                        </td>
                        <td>{profile?.xp || "0/–"}</td>
                    </tr>
                </tbody>
            </table>
        </div>
    );
}
function ModelDetails({ model, pet }) {
    const rows = [
        ...(model.counters || []),
        ["Skills", profiles[model.id]?.skills || "—"],
        ...(model.rules ? [["Rules", model.rules]] : []),
        ...(model.powers ? [["Powers", model.powers]] : []),
        ["Gear", pet ? "—" : (model.pets || []).join(", ") || "Flak armour"],
        ...(model.gearGroups || []),
        ...(!pet
            ? [["Gang legacy", <span className="gang-slot">House Escher</span>]]
            : []),
    ];
    return (
        <dl className="gang-model-details">
            {rows.map(([label, value]) => (
                <React.Fragment key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                </React.Fragment>
            ))}
        </dl>
    );
}
function ModelCard({ node, pet, owner, index }) {
    const [tab, setTab] = useState(0),
        id = useId();
    const model = pet
        ? {
              id: `${node.id}-pet-${index}`,
              name: pet,
              rating: 0,
              rank: 5,
              gear: "Claws and teeth",
          }
        : { ...M.models[node.id], id: node.id };
    const tabs = ["Card", "Lore", "Notes"];
    return (
        <article
            id={`model-${model.id}`}
            data-flip={`card-${model.id}`}
            className={`${cotton.card} gang-card gang-standard ${model.status ? "gang-inactive" : ""}`}
        >
            <header className="gang-card-header">
                <div className="gang-card-title">
                    <h2>
                        {model.name}
                        {pet && (
                            <span title={`Attached to ${owner}`}>
                                <Icon icon={Cat} size={13} />
                                <span className="cm-sr">
                                    Attached to {owner}
                                </span>
                            </span>
                        )}
                    </h2>
                    <div className="gang-header-marks">
                        {model.status && (
                            <span className="gang-status">
                                <Icon
                                    icon={
                                        model.status === "Dead" ? Skull : Wrench
                                    }
                                    size={12}
                                />
                                {model.status}
                            </span>
                        )}
                        <span className="gang-rating">{model.rating}¢</span>
                    </div>
                </div>
                {model.type && <div className="gang-profile">{model.type}</div>}
            </header>
            <div className="gang-card-controls">
                <div
                    className={`${cotton.tabs.rail} gang-standard-tabs`}
                    role="tablist"
                    aria-label={`${model.name} card sections`}
                    onKeyDown={(event) => {
                        const next =
                            event.key === "ArrowRight"
                                ? (tab + 1) % 3
                                : event.key === "ArrowLeft"
                                  ? (tab + 2) % 3
                                  : event.key === "Home"
                                    ? 0
                                    : event.key === "End"
                                      ? 2
                                      : null;
                        if (next !== null) {
                            event.preventDefault();
                            setTab(next);
                            event.currentTarget
                                .querySelectorAll("button")
                                [next].focus();
                        }
                    }}
                >
                    {tabs.map((name, i) => (
                        <button
                            key={name}
                            id={`${id}-tab-${i}`}
                            type="button"
                            role="tab"
                            aria-selected={tab === i}
                            aria-controls={`${id}-panel`}
                            tabIndex={tab === i ? 0 : -1}
                            className={`${cotton.tabs.button} ${tab === i ? cotton.tabs.active : cotton.tabs.inactive}`}
                            onClick={() => setTab(i)}
                        >
                            {name}
                        </button>
                    ))}
                </div>
            </div>
            <div
                id={`${id}-panel`}
                role="tabpanel"
                aria-labelledby={`${id}-tab-${tab}`}
                tabIndex={0}
            >
                {tab === 0 ? (
                    <>
                        <Statline model={model} pet={pet} />
                        <ModelDetails model={model} pet={pet} />
                        <div className="gang-weapons">
                            <table aria-label={`${model.name} weapons`}>
                                <thead>
                                    <tr>
                                        <th scope="col">Weapons</th>
                                        {["SR", "LR", "Str", "AP", "L"].map(
                                            (name) => (
                                                <th scope="col" key={name}>
                                                    {name}
                                                </th>
                                            ),
                                        )}
                                    </tr>
                                </thead>
                                <tbody>
                                    {model.gear
                                        .split(" · ")
                                        .map((weapon, i) => (
                                            <React.Fragment key={weapon}>
                                                <tr>
                                                    <td>{weapon}</td>
                                                    {(i === 0 && !pet
                                                        ? [
                                                              "6″",
                                                              "12″",
                                                              "3",
                                                              "–",
                                                              "1",
                                                          ]
                                                        : [
                                                              "E",
                                                              "–",
                                                              "S",
                                                              "–",
                                                              "1",
                                                          ]
                                                    ).map((value, j) => (
                                                        <td key={j}>{value}</td>
                                                    ))}
                                                </tr>
                                                {weaponTraits[weapon] && (
                                                    <tr className="gang-weapon-traits">
                                                        <td></td>
                                                        <td colSpan={5}>
                                                            {
                                                                weaponTraits[
                                                                    weapon
                                                                ]
                                                            }
                                                        </td>
                                                    </tr>
                                                )}
                                            </React.Fragment>
                                        ))}
                                </tbody>
                            </table>
                        </div>
                    </>
                ) : (
                    <div className="gang-card-prose">
                        {tab === 1 ? "Nothing written yet." : "No notes yet."}
                    </div>
                )}
            </div>
        </article>
    );
}
function Panel({ node }) {
    const model = M.models[node.id];
    return (
        <article
            data-flip={`card-${node.id}`}
            className={`${cotton.card} gang-card gang-special gang-${model.icon}`}
        >
            <header className="gang-card-header">
                <div className="gang-panel-title">
                    <span className="gang-panel-icon">
                        <Icon
                            icon={
                                {
                                    campaign: Flag,
                                    actions: ListChecks,
                                    stash: Backpack,
                                }[model.icon]
                            }
                            size={13}
                        />
                    </span>
                    <h2 className="gang-panel-label">
                        {model.icon === "campaign"
                            ? "Campaign"
                            : model.icon === "stash"
                              ? "Stash"
                              : "Available actions"}
                    </h2>
                </div>
                {model.icon === "campaign" ? (
                    <span className="gang-panel-note">
                        Dustfall Dominion <Icon icon={ArrowRight} size={14} />
                    </span>
                ) : (
                    model.icon === "stash" && (
                        <span className="gang-panel-note">120¢ + 55¢</span>
                    )
                )}
            </header>
            <div className="gang-special-body">
                {model.icon === "campaign" ? (
                    <>
                        <dl className="gang-campaign-attributes">
                            {[
                                ["Faction", "Violet"],
                                ["Reputation", "3"],
                                ["Income", "60"],
                                ["Territories", "Settlement · Chem-pit"],
                                ["Battles", "4"],
                            ].map(([name, value]) => (
                                <div key={name}>
                                    <dt>{name}</dt>
                                    <dd>{value}</dd>
                                </div>
                            ))}
                        </dl>
                        <div className="gang-boons">
                            <h3>Boons</h3>
                            <dl>
                                <dt>Settlement</dt>
                                <dd>Income</dd>
                            </dl>
                        </div>
                    </>
                ) : model.icon === "stash" ? (
                    <div className="gang-stash-lines">
                        <dl>
                            <dt>Weapons</dt>
                            <dd>
                                Lasgun <span>1 × 15¢</span>
                            </dd>
                            <dd>
                                Stiletto knife <span>2 × 10¢</span>
                            </dd>
                            <dt>Wargear</dt>
                            <dd>
                                Flak armour <span>1 × 20¢</span>
                            </dd>
                        </dl>
                    </div>
                ) : (
                    <dl className="gang-available-actions">
                        <div>
                            <dt>Hire models</dt>
                            <dd>Available</dd>
                        </div>
                        <div>
                            <dt>Visit the trading post</dt>
                            <dd>Available</dd>
                        </div>
                        <div>
                            <dt>Record a battle</dt>
                            <dd>Available</dd>
                        </div>
                    </dl>
                )}
            </div>
        </article>
    );
}
function GangGrid({ saved, page }) {
    const cards = M.flatten(saved),
        rendered = [];
    for (let i = 0; i < cards.length; i++) {
        const n = cards[i],
            model = M.models[n.id],
            next = cards[i + 1];
        if (
            ["stash", "actions"].includes(n.id) &&
            next &&
            ["stash", "actions"].includes(next.id) &&
            next.id !== n.id
        ) {
            rendered.push(
                <div className="gang-panel-stack" key={`${n.id}-${next.id}`}>
                    <Panel node={n} />
                    <Panel node={next} />
                </div>,
            );
            i++;
        } else if (model.special) rendered.push(<Panel key={n.id} node={n} />);
        else {
            rendered.push(<ModelCard key={n.id} node={n} />);
            (model.pets || []).forEach((pet, index) =>
                rendered.push(
                    <ModelCard
                        key={`${n.id}-pet-${index}`}
                        node={n}
                        pet={pet}
                        owner={model.name}
                        index={index}
                    />,
                ),
            );
        }
    }
    return (
        <div className="gang-grid n26-roster-grid" ref={page}>
            {rendered}
        </div>
    );
}
export function GangSheet({
    saved,
    page,
    trigger,
    onOpen,
    onToggleTheme,
    notice,
    onNotice,
}) {
    const [info, setInfo] = useState(null);
    const members = M.flatten(saved).filter((n) => !M.models[n.id].special);
    const rating = members.reduce((n, m) => n + M.models[m.id].rating, 0);
    const count = members.reduce(
        (n, m) => n + 1 + (M.models[m.id].pets?.length || 0),
        0,
    );
    return (
        <>
            <nav className="gang-nav dark" aria-label="Gyrinx">
                <div className="gang-nav-inner">
                    <a className="gang-brand" href="https://gyrinx.app/n26/">
                        <img
                            src="https://gyrinx.app/static/platform/img/brand/logo-gold-transparent-bg.688efa78e2c1.svg"
                            width="24"
                            height="24"
                            alt=""
                        />
                        Gyrinx
                    </a>
                    <a className="gang-switcher" href="/gang/">
                        The Nightshade Coven
                        <Icon icon={ChevronDown} size={12} />
                    </a>
                    <div className="gang-nav-actions">
                        <a
                            href="https://gyrinx.app/n26/design/"
                            title="N26 design gallery"
                            aria-label="N26 design gallery"
                        >
                            <Icon icon={CircleHelp} size={18} />
                        </a>
                        <span className="gang-editions">
                            <a href="https://gyrinx.app/">N23</a>
                            <span aria-current="true">N26</span>
                        </span>
                        <Button
                            icon={SunMoon}
                            aria-label="Toggle dark mode"
                            title="Toggle dark mode"
                            onClick={onToggleTheme}
                        />
                        <span className="gang-preview-label">
                            Design preview
                        </span>
                        <details className="gang-site-menu">
                            <summary aria-label="Navigation">
                                <Icon icon={Menu} size={20} />
                            </summary>
                            <div>
                                <a href="https://gyrinx.app/n26/gangs/">
                                    Gangs
                                    <Icon icon={Users} size={15} />
                                </a>
                                <a href="https://gyrinx.app/n26/design/">
                                    N26 design gallery
                                    <Icon icon={ExternalLink} size={15} />
                                </a>
                            </div>
                        </details>
                    </div>
                </div>
            </nav>
            <main id="gang-main">
                <div className="gang-breadcrumb">
                    <span>You</span>
                    <span aria-hidden="true">/</span>
                    <span>The Nightshade Coven</span>
                    <Button
                        icon={Share2}
                        onClick={async () => {
                            try {
                                await navigator.clipboard.writeText(
                                    location.href,
                                );
                                onNotice("Preview link copied.");
                            } catch {
                                onNotice(`Preview link: ${location.href}`);
                            }
                        }}
                    >
                        Share
                    </Button>
                </div>
                <div className="gang-heading">
                    <div>
                        <h1>
                            <span className="gang-colour" />
                            The Nightshade Coven
                        </h1>
                        <p>Escher</p>
                    </div>
                    <div className="gang-figures">
                        <Button
                            variant="default"
                            icon={Users}
                            aria-label={`Roster breakdown: ${count} models`}
                            onClick={() => setInfo("Roster breakdown")}
                        >
                            {count}
                            <Icon icon={ChevronDown} size={12} />
                        </Button>
                        <dl>
                            {[
                                ["TP", "Trade Points", "—"],
                                ["R", "Rating", `${rating}¢`],
                                ["Cr", "Credits", "120¢"],
                                ["St", "Stash", "55¢"],
                                ["W", "Wealth", `${rating + 175}¢`],
                            ].map(([short, label, value]) => (
                                <div key={short}>
                                    <dt title={label}>
                                        <span aria-hidden="true">{short}</span>
                                        <span className="cm-sr">{label}</span>
                                    </dt>
                                    <dd>{value}</dd>
                                </div>
                            ))}
                        </dl>
                    </div>
                </div>
                <div className="gang-details-bar">
                    <dl>
                        <div className="gang-traits">
                            <dt>Gang traits</dt>
                            <dd>Law abiding, Chem-alchemy</dd>
                        </div>
                        <div>
                            <dt>Skill Tree 1</dt>
                            <dd>Agility</dd>
                        </div>
                        <div>
                            <dt>Skill Tree 2</dt>
                            <dd>Combat</dd>
                        </div>
                        <div>
                            <dt>Skill Tree 3</dt>
                            <dd>Finesse</dd>
                        </div>
                        <div>
                            <dt>Skill Tree 4</dt>
                            <dd>Shooting</dd>
                        </div>
                    </dl>
                    <div className="gang-page-actions">
                        <Button
                            variant="default"
                            onClick={() => setInfo("Gang notes")}
                        >
                            Notes
                        </Button>
                        <Button
                            variant="default"
                            onClick={() => setInfo("Gang lore")}
                        >
                            Lore
                        </Button>
                        <Button
                            variant="primary"
                            icon={LayoutFreeform}
                            ref={trigger}
                            onClick={onOpen}
                        >
                            Card Manager
                        </Button>
                    </div>
                </div>
                {notice && (
                    <div role="status" className="gang-notice">
                        {notice}
                    </div>
                )}
                <GangGrid saved={saved} page={page} />
                <p className="gang-disclaimer">
                    Sample gang. Layout saves in this browser. Refund, archive
                    and delete are simulated.
                </p>
            </main>
            <footer className="gang-site-footer">
                <span>Gyrinx</span>
                <span>Design preview · N26</span>
                <a href="https://gyrinx.app/n26/design/">
                    Design gallery
                    <Icon icon={ArrowRight} size={14} />
                </a>
            </footer>
            {info && (
                <InfoDialog title={info} onClose={() => setInfo(null)}>
                    {info === "Roster breakdown" ? (
                        <dl className="gang-roster-breakdown">
                            {members.map((n) => (
                                <div key={n.id}>
                                    <dt>{M.models[n.id].name}</dt>
                                    <dd>{M.models[n.id].type}</dd>
                                    <dd>{M.models[n.id].rating}¢</dd>
                                </div>
                            ))}
                        </dl>
                    ) : (
                        <p>
                            {info === "Gang notes"
                                ? "No notes yet."
                                : "Nothing written yet."}
                        </p>
                    )}
                </InfoDialog>
            )}
        </>
    );
}
