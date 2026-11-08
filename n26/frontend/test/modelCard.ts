import type { EquipmentModelData, ModelCardData } from "../ui";

export const card: ModelCardData = {
    name: "Vex",
    rating: 35,
    profileName: "Ganger",
    ownerLine: "",
    typeLine: "Fighter",
    xp: 0,
    xpTarget: "–",
    statGroups: [],
    typeSpan: 1,
    weaponColumns: [],
    weapons: [],
    details: [
        {
            key: "ammo",
            label: "Ammo",
            editHref: "",
            parts: [
                {
                    kind: "counter",
                    key: "ammo-counter",
                    value: 3,
                    control: {
                        name: "Ammo",
                        assignment: "ammo-counter",
                        tallied: 0,
                        href: "/counter/",
                        back: "/equip/",
                    },
                },
            ],
        },
        {
            key: "skill",
            label: "Skills",
            editHref: "/skills/",
            parts: [
                {
                    kind: "choice",
                    key: "skill-slot",
                    chosen: null,
                    prompt: "Choose skills",
                    control: {
                        key: "skill-slot",
                        label: "Skills",
                        href: "/choose/",
                        back: "/equip/",
                        dismissHref: "/dismiss/",
                        restoreHref: "",
                        resolved: false,
                        full: false,
                        several: false,
                        followsStatus: false,
                    },
                },
            ],
        },
    ],
    stored: {
        id: "vex",
        renameHref: "/rename/",
        status: "active",
        statusHref: "/status/",
        statusLabel: "",
        statusColour: "ink",
        imageHref: "",
        modelCardsHref: "/cards/",
        rankTitles: [],
        foundingBudget: true,
        tradePointsLeft: 4,
        personalAction: "Hire",
        ratingOverride: {},
    },
};

export const model: EquipmentModelData = {
    name: "Vex",
    role: "Ganger",
    card,
    tabs: [
        { label: "Edit", href: "/edit/", current: false },
        { label: "Equip", href: "/equip/", current: true },
    ],
    switcher: {
        heading: "Equip another fighter",
        menuLabel: "Equip another fighter",
        placeholder: "Search models",
        empty: "No models",
        items: [{ label: "Rook", href: "/rook/equip/" }],
        next: null,
        source: "/fighters/",
    },
    budget: {
        activity: "hire-action",
        title: "Personal trade points",
        actionLabel: "Hire",
        facts: [
            {
                label: "Left",
                value: "4 TP",
                sub: "",
                ruled: false,
                strong: true,
            },
        ],
    },
    visitLeft: 9,
    panels: [],
};
