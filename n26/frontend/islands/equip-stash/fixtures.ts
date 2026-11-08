import type { EquipDialog, EquipProps } from "./types";
import type { EquipmentEntry } from "../../ui";
export const harness: EquipmentEntry = {
    key: "harness",
    name: "Harness",
    basePrice: 30,
    tradePoints: null,
    exclusive: false,
    count: 0,
    expanded: false,
    copies: [],
    purchase: {
        key: "harness",
        name: "Harness",
        price: 30,
        tradePoints: null,
        exclusive: false,
        notes: [],
        parts: [],
        choices: [
            {
                choose: "one",
                options: [
                    {
                        key: "plain",
                        name: "Plain",
                        surcharge: 0,
                        checked: true,
                        setKey: "plain-set",
                        price: 0,
                    },
                    {
                        key: "armed",
                        name: "Armed",
                        surcharge: 15,
                        checked: false,
                        setKey: "armed-set",
                        price: 15,
                    },
                ],
            },
        ],
    },
};
export const gun: EquipmentEntry = {
    key: "gun",
    name: "Autogun",
    basePrice: 35,
    tradePoints: 2,
    exclusive: false,
    count: 1,
    expanded: false,
    purchase: {
        key: "gun",
        name: "Autogun",
        price: 35,
        tradePoints: 2,
        exclusive: false,
        notes: [],
        choices: [],
        parts: [
            {
                key: "warp",
                name: "Warp rounds",
                price: 10,
                tradePoints: 1,
                exclusive: false,
                notes: [],
            },
        ],
    },
    copies: [
        {
            id: "gun-copy",
            name: "Autogun",
            rating: 35,
            chosen: [],
            parts: [],
            actions: [
                {
                    label: "Sell",
                    target: "/equip/?list=house&sell=gun-copy",
                    tone: "danger",
                },
                {
                    label: "Refund",
                    target: "/equip/?list=house&refund=gun-copy",
                    tone: "danger",
                },
            ],
            accessorise: {
                label: "Add accessory",
                target: "/equip/?list=house&accessorise=gun-copy",
                tone: "primary",
            },
        },
    ],
};
export const page: EquipProps = {
    gangName: "Ashen Choir",
    gangHref: "/gang/",
    owner: { name: "Keeper", badge: null },
    scope: "house",
    scopeLabel: "House list",
    scopeTabs: [
        {
            key: "house",
            label: "House list",
            title: "",
            href: "?list=house",
            current: true,
        },
        {
            key: "stash",
            label: "In stash",
            title: "",
            href: "?list=stash",
            current: false,
        },
    ],
    section: "",
    owned: "",
    listingHref: "/equip/?list=house",
    sections: [
        {
            name: "Gear",
            categories: [{ name: "Equipment", entries: [harness, gun] }],
        },
    ],
    categories: ["Equipment"],
    categoryOptions: ["Equipment"],
    priceFloor: 30,
    priceCeiling: 35,
    tradePointsCeiling: 2,
    hasTradePoints: true,
    postIsShut: false,
    foundingBlocksVisit: false,
    tradePointsHref: "/trade-points/",
    visitingTradingPost: false,
    figures: {
        items: [
            {
                short: "Cr",
                label: "Credits",
                value: "100¢",
                absent: "",
                href: "/credits/",
            },
        ],
        roster: { count: 0, rating: 0, groups: [], models: [] },
    },
    dialog: null,
    messages: [],
    requestKey: "new-page-key",
    csrfToken: "fresh-csrf",
    action: "/equip/?list=house",
    displayHref: "/equip/display/",
    commandHref: "/equip/command/",
    recoveryKey: "equip:owner:gang",
    signInHref: "/sign-in/?next=/equip/",
};
export const sell: EquipDialog = {
    assignment: "gun-copy",
    kind: "sell",
    title: "Sell Autogun?",
    lead: "The equipment is removed from the gang.",
    name: "Autogun",
    cancel_url: "/equip/?list=house&owned=gun",
    submit_label: "Sell",
    submit_variant: "danger",
    sum: "Half of its 35¢ rating, rounded up — 18¢.",
    remove_note: "",
    models: [],
    choices: [],
    pricePreview: null,
};
export function response(data: unknown, status = 200) {
    return new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json" },
    });
}
