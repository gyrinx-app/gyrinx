import React from "react";
import {
    RotateCcwClock,
    Star,
    GitFork,
    RotateCwFadingClock,
    Link2,
    Camera,
    Swords,
    UserRound,
} from "lucide-react";
import { Icon } from "./controls.jsx";
import { UserLink, GangLink, Menu, Dice } from "./history-ui.jsx";
import { base, viewerLink, fullDate, clock } from "./history-format.js";
import * as M from "./history-model.js";
export function Entry({
    entry,
    root,
    viewer,
    permalink,
    snapshotUrl,
    onAction,
    onRestoreTarget,
    targeted,
    lane,
    level = 0,
    latest = false,
    historyIndex,
    floatingMenu = false,
    flat = false,
}) {
    const state = entry.gang ? M.historyFor(root, entry.gang) : null;
    const index = historyIndex || (state ? M.historyIndex(state) : null);
    const domain = index?.versions.has(entry.id),
        inactive = domain && !index.active.has(entry.id),
        change = inactive ? index.changes.get(entry.id) : null;
    const owns = state && M.ownerOf(state) === viewer,
        highlighted = state && M.isHighlighted(state, entry.id, viewer);
    const before =
        entry.before ||
        (domain
            ? entry.parent
                ? M.version(state, entry.parent).snapshot
                : { rating: 0 }
            : null);
    const delta =
        entry.snapshot && before ? entry.snapshot.rating - before.rating : 0;
    return (
        <li
            id={`entry-${entry.id}`}
            data-entry-id={entry.id}
            className={`history-entry ${inactive ? "undone" : ""} ${entry.type === "restore" ? "restoration" : ""} ${highlighted ? "highlighted" : ""} ${targeted ? "entry-targeted" : ""}`}
            style={{ "--lane-level": level }}
            data-level={level}
            data-lane={lane || "canonical"}
            tabIndex={-1}
        >
            {!flat && (
                <TimelineNode
                    latest={latest}
                    restore={entry.type === "restore"}
                    highlighted={highlighted}
                />
            )}
            <div className="entry-record">
                <div className="entry-main">
                    <div className="entry-meta">
                        <UserLink id={entry.actor} />
                        {entry.gang && (
                            <>
                                <span>·</span>
                                <GangLink id={entry.gang} />
                            </>
                        )}
                        {entry.battle && (
                            <a
                                href={viewerLink(
                                    `${base}battles/sump-crossing/`,
                                )}
                            >
                                <Icon icon={Swords} size={12} />
                                {entry.battle}
                            </a>
                        )}
                        {entry.model && (
                            <a
                                href={viewerLink(
                                    `${base}models/${entry.model.toLowerCase().replaceAll(" ", "-")}/`,
                                )}
                            >
                                <Icon icon={UserRound} size={12} />
                                {entry.model}
                            </a>
                        )}
                    </div>
                    <p className="entry-description">
                        {entry.type === "restore" ? (
                            <>
                                Restored their gang to the{" "}
                                <a
                                    href={`#entry-${entry.targetEntryId || entry.restoreTarget || entry.to}`}
                                    onClick={(event) => {
                                        event.preventDefault();
                                        onRestoreTarget(
                                            entry.targetEntryId ||
                                                entry.restoreTarget ||
                                                entry.to,
                                        );
                                    }}
                                >
                                    {fullDate(
                                        entry.sourceWhen ||
                                            M.version(
                                                state,
                                                entry.restoreTarget || entry.to,
                                            ).when,
                                    )}{" "}
                                    version
                                </a>
                                .
                            </>
                        ) : (
                            entry.description
                        )}
                    </p>
                    {(entry.dice || entry.outcome) && (
                        <div className="entry-outcome">
                            {entry.dice && (
                                <Dice
                                    values={entry.dice}
                                    mode={entry.diceMode}
                                    modifier={entry.modifier}
                                />
                            )}
                            <span>{entry.outcome}</span>
                        </div>
                    )}
                </div>
                <div className="entry-figures">
                    <time dateTime={entry.when} title={fullDate(entry.when)}>
                        {clock(entry.when)}
                    </time>
                    {delta !== 0 && (
                        <div className="rating-change">
                            <strong>
                                {entry.snapshot.rating.toLocaleString()}
                            </strong>
                            <span>
                                rating{" "}
                                <small>
                                    {delta > 0 ? "+" : ""}
                                    {delta}
                                </small>
                            </span>
                        </div>
                    )}
                </div>
            </div>
            {(highlighted || inactive || targeted) && (
                <div className="entry-state">
                    {targeted && (
                        <span className="highlight-mark linked-mark">
                            <Icon icon={Link2} size={12} />
                            Linked
                        </span>
                    )}
                    {highlighted && (
                        <span className="highlight-mark">
                            <Icon icon={Star} size={12} />
                            Highlighted
                        </span>
                    )}
                    {inactive && (
                        <span className="undone-note">
                            {change?.type === "restore"
                                ? "Undone by a restore"
                                : "Undone by user"}
                            {change && (
                                <>
                                    {" "}
                                    · <UserLink id={change.actor} /> ·{" "}
                                    <time dateTime={change.when}>
                                        {fullDate(change.when)}
                                    </time>
                                </>
                            )}
                        </span>
                    )}
                </div>
            )}
            {entry.type !== "restore" && (
                <div className="entry-tools">
                    <Menu viewport={floatingMenu}>
                        <a href={permalink(entry)}>
                            <Icon icon={Link2} size={15} />
                            Link to this entry
                        </a>
                        {entry.snapshot && owns && (
                            <button
                                onClick={() => onAction("highlight", entry)}
                            >
                                <Icon icon={Star} size={15} />
                                {highlighted ? "Remove highlight" : "Highlight"}
                            </button>
                        )}
                        {entry.snapshot && state && (
                            <a href={snapshotUrl(entry)}>
                                <Icon icon={Camera} size={15} />
                                View snapshot
                            </a>
                        )}
                        {entry.snapshot && owns && (
                            <>
                                <button
                                    onClick={() => onAction("restore", entry)}
                                >
                                    <Icon
                                        icon={RotateCwFadingClock}
                                        size={15}
                                    />
                                    Restore this version
                                </button>

                                <button
                                    onClick={() => onAction("clone", entry)}
                                >
                                    <Icon icon={GitFork} size={15} />
                                    Clone from version
                                </button>
                            </>
                        )}
                    </Menu>
                </div>
            )}
        </li>
    );
}
export function TimelineNode({
    latest = false,
    restore = false,
    highlighted = false,
}) {
    if (restore)
        return (
            <RotateCcwClock
                size={14}
                strokeWidth={1.7}
                aria-hidden="true"
                className={`timeline-node restoration-node ${highlighted ? "filled" : ""}`}
            />
        );
    return (
        <svg
            className={`timeline-node ${latest ? "latest" : ""} ${highlighted ? "filled" : ""}`}
            width="9"
            height="9"
            viewBox="0 0 10 10"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
        >
            {latest ? (
                <path d="M1 6 L5 2 L9 6 M5 2 V10" />
            ) : (
                <circle
                    cx="5"
                    cy="5"
                    r="4"
                    fill={highlighted ? "var(--color-accent)" : "none"}
                />
            )}
        </svg>
    );
}
