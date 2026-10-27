export const storageKey = "gyrinx-campaign-periods-v1";
export const campaignDescription = [
    "The Ash Road winds between abandoned manufactoria, dust-choked settlements and the last working water pumps on the edge of the hive. Caravans still brave the route, carrying promethium, ammunition and food to anyone who can pay. Three rival gangs have arrived to collect the tolls, claim the best trading posts and decide whose colours fly above the road.",
    "During Occupation, gangs push into unclaimed ground: a collapsed dome, an old pumping station and the rusting gantries above Toll Crossing. Every victory offers a foothold, but holding territory means protecting the workers and traders who keep it productive. Challenges should be agreed with the arbitrator so every gang has a chance to shape the campaign.",
    "Downtime offers a brief opportunity to recover, recruit and re-equip. When Takeover begins, the fragile borders disappear. Rivals can challenge for each other’s holdings, alliances become bargains and a quiet stretch of road can turn into an ambush. Record your battles against their campaign cycle so the story of the Ash Road grows alongside the gangs.",
];

export function addPastExamples(state) {
    if (state.sampleHistoryVersion === 1) return state;
    const past = state.cycles.filter((c) => state.closedCycles.includes(c.id));
    const names = [
        "Raid on the rust yards",
        "The caravan ambush",
        "Skirmish at Sump Gate",
        "Fight for the water tower",
    ];
    past.forEach((cycle, index) => {
        if (!cycle.endedAt)
            cycle.endedAt = new Date(
                Date.now() - (past.length - index) * 7 * 86400000,
            ).toISOString();
        if (
            state.battles.some((b) => b.cycle === cycle.id) ||
            state.gangs.length < 2
        )
            return;
        const phase = state.phases.find((p) => p.id === cycle.phase);
        // Downtime and other recovery phases receive dates without invented battles.
        if (
            phase.grant > 0 &&
            Object.values(phase.rewards).every(
                (r) => String(r.credits) === "0" && Number(r.reputation) === 0,
            )
        )
            return;
        state.battles.push({
            id: `sample-battle-${cycle.id}`,
            name: `${names[index % names.length]}${index >= names.length ? ` · ${cycle.name}` : ""}`,
            cycle: cycle.id,
            cycleName: cycle.name,
            phase: phase.id,
            phaseName: phase.name,
            participants: state.gangs.slice(0, 2).map((g) => g.id),
            winner: "draw",
            sideJobs: [],
            rules: null,
            payouts: state.gangs.slice(0, 2).map((g) => ({
                gang: g.id,
                credits: 0,
                reputation: 0,
                rolls: "Sample battle",
            })),
        });
    });
    state.sampleHistoryVersion = 1;
    return state;
}
export const outcomeLabels = {
    win: "Win",
    loss: "Loss",
    draw: "Draw",
    sideJob: "Side job",
    territoryLoss: "Territory lost",
};
export function defaults() {
    return addPastExamples({
        version: 1,
        name: "The Ash Road",

        limit: 7,
        start: "",
        days: 7,

        ended: false,
        status: "in_progress",
        autoCycles: null,
        currentCycle: "c3",
        currentPhase: "occupation",
        phases: [
            {
                id: "occupation",
                name: "Occupation",

                description:
                    "Establish your foothold along the Ash Road. Unclaimed territories are open to challenge.",
                effects:
                    "Fight for unclaimed territories. Once every territory has an owner, agree challenges with the arbitrator.",
                grant: 0,

                rewards: {
                    win: { credits: "2d3×10", reputation: 1 },
                    loss: { credits: "d3×10", reputation: 0 },
                    draw: { credits: "d3×10", reputation: 0 },
                    sideJob: { credits: "d3×10", reputation: 0 },
                    territoryLoss: { credits: "0", reputation: 0 },
                },
            },
            {
                id: "downtime",
                name: "Downtime",

                description:
                    "A pause to recover, recruit and re-equip before the campaign resumes.",
                effects:
                    "Recover, recruit and re-equip. Each gang receives 250 credits when Downtime begins.",
                grant: 250,

                rewards: Object.fromEntries(
                    Object.keys(outcomeLabels).map((k) => [
                        k,
                        { credits: "0", reputation: 0 },
                    ]),
                ),
            },
            {
                id: "takeover",
                name: "Takeover",

                description:
                    "Defend the territories you hold and challenge your rivals for control of theirs.",
                effects:
                    "Fight over territories held by other gangs. Losing a territory reduces reputation by 1.",
                grant: 0,

                rewards: {
                    win: { credits: "2d6×10", reputation: 2 },
                    loss: { credits: "d6×10", reputation: 0 },
                    draw: { credits: "d6×10", reputation: 0 },
                    sideJob: { credits: "d6×10", reputation: 0 },
                    territoryLoss: { credits: "0", reputation: -1 },
                },
            },
        ],
        cycles: Array.from({ length: 7 }, (_, i) => ({
            id: `c${i + 1}`,
            number: i + 1,
            name: `Cycle ${i + 1}`,
            phase: i < 3 ? "occupation" : i === 3 ? "downtime" : "takeover",
            description:
                i === 2
                    ? "Finish your Occupation battles and settle territory claims before Downtime."
                    : "",
            effects: "",
        })),
        gangs: [
            {
                id: "nightshade",
                name: "Nightshade Coven",
                owner: "louis",
                colour: "violet",
                rating: 1375,
                credits: 185,
                reputation: 5,
                territories: 3,
            },
            {
                id: "iron",
                name: "Iron Vultures",
                owner: "mira",
                colour: "orange",
                rating: 1420,
                credits: 120,
                reputation: 4,
                territories: 2,
            },
            {
                id: "sump",
                name: "Sump Saints",
                owner: "tom",
                colour: "emerald",
                rating: 1240,
                credits: 240,
                reputation: 3,
                territories: 2,
            },
        ],
        battles: [
            {
                id: "b1",
                name: "The old pump station",
                cycle: "c3",
                cycleName: "Cycle 3",
                phase: "occupation",
                phaseName: "Occupation",
                participants: ["nightshade", "iron"],
                winner: "nightshade",
                sideJobs: ["nightshade"],
                rules: null,
                payouts: [
                    {
                        gang: "nightshade",
                        credits: 60,
                        reputation: 1,
                        rolls: "2, 3 + 1",
                    },
                    { gang: "iron", credits: 20, reputation: 0, rolls: "2" },
                ],
            },
            {
                id: "b2",
                name: "A toll on the Ash Road",
                cycle: "c2",
                cycleName: "Cycle 2",
                phase: "occupation",
                phaseName: "Occupation",
                participants: ["sump", "iron"],
                winner: "draw",
                sideJobs: [],
                rules: null,
                payouts: [
                    { gang: "sump", credits: 20, reputation: 0, rolls: "2" },
                    { gang: "iron", credits: 10, reputation: 0, rolls: "1" },
                ],
            },
        ],
        entries: [
            {
                id: "e1",
                text: "Cycle 3 began. Occupation continues.",
                cycle: "c3",
            },
            {
                id: "e2",
                text: "Nightshade Coven won The old pump station.",
                cycle: "c3",
            },
        ],
        grants: [],
        closedCycles: ["c1", "c2"],
    });
}
