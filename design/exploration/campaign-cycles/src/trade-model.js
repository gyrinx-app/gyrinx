import { territories } from "./campaign-fixtures.js";
export const emptyOffer = () => ({ credits: 0, holdings: [], note: "" });
export function initialiseTrades(s) {
    if (s.tradingEnabled === undefined) s.tradingEnabled = false;
    s.trades ??= [];
    s.tradeNotifications ??= [];
    if (!s.tradeHoldings) {
        s.tradeHoldings = territories
            .filter((t) => t[1])
            .map(([name, owner], i) => ({
                id: `territory-${i}`,
                name,
                owner,
                kind: "Assets / resources",
            }));
        s.gangs.forEach((g) => {
            ["Lasgun", "Mesh armour", "Frag grenades"].forEach((name, i) =>
                s.tradeHoldings.push({
                    id: `${g.id}-gear-${i}`,
                    owner: g.id,
                    name,
                    kind: "Equipment",
                    location: "stash",
                    assignedTo: null,
                }),
            );
            s.tradeHoldings.push({
                id: `${g.id}-resource`,
                owner: g.id,
                name: "Promethium cache",
                kind: "Assets / resources",
            });
        });
    }
    // Earlier demo equipment was created exclusively as unassigned stash holdings.
    if (s.tradeStashVersion !== 1) {
        s.tradeHoldings.forEach((h) => {
            if (
                h.kind === "Equipment" &&
                h.location === undefined &&
                !h.assignedTo
            )
                h.location = "stash";
        });
        s.tradeStashVersion = 1;
    }
    for (const t of s.trades) {
        if (t.campaignUndoRequestsVersion !== 1) {
            t.events.forEach((event, index) => {
                if (
                    event.kind !== "undo-requested" ||
                    s.entries.some(
                        (entry) =>
                            entry.trade === t.id &&
                            entry.tradeEvent === "undo-requested" &&
                            entry.at === event.at &&
                            entry.text === event.text,
                    )
                )
                    return;
                const entry = {
                    id: `trade-undo-request-${t.id}-${index}`,
                    trade: t.id,
                    tradeEvent: "undo-requested",
                    text: event.text,
                    actor: event.actor,
                    at: event.at,
                };
                const position = s.entries.findIndex(
                    (existing) => !existing.at || existing.at <= event.at,
                );
                s.entries.splice(
                    position === -1 ? s.entries.length : position,
                    0,
                    entry,
                );
            });
            t.campaignUndoRequestsVersion = 1;
        }
        t.openedAt ??=
            t.events.find(
                (e) =>
                    e.kind === "opened" || / opened a trade with /.test(e.text),
            )?.at ||
            t.events[0]?.at ||
            null;
        if (t.status !== "open")
            t.closedAt ??=
                t.completedAt ||
                t.events.find(
                    (e) =>
                        ["declined", "completed"].includes(e.kind) ||
                        / declined the trade\.$/.test(e.text),
                )?.at ||
                null;
        if (t.offerNotesVersion === 1) continue;
        for (const id of [t.from, t.to]) {
            t.offers[id].note ??= "";
            const earlier = (t.notes || []).filter(
                (n) => gang(s, id)?.owner === n.actor,
            );
            if (t.status === "open" && earlier.length) {
                t.offers[id].note = [
                    t.offers[id].note,
                    ...earlier.map((n) => n.text),
                ]
                    .filter(Boolean)
                    .join("\n\n");
            }
        }
        if (t.status === "open" && t.notes?.length) {
            if (t.accepted.length) {
                t.accepted = [];
                t.events.push({
                    text: "Earlier notes were included in the offers. Both gangs must review and accept again.",
                    actor: "Campaign",
                    at: new Date().toISOString(),
                    kind: "migration",
                });
            }
            t.notes = [];
        }
        t.offerNotesVersion = 1;
    }
    return s;
}
const gang = (s, id) => s.gangs.find((g) => g.id === id);
export function availableCredits(s, id, except) {
    return (
        gang(s, id).credits -
        s.trades
            .filter(
                (t) =>
                    t.id !== except && t.status === "open" && t.accepted.length,
            )
            .reduce((n, t) => n + (t.offers[id]?.credits || 0), 0)
    );
}
export function availableHoldings(s, id, except) {
    const reserved = new Set(
        s.trades
            .filter(
                (t) =>
                    t.id !== except && t.status === "open" && t.accepted.length,
            )
            .flatMap((t) => Object.values(t.offers).flatMap((o) => o.holdings)),
    );
    return s.tradeHoldings.filter(
        (h) =>
            h.owner === id &&
            !reserved.has(h.id) &&
            (h.kind !== "Equipment" ||
                (h.location === "stash" && !h.assignedTo)),
    );
}
function validateOffer(s, id, offer, except) {
    if (
        !offer ||
        !Number.isSafeInteger(offer.credits) ||
        offer.credits < 0 ||
        offer.credits > availableCredits(s, id, except)
    )
        throw new Error("The offered credits exceed the available balance.");
    if (
        typeof (offer.note ?? "") !== "string" ||
        (offer.note || "").length > 4000
    )
        throw new Error("Offer notes must be at most 4,000 characters.");
    const available = new Set(
        availableHoldings(s, id, except).map((h) => h.id),
    );
    if (
        new Set(offer.holdings).size !== offer.holdings.length ||
        offer.holdings.some((h) => !available.has(h))
    )
        throw new Error(
            "Some offered holdings are no longer available. Review the offer.",
        );
}
export function isCampaignEntry(entry) {
    if (!entry.trade) return true;
    return (
        [
            "opened",
            "completed",
            "declined",
            "undone",
            "undo-requested",
        ].includes(entry.tradeEvent) ||
        (!entry.tradeEvent &&
            (/ opened a trade with /.test(entry.text) ||
                /^Trade completed\./.test(entry.text) ||
                / declined the trade\.$/.test(entry.text)))
    );
}
function log(s, t, text, actor, kind = "updated", details = null) {
    const at = new Date().toISOString();
    t.events.push({
        text,
        actor,
        at,
        kind,
        ...(details ? { details: structuredClone(details) } : {}),
    });
    if (
        ![
            "opened",
            "completed",
            "declined",
            "undone",
            "undo-requested",
        ].includes(kind)
    )
        return;
    s.entries.unshift({
        id: crypto.randomUUID(),
        text,
        actor,
        at,
        trade: t.id,
        tradeEvent: kind,
        cycle: s.currentCycle,
    });
}
export function openTrade(s, actor, from, to, offer, note = offer.note || "") {
    initialiseTrades(s);
    if (!s.tradingEnabled)
        throw new Error("Trading is disabled for this campaign.");
    if (
        !gang(s, from) ||
        !gang(s, to) ||
        from === to ||
        gang(s, from).owner !== actor ||
        gang(s, to).owner === actor
    )
        throw new Error("Select your gang and a gang owned by another player.");
    offer = { ...offer, note };
    validateOffer(s, from, offer);
    const t = {
        id: crypto.randomUUID(),
        from,
        to,
        status: "open",
        openedAt: new Date().toISOString(),
        accepted: [],
        offers: { [from]: structuredClone(offer), [to]: emptyOffer() },
        notes: [],
        offerNotesVersion: 1,
        events: [],
    };
    s.trades.unshift(t);
    log(
        s,
        t,
        `${gang(s, from).name} opened a trade with ${gang(s, to).name}.`,
        actor,
        "opened",
        offerSnapshot(s, from, offer),
    );
    s.tradeNotifications.unshift({
        id: crypto.randomUUID(),
        trade: t.id,
        owner: gang(s, to).owner,
        text: `${gang(s, from).name} has begun a trade with ${gang(s, to).name}.`,
        read: false,
    });
    return t.id;
}
export function actOnTrade(s, id, actor, action, data) {
    initialiseTrades(s);
    const t = s.trades.find((t) => t.id === id);
    if (!t) throw new Error("This trade could not be found.");
    const own = [t.from, t.to].find((id) => gang(s, id).owner === actor);
    if (!own)
        throw new Error(
            "Only the owners of the participating gangs can change this trade.",
        );
    if (action.startsWith("undo-"))
        return undoTrade(s, t, own, actor, action, data);
    if (t.status !== "open") throw new Error("This trade has ended.");
    if (action === "decline") {
        t.status = "declined";
        t.closedAt = new Date().toISOString();
        t.accepted = [];
        log(
            s,
            t,
            `${gang(s, own).name} declined the trade.`,
            actor,
            "declined",
        );
        return;
    }
    if (action === "withdraw") {
        if (!t.accepted.includes(own) || t.accepted.length !== 1)
            throw new Error("Only your pending acceptance can be cancelled.");
        t.accepted = [];
        log(
            s,
            t,
            `${gang(s, own).name} cancelled their acceptance. Both offers are editable.`,
            actor,
            "withdrawn",
        );
        return;
    }
    if (!s.tradingEnabled)
        throw new Error(
            "Trading is disabled. You can still decline or cancel your acceptance.",
        );
    if (action === "offer") {
        if (t.accepted.length)
            throw new Error(
                "Both offers are locked. Select Counter-offer to revise your offer.",
            );
        validateOffer(s, own, data, id);
        t.offers[own] = { ...structuredClone(data), note: data.note || "" };
        log(
            s,
            t,
            `${gang(s, own).name} updated their offer.`,
            actor,
            "offered",
            offerSnapshot(s, own, t.offers[own]),
        );
    } else if (action === "counter") {
        if (!t.accepted.length || t.accepted.includes(own))
            throw new Error("Wait for the other gang to respond.");
        t.accepted = [];
        log(
            s,
            t,
            `${gang(s, own).name} made a counter-offer. Both gangs must accept again.`,
            actor,
        );
    } else if (action === "accept") {
        if (t.accepted.includes(own))
            throw new Error("Your gang has already accepted.");
        [t.from, t.to].forEach((id) =>
            validateOffer(s, id, t.offers[id], t.id),
        );
        t.accepted.push(own);
        log(s, t, `${gang(s, own).name} accepted the trade.`, actor);
        if (t.accepted.length === 2) {
            t.transfers = transferSummary(s, t);
            // Both sides have been validated before applying either transfer.
            for (const transfer of t.transfers) {
                gang(s, transfer.from).credits -= transfer.credits;
                gang(s, transfer.to).credits += transfer.credits;
                transfer.holdings.forEach((h) => {
                    s.tradeHoldings.find((v) => v.id === h.id).owner =
                        transfer.to;
                });
            }
            t.status = "completed";
            t.completedAt = new Date().toISOString();
            t.closedAt = t.completedAt;
            s.gangs.forEach((g) => {
                g.territories = s.tradeHoldings.filter(
                    (h) => h.owner === g.id && h.id.startsWith("territory-"),
                ).length;
            });
            log(
                s,
                t,
                `${gang(s, t.from).name} and ${gang(s, t.to).name} completed their trade.`,
                actor,
                "completed",
            );
        }
    } else throw new Error("Unknown trade action.");
}

