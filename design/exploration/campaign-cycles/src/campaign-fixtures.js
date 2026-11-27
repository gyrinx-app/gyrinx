export const gangTypes = {
    nightshade: "Escher (HoB)",
    iron: "Orlock (HoI)",
    sump: "Cawdor (HoF)",
};
export const territories = [
    ["Toll Crossing", "nightshade", 20],
    ["Old Ruins", "nightshade", 10],
    ["Collapsed Dome", "nightshade", 10],
    ["Mine Workings", "iron", 20],
    ["Slag Furnace", "iron", 10],
    ["Water Still", "sump", 10],
    ["Synth Still", "sump", 10],
    ["Bone Shrine", null, 0],
    ["Generatorium", null, 0],
    ["Fungal Grotto", null, 0],
    ["Refuse Drift", null, 0],
    ["Archaeotech Site", null, 0],
];
export const territoryNames = (id) =>
    territories
        .filter((t) => t[1] === id)
        .map((t) => t[0])
        .join(", ");
export const gangIncome = (id) =>
    territories.filter((t) => t[1] === id).reduce((n, t) => n + t[2], 0);
