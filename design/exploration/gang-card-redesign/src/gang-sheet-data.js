// Fixed display data for the independent gang-page design preview.
export const physical = ["M", "WS", "BS", "S", "T", "W", "I", "A", "Sv"];
export const mental = ["Ld", "Cl", "Wil", "Int"];
export const archetypes = [
    "Leader",
    "Champion",
    "Ganger",
    "Prospect",
    "Juve",
    "Vehicle",
];
export const profiles = {
    vesper: {
        stats: ["5″", "3+", "3+", "3", "3", "3", "2+", "3", "5+"],
        mind: ["5+", "4+", "5+", "6+"],
        xp: "12/19",
        skills: "Spring up, Commanding presence",
    },
    nyx: {
        stats: ["5″", "3+", "3+", "3", "3", "2", "2+", "2", "5+"],
        mind: ["6+", "5+", "6+", "6+"],
        xp: "7/13",
        skills: "Spring up",
    },
    ash: {
        stats: ["6″", "2+", "3+", "4", "3", "2", "2+", "3", "6+"],
        mind: ["7+", "5+", "5+", "7+"],
        xp: "8/13",
        skills: "Combat virtuoso",
    },
};
export const cardExamples = {
    vesper: {
        image: "/static/cards/dog-golden.jpg",
        counters: [["Kills", "3"]],
        rules: "Gang Hierarchy (Leader), Group Activation (2)",
        actions: ["Select a skill", "Spend built-in TP"],
        lore: "Vesper leads the Nightshade Coven from the chem-pits of Dustfall.",
        notes: "Keep the Phyrr cats with their owner.",
    },
    nyx: {
        image: "/static/cards/dog-corgi.jpg",
        actions: ["Select a skill"],
        rules: "Gang Hierarchy (Champion), Group Activation (1)",
        accessories: { "Needle rifle": "Telescopic sight" },
    },
    ash: {
        status: "In recovery",
        image: "/static/cards/dog-husky.jpg",
        actions: ["Resolve lasting injury"],
        rules: "Gang Hierarchy (Champion)",
    },
    sera: { status: "Captured" },
    jade: { image: "/static/cards/dog-corgi.jpg" },
    wren: {
        image: "/static/cards/dog-golden.jpg",
        gearGroups: [["Equipment", "Respirator"]],
    },
    echo: {
        powers: "Dark Shield",
        counters: [
            ["Kills", "2"],
            ["Battles", "7"],
        ],
        rules: "Gang Fighter (Juve), Hot-headed",
        gearGroups: [
            ["Equipment", "Respirator, Photo-goggles, Medicae kit"],
            ["Injuries", "Old battle wound, Hobbled"],
        ],
        gear: "Stub gun · Fighting knife · Lasgun · Shotgun · Autogun · Needle pistol",
    },
};
export const weaponTraits = {
    "Plasma pistol": "Pistol, Scarce",
    "Shock whip": "Melee, Shock, Versatile",
    "Needle rifle": "Scarce, Silent, Toxin",
    "Stiletto knife": "Melee, Toxin",
    "Venom claw": "Melee, Toxin",
    "Needle pistol": "Pistol, Scarce, Silent, Toxin",
    Lasgun: "Plentiful",
    Shotgun: "Knockback",
    "Fighting knife": "Melee",
    Autogun: "Rapid Fire (1)",
    Bow: "Silent",
    Whip: "Melee, Versatile",
    "Stub gun": "Pistol, Plentiful",
    "Heavy stubber": "Rapid Fire (2), Unwieldy",
    "Claws and teeth": "Melee",
};