export function transferSummary(s, t) {
    return (
        t.transfers ||
        [t.from, t.to].map((id) => ({
            from: id,
            to: id === t.from ? t.to : t.from,
            fromName: gang(s, id).name,
            toName: gang(s, id === t.from ? t.to : t.from).name,
            credits: t.offers[id].credits,
            holdings: t.offers[id].holdings.map((h) => {
                const holding = s.tradeHoldings.find((v) => v.id === h);
                return {
                    id: h,
                    name: holding?.name || "Earlier holding",
                    kind: holding?.kind || "Equipment",
                };
            }),
            note: t.offers[id].note || "",
        }))
    );
}

export const statusLabel = (status) =>
    ({
        open: "Open",
        completed: "Completed",
        declined: "Declined",
        undone: "Undone",
    })[status] || status;
export function offerSnapshot(s, id, offer) {
    return {
        gang: id,
        gangName: gang(s, id).name,
        credits: offer.credits,
        note: offer.note || "",
        holdings: offer.holdings.map((id) => {
            const h = s.tradeHoldings.find((h) => h.id === id);
            return {
                id,
                name: h?.name || "Earlier holding",
                kind: h?.kind || "Equipment",
            };
        }),
    };
}
function undoTrade(s, t, own, actor, action, requestId) {
    if (t.status !== "completed")
        throw new Error("Only a completed trade can be undone.");
    if (action === "undo-request") {
        if (t.undo?.status === "pending")
            throw new Error("An undo request is already pending.");
        t.undo = {
            id: crypto.randomUUID(),
            status: "pending",
            requestedBy: own,
            requestedAt: new Date().toISOString(),
        };
        log(
            s,
            t,
            `${gang(s, own).name} requested an undo. The other gang must accept before anything is returned.`,
            actor,
            "undo-requested",
        );
        const other = own === t.from ? t.to : t.from;
        s.tradeNotifications.unshift({
            id: crypto.randomUUID(),
            trade: t.id,
            owner: gang(s, other).owner,
            text: `${gang(s, own).name} requested an undo of their trade with ${gang(s, other).name}.`,
            read: false,
        });
        return;
    }
    if (t.undo?.status !== "pending" || t.undo.id !== requestId)
        throw new Error(
            "This undo request has changed. Review the trade again.",
        );
    const requester = t.undo.requestedBy === own;
    if (action === "undo-cancel") {
        if (!requester)
            throw new Error(
                "Only the requesting gang can cancel this request.",
            );
        t.undo.status = "cancelled";
        log(
            s,
            t,
            `${gang(s, own).name} cancelled the undo request.`,
            actor,
            "undo-cancelled",
        );
        return;
    }
    if (requester)
        throw new Error("The other gang must respond to your undo request.");
    if (action === "undo-decline") {
        t.undo.status = "declined";
        log(
            s,
            t,
            `${gang(s, own).name} declined the undo request. The completed trade is unchanged.`,
            actor,
            "undo-declined",
        );
        return;
    }
    if (action !== "undo-accept") throw new Error("Unknown undo action.");
    const transfers = transferSummary(s, t);
    // Validate the whole return before changing either gang; credits settle net.
    for (const id of [t.from, t.to]) {
        const paying = transfers
            .filter((v) => v.to === id)
            .reduce((n, v) => n + v.credits, 0);
        const receiving = transfers
            .filter((v) => v.from === id)
            .reduce((n, v) => n + v.credits, 0);
        if (availableCredits(s, id) < Math.max(0, paying - receiving))
            throw new Error(
                `${gang(s, id).name} does not have enough unreserved credits to undo this trade.`,
            );
    }
    for (const transfer of transfers) {
        const available = new Set(
            availableHoldings(s, transfer.to).map((h) => h.id),
        );
        if (transfer.holdings.some((h) => !available.has(h.id)))
            throw new Error(
                "A traded holding has moved, is assigned to a model or is reserved in another trade. Return it to the receiving gang’s stash and release any reservation before undoing.",
            );
    }
    t.transfers ??= structuredClone(transfers);
    for (const transfer of transfers) {
        gang(s, transfer.to).credits -= transfer.credits;
        gang(s, transfer.from).credits += transfer.credits;
        transfer.holdings.forEach((h) => {
            s.tradeHoldings.find((v) => v.id === h.id).owner = transfer.from;
        });
    }
    s.gangs.forEach((g) => {
        g.territories = s.tradeHoldings.filter(
            (h) => h.owner === g.id && h.id.startsWith("territory-"),
        ).length;
    });
    t.undo.status = "accepted";
    t.undoneAt = new Date().toISOString();
    t.undo.respondedAt = t.undoneAt;
    t.status = "undone";
    log(
        s,
        t,
        `${gang(s, own).name} accepted the undo. The trade was undone and all transferred credits and holdings were returned.`,
        actor,
        "undone",
    );
}
