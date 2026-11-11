// Independent display fixtures. These are examples, not an authoritative rules pack.
export const categories = [
    ["profiles", "Profiles"],
    ["weapons", "Weapons"],
    ["accessories", "Weapon accessories"],
    ["gear", "Gear"],
    ["injuries", "Injuries"],
    ["skills", "Skills"],
    ["territories", "Built-in territories"],
    ["powers", "Powers"],
    ["ranks", "Ranks"],
];
const entries = [];
function add(category, name, set, extra = {}) {
    const item = {
        id: `${category}-${entries.filter((e) => e.category === category).length + 1}`,
        category,
        name,
        set,
        pack: "Necromunda · example pack",
        ...extra,
    };
    entries.push(item);
    return item;
}
const spring = add("skills", "Spring Up", "Agility", { number: 6 });
const dodge = add("skills", "Dodge", "Agility", { number: 2 });
add("skills", "Catfall", "Agility", { number: 1 });
add("skills", "Clamber", "Agility", { number: 3 });
add("skills", "Leap", "Agility", { number: 4 });
add("skills", "Sprint", "Agility", { number: 5 });
const nerves = add("skills", "Nerves of Steel", "Ferocity", { number: 5 });
add("skills", "Berserker", "Ferocity", { number: 1 });
add("skills", "True Grit", "Ferocity", { number: 6 });
add("skills", "Fast Shot", "Shooting", { number: 1 });
add("skills", "Overwatch", "Shooting", { number: 4 });
add("skills", "Munitioneer", "Savant", { number: 4 });
const stats = [
    "5″",
    "4+",
    "4+",
    "3",
    "3",
    "1",
    "3+",
    "1",
    "7+",
    "7+",
    "7+",
    "7+",
];
[
    [
        "Escher Queen",
        "House Escher",
        "Leader",
        125,
        ["5″", "3+", "3+", "3", "3", "3", "2+", "3", "5+", "4+", "5+", "6+"],
        [spring.id],
    ],
    [
        "Escher Matriarch",
        "House Escher",
        "Champion",
        100,
        ["5″", "3+", "3+", "3", "3", "2", "2+", "2", "6+", "5+", "6+", "6+"],
        [],
    ],
    [
        "Escher Death-maiden",
        "House Escher",
        "Champion",
        115,
        ["6″", "2+", "3+", "4", "3", "2", "2+", "3", "7+", "5+", "5+", "7+"],
        [dodge.id],
    ],
    ["Escher Gang Sister", "House Escher", "Ganger", 50, stats, []],
    ["Escher Little Sister", "House Escher", "Juve", 20, stats, []],
    [
        "Goliath Forge Tyrant",
        "House Goliath",
        "Leader",
        135,
        ["4″", "3+", "4+", "4", "4", "3", "3+", "3", "5+", "4+", "8+", "7+"],
        [nerves.id],
    ],
    [
        "Goliath Bruiser",
        "House Goliath",
        "Ganger",
        55,
        ["4″", "4+", "4+", "4", "4", "1", "4+", "1", "8+", "5+", "9+", "8+"],
        [],
    ],
    ["Orlock Road Captain", "House Orlock", "Leader", 120, stats, []],
    ["Orlock Gunner", "House Orlock", "Ganger", 45, stats, []],
    ["Delaque Ghost", "House Delaque", "Ganger", 50, stats, []],
    ["Van Saar Tek", "House Van Saar", "Ganger", 65, stats, []],
    ["Cawdor Bonepicker", "House Cawdor", "Juve", 20, stats, []],
].forEach(([name, set, type, price, stats, related]) =>
    add("profiles", name, set, { type, price, stats, related, gear: [] }),
);
const wp = (name, values, traits, price = 0) => ({
    name,
    values,
    traits,
    price,
});
[
    [
        "Lasgun",
        "Basic",
        15,
        [wp("Standard", ["18″", "24″", "3", "—", "1"], ["Plentiful"])],
    ],
    [
        "Autogun",
        "Basic",
        15,
        [wp("Standard", ["12″", "24″", "3", "—", "1"], ["Rapid Fire (1)"])],
    ],
    [
        "Shotgun",
        "Basic",
        30,
        [
            wp("Solid shot", ["8″", "16″", "4", "—", "2"], ["Knockback"]),
            wp("Scatter shot", ["4″", "8″", "2", "—", "1"], ["Scattershot"]),
            wp(
                "Executioner shells",
                ["4″", "16″", "4", "-2", "2"],
                ["Knockback"],
                20,
            ),
        ],
    ],
    [
        "Boltgun",
        "Basic",
        55,
        [wp("Standard", ["12″", "24″", "4", "-1", "2"], ["Rapid Fire (1)"])],
    ],
    [
        "Plasma gun",
        "Special",
        100,
        [
            wp(
                "Low power",
                ["12″", "24″", "5", "-1", "2"],
                ["Rapid Fire (1)", "Scarce"],
            ),
            wp(
                "Maximal",
                ["12″", "24″", "7", "-2", "3"],
                ["Scarce", "Unstable"],
            ),
        ],
    ],
    [
        "Needle rifle",
        "Special",
        35,
        [
            wp(
                "Standard",
                ["9″", "18″", "—", "-2", "—"],
                ["Scarce", "Silent", "Toxin"],
            ),
        ],
    ],
    [
        "Stub gun",
        "Pistol",
        5,
        [
            wp(
                "Standard",
                ["6″", "12″", "3", "—", "1"],
                ["Pistol", "Plentiful"],
            ),
            wp(
                "Dum-dum rounds",
                ["6″", "12″", "4", "—", "1"],
                ["Pistol", "Limited"],
                5,
            ),
        ],
    ],
    [
        "Plasma pistol",
        "Pistol",
        50,
        [
            wp(
                "Low power",
                ["6″", "12″", "5", "-1", "2"],
                ["Pistol", "Scarce"],
            ),
            wp(
                "Maximal",
                ["6″", "12″", "7", "-2", "3"],
                ["Pistol", "Scarce", "Unstable"],
            ),
        ],
    ],
    [
        "Stiletto knife",
        "Close combat",
        20,
        [wp("Standard", ["—", "E", "—", "-1", "—"], ["Melee", "Toxin"])],
    ],
    [
        "Shock whip",
        "Close combat",
        25,
        [
            wp(
                "Standard",
                ["—", "3″", "S", "—", "1"],
                ["Melee", "Shock", "Versatile"],
            ),
        ],
    ],
].forEach(([name, set, price, profiles]) =>
    add("weapons", name, set, { price, profiles, slots: 1 }),
);
[
    ["Telescopic sight", 25, "Basic, Special, Heavy"],
    ["Infra-sight", 40, "Basic, Special, Heavy"],
    ["Suspensor", 60, "Heavy"],
    ["Gunshroud", 20, "Basic, Pistol, Special"],
    ["Mono-sight", 35, "Basic, Special, Heavy"],
    ["Hotshot las pack", 20, "Lasgun, Laspistol"],
].forEach(([name, price, applies]) =>
    add("accessories", name, "Weapon accessories", { price, applies }),
);
[
    "Settlement",
    "Drinking Hole",
    "Slag Furnace",
    "Tunnels",
    "Rogue Doc Shop",
    "Workshop",
].forEach((name) =>
    add("territories", name, "Dominion", {
        type: "Territory",
        applies: "Gang",
        metadata: [
            ["Assignment", "Built into a gang"],
            ["Campaign type", "Dominion"],
        ],
    }),
);
[
    "Scouring",
    "Levitation",
    "Warp Strength",
    "Dark Shield",
    "Assail",
    "Mind Lock",
].forEach((name, i) =>
    add("powers", name, i < 4 ? "Telekinesis" : "Telepathy", {
        number: i < 4 ? i + 1 : i - 3,
        applies: "Fighter (Psyker)",
    }),
);
add("ranks", "Fighter experience", "Fighter progression", {
    counter: "XP",
    metadata: [
        ["Applies to", "Fighters"],
        ["Counter", "XP"],
        ["Initial title", "New recruit"],
    ],
    levels: [
        ["6 XP", "Blooded"],
        ["16 XP", "Experienced"],
        ["31 XP", "Veteran"],
        ["51 XP", "Distinguished"],
    ],
});
add("ranks", "Specialist experience", "Fighter progression", {
    counter: "XP",
    metadata: [
        ["Applies to", "Fighter (Specialist)"],
        ["Counter", "XP"],
        ["Initial title", "Specialist"],
    ],
    levels: [
        ["6 XP", "Experienced specialist"],
        ["16 XP", "Veteran specialist"],
        ["31 XP", "Distinguished specialist"],
    ],
});
const modifier = (stat, mode, amount, scope = "Fighter") => ({
    stat,
    mode,
    amount,
    scope,
});
[
    ["Hobbled", "42", modifier("Movement", "reduce", 1)],
    ["Spinal Injury", "43", modifier("Strength", "reduce", 1)],
    ["Enfeebled", "44", modifier("Toughness", "reduce", 1)],
    ["Head Injury", "45", modifier("Intelligence", "worsen", 1)],
    ["Eye Injury", "46", modifier("Ballistic Skill", "worsen", 1)],
    ["Hand Injury", "51", modifier("Weapon Skill", "worsen", 1)],
].forEach(([name, roll, effect]) =>
    add("injuries", name, "Lasting injuries", {
        roll,
        applies: "Fighter",
        modifiers: [effect],
    }),
);
[
    ["Armoured undersuit", 25, modifier("Save", "improve", 1)],
    ["Bionic arm", 80, modifier("Strength", "increase", 1)],
    ["Bionic leg", 50, modifier("Movement", "increase", 1)],
    ["Servo harness", 130, modifier("Strength", "increase", 2)],
].forEach(([name, price, effect]) =>
    add("gear", name, "Wargear", {
        price,
        applies: "Fighter",
        modifiers: [effect],
    }),
);
entries.find((e) => e.name === "Hotshot las pack").modifiers = [
    modifier("Strength", "increase", 1, "Attached las weapon"),
    modifier("Armour penetration", "improve", 1, "Attached las weapon"),
];
export { entries };
export function searchEntries(query) {
    const words = query
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase()
        .trim()
        .split(/\s+/)
        .filter(Boolean);
    return entries
        .filter((e) => {
            const text = [
                e.name,
                e.set,
                e.type,
                e.applies,
                e.number,
                e.roll,
                ...(e.modifiers || []).flatMap((m) => [
                    m.stat,
                    m.mode,
                    m.scope,
                ]),
                ...(e.profiles || []).flatMap((p) => [p.name, ...p.traits]),
            ]
                .join(" ")
                .normalize("NFD")
                .replace(/\p{Diacritic}/gu, "")
                .toLowerCase();
            return words.every((w) => text.includes(w));
        })
        .sort((a, b) => {
            const q = query.toLowerCase().trim();
            return (
                Number(b.name.toLowerCase() === q) -
                    Number(a.name.toLowerCase() === q) ||
                Number(b.name.toLowerCase().startsWith(q)) -
                    Number(a.name.toLowerCase().startsWith(q)) ||
                a.name.localeCompare(b.name)
            );
        });
}
