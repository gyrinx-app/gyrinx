import cotton from "./cotton.json";
import { gangIcons } from "./campaign-fixtures.js";
import React, { useState } from "react";
import {
    Handshake,
    LockKeyhole,
    Check,
    Package,
    Coins,
    Landmark,
    ArrowRightLeft,
    Plus,
    Undo2,
} from "lucide-react";
import { Button, Icon } from "./controls.jsx";
import { Select, Input } from "./surface-controls.jsx";
import { TextArea, Tag, CheckField } from "./campaign-ui.jsx";
import { CampaignCard as Card } from "./campaign-view.jsx";
import * as T from "./trade-model.js";
export function GangIdentity({ gang, offer = false, compact = false }) {
    return (
        <div
            className="tr-gang"
            style={{ "--tr-colour": `var(--color-${gang.colour}-500)` }}
        >
            <span className="tr-gang-icon">
                <img
                    src={
                        gang.iconUrl ||
                        `/static/history/${gangIcons[gang.id] || "custom-gang"}.svg`
                    }
                    alt=""
                />
            </span>
            <div>
                {compact ? (
                    <strong className="tr-identity-name">{gang.name}</strong>
                ) : (
                    <h2>
                        {gang.name}
                        {offer ? "’s offer" : ""}
                    </h2>
                )}
                <p>{gang.owner}</p>
            </div>
        </div>
    );
}
function OfferEditor({ state, gang, offer, setOffer, trade }) {
    const holdings = T.availableHoldings(state, gang.id, trade);
    return (
        <div className="tr-editor">
            <Input
                label="Credits"
                type="number"
                min="0"
                max={T.availableCredits(state, gang.id, trade)}
                required
                value={offer.credits}
                onChange={(v) =>
                    setOffer({ ...offer, credits: v === "" ? "" : Number(v) })
                }
            />
            <p className="cp-help">
                {T.availableCredits(state, gang.id, trade)}¢ available
            </p>
            <p className="cp-help">
                Only equipment in the gang’s stash can be offered.
            </p>
            {["Equipment", "Assets / resources"].map((kind) => (
                <fieldset key={kind}>
                    <legend>
                        <Icon
                            icon={kind === "Equipment" ? Package : Landmark}
                            size={16}
                        />
                        {kind}
                    </legend>
                    {holdings
                        .filter((h) => h.kind === kind)
                        .map((h) => (
                            <CheckField
                                key={h.id}
                                label={h.name}
                                checked={offer.holdings.includes(h.id)}
                                onChange={(checked) =>
                                    setOffer({
                                        ...offer,
                                        holdings: checked
                                            ? [...offer.holdings, h.id]
                                            : offer.holdings.filter(
                                                  (id) => id !== h.id,
                                              ),
                                    })
                                }
                            />
                        ))}
                    {!holdings.some((h) => h.kind === kind) && (
                        <p className="cp-help">No available holdings.</p>
                    )}
                </fieldset>
            ))}
            <TextArea
                label="Offer note (optional)"
                value={offer.note || ""}
                onChange={(note) => setOffer({ ...offer, note })}
                maxLength={4000}
                help="Part of this offer. Both gangs accept these terms, including any IOU or other agreement."
            />
        </div>
    );
}
function OfferSummary({ state, offer }) {
    return (
        <div className="tr-summary">
            <div className="tr-holding">
                <Icon icon={Coins} />
                <span>Credits</span>
                <strong>{offer.credits}¢</strong>
            </div>
            {["Equipment", "Assets / resources"].map((kind) => (
                <section key={kind}>
                    <h3>
                        <Icon
                            icon={kind === "Equipment" ? Package : Landmark}
                            size={16}
                        />
                        {kind}
                    </h3>
                    {offer.holdings
                        .map((id) =>
                            state.tradeHoldings.find((h) => h.id === id),
                        )
                        .filter((h) => h?.kind === kind)
                        .map((h) => (
                            <div className="tr-holding" key={h.id}>
                                <span>{h.name}</span>
                                <span>× 1</span>
                            </div>
                        ))}
                    {!offer.holdings.some(
                        (id) =>
                            state.tradeHoldings.find((h) => h.id === id)
                                ?.kind === kind,
                    ) && <p className="cp-help">None offered</p>}
                </section>
            ))}
            <section>
                <h3>Offer note</h3>
                <p className="tr-note-text">
                    {offer.note || "No additional terms."}
                </p>
            </section>
        </div>
    );
}
export function TradeSettings({ state, arbitrator, commit }) {
    const [enabled, setEnabled] = useState(!!state.tradingEnabled);
    if (!arbitrator)
        return <p>Only the campaign arbitrator can edit these settings.</p>;
    return (
        <Card title="Campaign trading">
            <form
                className="tr-settings"
                onSubmit={(e) => {
                    e.preventDefault();
                    commit((s) => {
                        s.tradingEnabled = enabled;
                    }, "Campaign trading settings saved.");
                }}
            >
                <CheckField
                    label="Allow trades between campaign gangs"
                    checked={enabled}
                    onChange={setEnabled}
                />
                <p className="cp-help">
                    Disabled by default. When disabled, existing trades remain
                    available as records. Participants can decline open trades.
                </p>
                <Button variant="success" type="submit">
                    Save
                </Button>
            </form>
        </Card>
    );
}
export function TradeList({ state, actor, open, create }) {
    const trades = (state.trades || []).filter((t) =>
        [t.from, t.to].some(
            (id) => state.gangs.find((g) => g.id === id)?.owner === actor,
        ),
    );
    return (
        <Card
            title="Trades"
            action={
                <Button
                    icon={Plus}
                    variant="primary"
                    disabled={
                        !state.tradingEnabled ||
                        !state.gangs.some((g) => g.owner === actor)
                    }
                    onClick={create}
                >
                    Start a trade
                </Button>
            }
        >
            <div className="tr-list">
                {!trades.length && (
                    <p className="cp-help">
                        No trades yet. Start a trade with another gang in this
                        campaign.
                    </p>
                )}
                {trades.map((t) => (
                    <button key={t.id} onClick={() => open(t.id)}>
                        <Icon icon={Handshake} />
                        <span>
                            {state.gangs.find((g) => g.id === t.from)?.name}{" "}
                            <span className="text-muted">with</span>{" "}
                            {state.gangs.find((g) => g.id === t.to)?.name}
                        </span>
                        <Tag>{T.statusLabel(t.status)}</Tag>
                    </button>
                ))}
            </div>
        </Card>
    );
}
export function TradeScreen({ state, actor, tradeId, commit, open }) {
    const trade = state.trades?.find((t) => t.id === tradeId);
    const [from, setFrom] = useState(
        state.gangs.find((g) => g.owner === actor)?.id || "",
    );
    const [to, setTo] = useState(
        state.gangs.find((g) => g.owner !== actor)?.id || "",
    );
    const [offer, setOffer] = useState(T.emptyOffer),
        [editing, setEditing] = useState(false);
    const own =
        trade &&
        [trade.from, trade.to].find(
            (id) => state.gangs.find((g) => g.id === id)?.owner === actor,
        );
    const ended = trade && trade.status !== "open",
        locked = !!trade?.accepted.length;
    const gang = (id) => state.gangs.find((g) => g.id === id);
    const act = (action, data, message) =>
        commit((s) => T.actOnTrade(s, trade.id, actor, action, data), message);
    if (tradeId && !trade)
        return (
            <p role="alert">
                This trade could not be found. Open a trade from the campaign
                log.
            </p>
        );
    return (
        <div className="tr-workspace">
            <div className="tr-heading">
                <div className="cp-inline">
                    <Icon icon={Handshake} size={24} />
                    <h1>{trade ? "Gang trade" : "New trade"}</h1>
                    <Tag>{trade ? T.statusLabel(trade.status) : "Draft"}</Tag>
                </div>
                {trade ? (
                    <p className="tr-dates">
                        Opened <TradeTime at={trade.openedAt} />
                        {trade.closedAt ? (
                            <>
                                {" "}
                                · Closed <TradeTime at={trade.closedAt} />
                            </>
                        ) : (
                            " · Still open"
                        )}
                        {trade.undoneAt && (
                            <>
                                {" "}
                                · Undone <TradeTime at={trade.undoneAt} />
                            </>
                        )}
                    </p>
                ) : (
                    <p>Agree an exchange with another gang in this campaign.</p>
                )}
            </div>
            {!trade && (
                <Card title="Participants">
                    <div className="tr-participants">
                        <Select
                            label="Your gang"
                            value={from}
                            onChange={(id) => {
                                setFrom(id);
                                setOffer(T.emptyOffer());
                            }}
                            options={state.gangs
                                .filter((g) => g.owner === actor)
                                .map((g) => [g.id, g.name])}
                        />
                        <Icon icon={ArrowRightLeft} />
                        <Select
                            label="Trade with"
                            value={to}
                            onChange={setTo}
                            options={state.gangs
                                .filter((g) => g.owner !== actor)
                                .map((g) => [g.id, g.name])}
                        />
                    </div>
                </Card>
            )}
            {trade && (
                <div
                    className={`tr-banner ${trade.status === "completed" ? "tr-completed" : ""}`}
                    role="status"
                >
                    <Icon
                        icon={
                            trade.status === "undone"
                                ? Undo2
                                : ended && trade.status === "completed"
                                  ? Check
                                  : locked
                                    ? LockKeyhole
                                    : Handshake
                        }
                    />
                    <div>
                        <strong>
                            {ended
                                ? trade.status === "completed"
                                    ? "Trade completed"
                                    : trade.status === "undone"
                                      ? "Trade undone"
                                      : "Trade declined"
                                : locked
                                  ? "Both offers are locked"
                                  : "Waiting for agreement"}
                        </strong>
                        <p>
                            {ended
                                ? trade.status === "completed"
                                    ? "All offered credits and holdings have changed owner."
                                    : trade.status === "undone"
                                      ? "All transferred credits and holdings were returned. The original agreement has been undone."
                                      : "No credits or holdings were transferred."
                                : locked
                                  ? trade.accepted.includes(own)
                                      ? "You can cancel your acceptance to edit your offer while the trade remains open."
                                      : "Accept the exchange, decline it, or make a counter-offer. A counter-offer clears the acceptance."
                                  : "Each player can change their own offer. Both players must accept the same exchange."}
                        </p>
                    </div>
                </div>
            )}
            <div className="tr-offers">
                {[trade?.from || from, trade?.to || to].map(
                    (id, index) =>
                        gang(id) && (
                            <section
                                key={id}
                                className={`tr-offer ${trade?.accepted.includes(id) ? "tr-offer-accepted" : ""}`}
                                style={{
                                    "--tr-colour": `var(--color-${gang(id).colour}-500)`,
                                }}
                            >
                                <header>
                                    <GangIdentity gang={gang(id)} offer />
                                    <div className="cp-inline">
                                        {trade?.accepted.includes(id) ? (
                                            <span
                                                className={`${cotton.tradeAcceptedBadge} tr-accepted-label`}
                                            >
                                                <Icon icon={Check} size={14} />
                                                Accepted
                                            </span>
                                        ) : (
                                            <Tag>
                                                {ended
                                                    ? T.statusLabel(
                                                          trade.status,
                                                      )
                                                    : id === own ||
                                                        (!trade && index === 0)
                                                      ? "Your offer"
                                                      : "Awaiting acceptance"}
                                            </Tag>
                                        )}
                                        {locked && !ended && (
                                            <Icon
                                                icon={LockKeyhole}
                                                size={14}
                                            />
                                        )}
                                    </div>
                                </header>
                                {(!trade && index === 0) ||
                                (trade &&
                                    editing &&
                                    own === id &&
                                    !locked &&
                                    !ended) ? (
                                    <OfferEditor
                                        state={state}
                                        gang={gang(id)}
                                        offer={offer}
                                        setOffer={setOffer}
                                        trade={trade?.id}
                                    />
                                ) : (
                                    <OfferSummary
                                        state={state}
                                        offer={
                                            trade?.offers[id] || T.emptyOffer()
                                        }
                                    />
                                )}{" "}
                                {trade?.status !== "open" &&
                                    trade?.notes?.some(
                                        (n) => n.actor === gang(id).owner,
                                    ) && (
                                        <section className="tr-legacy-notes">
                                            <h3>
                                                Earlier notes (outside the
                                                accepted offer)
                                            </h3>
                                            {trade.notes
                                                .filter(
                                                    (n) =>
                                                        n.actor ===
                                                        gang(id).owner,
                                                )
                                                .map((n, i) => (
                                                    <p
                                                        key={i}
                                                        className="tr-note-text"
                                                    >
                                                        {n.text}
                                                    </p>
                                                ))}
                                        </section>
                                    )}
                                {!trade && index === 1 && (
                                    <p className="tr-card-foot cp-help">
                                        {gang(id).owner} adds their offer after
                                        you open the trade.
                                    </p>
                                )}
                                {trade &&
                                    own === id &&
                                    !ended &&
                                    !locked &&
                                    state.tradingEnabled && (
                                        <div className="tr-card-foot">
                                            {editing ? (
                                                <>
                                                    <Button
                                                        variant="default"
                                                        onClick={() =>
                                                            setEditing(false)
                                                        }
                                                    >
                                                        Cancel
                                                    </Button>
                                                    <Button
                                                        variant="success"
                                                        onClick={async () => {
                                                            if (
                                                                await act(
                                                                    "offer",
                                                                    offer,
                                                                    "Offer saved.",
                                                                )
                                                            )
                                                                setEditing(
                                                                    false,
                                                                );
                                                        }}
                                                    >
                                                        Save offer
                                                    </Button>
                                                </>
                                            ) : (
                                                <Button
                                                    variant="primary"
                                                    onClick={() => {
                                                        setOffer(
                                                            structuredClone(
                                                                trade.offers[
                                                                    id
                                                                ],
                                                            ),
                                                        );
                                                        setEditing(true);
                                                    }}
                                                >
                                                    Edit offer
                                                </Button>
                                            )}
                                        </div>
                                    )}
                            </section>
                        ),
                )}
            </div>
            {trade && own && !ended && (
                <div className="tr-actions">
                    <p className="cp-help">
                        {trade.accepted.includes(own)
                            ? "You accepted. Waiting for the other gang."
                            : "Review both offers before accepting."}
                    </p>
                    <div>
                        <Button
                            variant="default"
                            onClick={() =>
                                act("decline", null, "Trade declined.")
                            }
                        >
                            Decline
                        </Button>
                        {locked && !trade.accepted.includes(own) && (
                            <Button
                                variant="primary"
                                disabled={!state.tradingEnabled}
                                onClick={async () => {
                                    if (
                                        await act(
                                            "counter",
                                            null,
                                            "Acceptance cleared. Revise your offer.",
                                        )
                                    ) {
                                        setOffer(
                                            structuredClone(trade.offers[own]),
                                        );
                                        setEditing(true);
                                    }
                                }}
                            >
                                Counter-offer
                            </Button>
                        )}
                        {trade.accepted.includes(own) ? (
                            <Button
                                variant="default"
                                onClick={async () => {
                                    if (
                                        await act(
                                            "withdraw",
                                            null,
                                            "Acceptance cancelled. Revise your offer.",
                                        )
                                    ) {
                                        setOffer(
                                            structuredClone(trade.offers[own]),
                                        );
                                        setEditing(true);
                                    }
                                }}
                            >
                                Cancel acceptance
                            </Button>
                        ) : (
                            <Button
                                variant="success"
                                icon={Check}
                                disabled={editing || !state.tradingEnabled}
                                onClick={() =>
                                    act("accept", null, "Acceptance recorded.")
                                }
                            >
                                Accept
                            </Button>
                        )}
                    </div>
                </div>
            )}
            {trade && !own && (
                <p className="cp-help">
                    Only the owners of these two gangs can interact with the
                    trade.
                </p>
            )}
            {["completed", "undone"].includes(trade?.status) && (
                <Card
                    title={
                        trade.status === "undone"
                            ? "Original exchange (undone)"
                            : "What changed hands"
                    }
                >
                    <div className="tr-transfer-summary">
                        {T.transferSummary(state, trade).map((transfer) => (
                            <section key={transfer.from}>
                                <div className="tr-transfer-route">
                                    <GangIdentity
                                        gang={{
                                            ...gang(transfer.from),
                                            name: transfer.fromName,
                                        }}
                                        compact
                                    />
                                    <span className="cp-help tr-transfer-to">
                                        to
                                    </span>
                                    <GangIdentity
                                        gang={{
                                            ...gang(transfer.to),
                                            name: transfer.toName,
                                        }}
                                        compact
                                    />
                                </div>
                                <ul>
                                    {transfer.credits > 0 && (
                                        <li>{transfer.credits}¢</li>
                                    )}
                                    {transfer.holdings.map((h) => (
                                        <li key={h.id}>{h.name} × 1</li>
                                    ))}
                                </ul>
                                {!transfer.credits &&
                                    !transfer.holdings.length && (
                                        <p className="cp-help">
                                            No credits or holdings transferred.
                                        </p>
                                    )}
                                {transfer.note && (
                                    <div>
                                        <h4>
                                            Agreed note from {transfer.fromName}
                                        </h4>
                                        <p className="tr-note-text">
                                            {transfer.note}
                                        </p>
                                    </div>
                                )}
                            </section>
                        ))}
                    </div>
                </Card>
            )}
            {trade?.status === "completed" && own && (
                <Card title="Undo trade">
                    <div className="tr-undo">
                        {trade.undo?.status === "pending" ? (
                            <>
                                <p role="status">
                                    {gang(trade.undo.requestedBy).name}{" "}
                                    requested an undo. Both gangs must agree
                                    before credits and holdings are returned.
                                </p>
                                <div className="cp-inline">
                                    {trade.undo.requestedBy === own ? (
                                        <Button
                                            variant="default"
                                            onClick={() =>
                                                act(
                                                    "undo-cancel",
                                                    trade.undo.id,
                                                    "Undo request cancelled.",
                                                )
                                            }
                                        >
                                            Cancel undo request
                                        </Button>
                                    ) : (
                                        <>
                                            <Button
                                                variant="default"
                                                onClick={() =>
                                                    act(
                                                        "undo-decline",
                                                        trade.undo.id,
                                                        "Undo request declined.",
                                                    )
                                                }
                                            >
                                                Decline undo
                                            </Button>
                                            <Button
                                                variant="success"
                                                icon={Undo2}
                                                onClick={() =>
                                                    act(
                                                        "undo-accept",
                                                        trade.undo.id,
                                                        "Trade undone. Credits and holdings returned.",
                                                    )
                                                }
                                            >
                                                Accept undo
                                            </Button>
                                        </>
                                    )}
                                </div>
                            </>
                        ) : (
                            <>
                                <p>
                                    Request the other player’s agreement to
                                    return all transferred credits and holdings
                                    and undo the original agreement.
                                </p>
                                <p className="cp-help">
                                    Holdings must still belong to the receiving
                                    gang and be available. Equipment must be in
                                    the stash. Credits reserved in other trades
                                    cannot be returned.
                                </p>
                                <Button
                                    variant="primary"
                                    icon={Undo2}
                                    onClick={() =>
                                        act(
                                            "undo-request",
                                            null,
                                            "Undo requested. The other player has been notified.",
                                        )
                                    }
                                >
                                    Request undo
                                </Button>
                            </>
                        )}
                    </div>
                </Card>
            )}
            {!trade && (
                <div className="tr-actions">
                    <p className="cp-help">
                        Opening a trade logs it and notifies the other gang’s
                        owner.
                    </p>
                    <Button
                        variant="success"
                        icon={Handshake}
                        disabled={!from || !to || !state.tradingEnabled}
                        onClick={async () => {
                            let id;
                            if (
                                await commit((s) => {
                                    id = T.openTrade(s, actor, from, to, offer);
                                }, "Trade opened. The other player has been notified.")
                            )
                                open(id);
                        }}
                    >
                        Open trade
                    </Button>
                </div>
            )}
            {trade && (
                <Card title="Trade history">
                    <ol className="tr-events">
                        {[...trade.events].reverse().map((e, i) => (
                            <li key={i}>
                                <span className="cp-help">
                                    {e.actor} ·{" "}
                                    {new Date(e.at).toLocaleString("en-GB")}
                                </span>
                                <p>{e.text}</p>
                                {e.details && (
                                    <div className="tr-event-offer">
                                        <strong>
                                            {e.details.gangName} offered
                                        </strong>
                                        <ul>
                                            <li>{e.details.credits}¢</li>
                                            {e.details.holdings.map((h) => (
                                                <li key={h.id}>{h.name} × 1</li>
                                            ))}
                                        </ul>
                                        {e.details.note && (
                                            <p className="tr-note-text">
                                                Offer note: {e.details.note}
                                            </p>
                                        )}
                                    </div>
                                )}
                            </li>
                        ))}
                    </ol>
                </Card>
            )}
        </div>
    );
}

function TradeTime({ at }) {
    if (!at) return <span>time unavailable</span>;
    return (
        <time dateTime={at}>
            {new Date(at).toLocaleString("en-GB", {
                dateStyle: "medium",
                timeStyle: "short",
            })}
        </time>
    );
}
