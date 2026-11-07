import type { ComponentProps } from "react";
import type {
    EquipmentModelData,
    EquipmentChoice,
    EquipmentEntry,
    GangFiguresData,
    UserLink,
    AlertTone,
} from "../../ui";
export type EquipDialog = {
    assignment: string;
    kind: string;
    title: string;
    lead: string;
    name: string;
    cancel_url: string;
    submit_label: string;
    submit_variant: string;
    sum?: string;
    remove_note: string;
    keepable?: string;
    keep_label?: string;
    keep_detail?: string;
    sell_all_label?: string;
    sell_all_detail?: string;
    models: Array<{ key: string; name: string }>;
    weapons?: Array<{ pk: string; label: string }>;
    accessories?: Array<{ pk: string; name: string; price: number }>;
    choices: EquipmentChoice[];
    pricePreview: {
        before: number;
        held: string[];
        refunds: Array<{
            setKey: string;
            entries: Array<{ key: string; paid: number }>;
        }>;
        resolution: Array<{
            choose: string;
            options: Array<{ setKey: string; price: number }>;
        }>;
    } | null;
};
export type EquipQuestion = {
    title: string;
    lead: string;
    heading: string;
    body: string;
    confirm_label: string;
    confirm_field: string;
    confirm_value: string;
    carry: Array<[string, string]>;
    facts: Array<{
        label: string;
        value: string;
        sub: string;
        ruled: boolean;
        strong: boolean;
    }>;
    aside: { lead: string; rest: string } | null;
    checkbox: {
        name: string;
        value: string;
        label: string;
        description: string;
        checked: boolean;
    } | null;
};
export type EquipProps = {
    model?: EquipmentModelData | null;
    gangName: string;
    gangHref: string;
    owner: ComponentProps<typeof UserLink>;
    scope: string;
    scopeLabel: string;
    scopeTabs: Array<{
        key: string;
        label: string;
        title: string;
        href: string;
        current: boolean;
    }>;
    section: string;
    owned: string;
    listingHref: string;
    sections: Array<{
        name: string;
        categories: Array<{ name: string; entries: EquipmentEntry[] }>;
    }>;
    categories: string[];
    categoryOptions: string[];
    priceFloor: number;
    priceCeiling: number;
    tradePointsCeiling: number;
    hasTradePoints: boolean;
    postIsShut: boolean;
    foundingBlocksVisit: boolean;
    tradePointsHref: string;
    visitingTradingPost: boolean;
    figures: GangFiguresData;
    dialog: EquipDialog | null;
    messages: Array<{ text: string; tone: AlertTone }>;
    requestKey: string;
    csrfToken: string;
    action: string;
    displayHref: string;
    commandHref: string;
    recoveryKey: string;
    signInHref: string;
};
export type EquipValues = {
    action: string;
    assignment: string;
    thing: string;
    list: string;
    section: string;
    owned: string;
    paid: string;
    rate: string;
    confirmed: string;
    personal_activity: string;
    selection: string;
    parts: string;
    request_key: string;
    accessories: string;
    to: string;
    weapon: string;
    miniature: string;
    accessory: string;
    display_name: string;
    display_details: string;
    change: string;
    dismissed: string;
};
export type EquipOutcome = {
    requestKey: string;
    outcome: "completed" | "confirmation";
    confirmation: EquipQuestion | null;
    page: EquipProps;
};
export type EquipDraft = {
    values: EquipValues;
    auto: boolean;
    question: EquipQuestion | null;
    dialog: EquipDialog | null;
};
export function blankValues(page: EquipProps): EquipValues {
    return {
        action: "",
        assignment: "",
        thing: "",
        list: page.scope,
        section: page.section,
        owned: page.owned,
        paid: "",
        rate: "",
        confirmed: "",
        personal_activity: page.model?.budget?.activity || "",
        selection: "[]",
        parts: "[]",
        request_key: page.requestKey,
        accessories: "stash",
        to: "",
        weapon: "",
        miniature: "",
        accessory: "",
        display_name: "",
        display_details: "[]",
        change: "",
        dismissed:
            new URL(page.action, window.location.href).searchParams.get(
                "dismissed",
            ) === "show"
                ? "show"
                : "",
    };
}
export function panelDraft(page: EquipProps, dialog: EquipDialog): EquipDraft {
    return {
        auto: false,
        question: null,
        dialog,
        values: {
            ...blankValues(page),
            action:
                dialog.kind === "fit" || dialog.kind === "detach"
                    ? "reassign"
                    : dialog.kind,
            assignment: dialog.assignment,
            display_name: dialog.name,
            display_details: JSON.stringify([dialog.lead]),
            to:
                dialog.kind === "detach"
                    ? "held"
                    : dialog.weapons?.length
                      ? "weapon"
                      : dialog.models.length
                        ? "model"
                        : "stash",
            weapon: dialog.weapons?.[0]?.pk ?? "",
            miniature: dialog.models[0]?.key ?? "",
            accessory: dialog.accessories?.[0]?.pk ?? "",
            selection: JSON.stringify(
                dialog.choices.flatMap((group) =>
                    group.options
                        .filter((option) => option.checked)
                        .map((option) => option.key),
                ),
            ),
        },
    };
}
