import type { ComponentProps } from "react";
import cotton from "../generated/cotton.json";
import { ModelScreenTabs, type ModelScreenTab } from "./ModelScreenTabs";
import { ButtonLink, Tally, Icon, type QuickSwitcherProps } from "./index";
import { ActionMenu, type ActionMenuItem } from "./ActionMenu";
import {
    ModelCard,
    isModelCard,
    FoundingMark,
    type ModelCardData,
} from "./ModelCard";

export type EquipmentModelData = {
    name: string;
    role: string;
    card: ModelCardData;
    tabs: ModelScreenTab[];
    switcher: QuickSwitcherProps;
    budget: {
        activity: string;
        title: string;
        actionLabel: string;
        facts: ComponentProps<typeof Tally>["facts"];
    } | null;
    visitLeft: number | null;
    panels: Array<{
        key: string;
        name: string;
        timing: string;
        flagged: boolean;
        menu: ActionMenuItem[];
        startHref: string;
        prices: Array<{ label: string; price: string }>;
        availableUses: number | null;
        thresholds: string[];
        problem: string;
        drafts: Array<{
            key: string;
            href: string;
            label: string;
            variant: "default" | "primary";
            problem: string;
            threshold: string;
            when: string;
            whenLabel: string;
        }>;
    }>;
};
export function EquipmentModel({
    model,
    csrfToken,
    frozen,
    countersFrozen,
    pendingTally,
    onTally,
}: {
    model: EquipmentModelData;
    csrfToken: string;
    frozen: boolean;
    countersFrozen: boolean;
    pendingTally?: string;
    onTally: (assignment: string, change: number, name: string) => void;
}) {
    return (
        <div>
            <div
                className={
                    model.panels.length
                        ? "mt-3 grid items-start gap-4 lg:grid-cols-2"
                        : "mt-3 lg:max-w-1/2"
                }
            >
                <ModelCard
                    card={model.card}
                    csrfToken={csrfToken}
                    frozen={frozen}
                    countersFrozen={countersFrozen}
                    pendingTally={pendingTally}
                    onTally={onTally}
                />
                {!!model.panels.length && (
                    <div className={cotton.modelCard.panels}>
                        <div className="divide-y divide-box-border">
                            {model.panels.map((panel) => (
                                <section
                                    key={panel.key}
                                    aria-label={panel.name}
                                >
                                    <div
                                        className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 ${panel.flagged ? "border-b border-box-border bg-blue-50 dark:bg-blue-950/20" : ""}`}
                                    >
                                        <div className="flex items-center gap-1.5">
                                            {panel.flagged && (
                                                <Icon
                                                    name="circle-fading-arrow-up"
                                                    className="size-4 text-blue-600 dark:text-blue-400"
                                                    label="Waiting"
                                                />
                                            )}
                                            <h3 className="font-semibold">
                                                {panel.name}
                                            </h3>
                                        </div>
                                        <div className="ml-auto flex items-center gap-1">
                                            <ActionMenu
                                                items={panel.menu}
                                                label={`More for ${panel.name}`}
                                                variant="ghost"
                                            />
                                            {panel.startHref && (
                                                <ButtonLink
                                                    href={panel.startHref}
                                                    variant="primary"
                                                    size="sm"
                                                    aria-label={`Start ${panel.name} flow`}
                                                >
                                                    Start →
                                                </ButtonLink>
                                            )}
                                            {panel.drafts.length === 1 && (
                                                <ButtonLink
                                                    href={panel.drafts[0].href}
                                                    variant={
                                                        panel.drafts[0].variant
                                                    }
                                                    size="sm"
                                                    aria-label={
                                                        panel.drafts[0].label
                                                    }
                                                >
                                                    {panel.drafts[0].problem
                                                        ? "View"
                                                        : "Resume"}{" "}
                                                    →
                                                </ButtonLink>
                                            )}
                                        </div>
                                    </div>
                                    <div className="space-y-2 px-4 pb-4 pt-3 text-sm">
                                        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-muted">
                                            <span>{panel.timing}</span>
                                            {panel.prices.map(
                                                (price, index) => (
                                                    <span key={index}>
                                                        Price{" "}
                                                        <strong className="text-ink-900 tabular-nums dark:text-ink-100">
                                                            {price.price}
                                                        </strong>
                                                        {price.label &&
                                                            ` ${price.label}`}
                                                    </span>
                                                ),
                                            )}
                                        </p>
                                        {!!panel.availableUses && (
                                            <div className="space-y-1">
                                                <p className="font-medium">
                                                    {panel.availableUses}{" "}
                                                    {panel.availableUses === 1
                                                        ? "use"
                                                        : "uses"}{" "}
                                                    available
                                                </p>
                                                {!!panel.thresholds.length && (
                                                    <p className="text-muted">
                                                        Earned at{" "}
                                                        {panel.thresholds.join(
                                                            ", ",
                                                        )}
                                                        .
                                                        {panel.thresholds
                                                            .length > 1 &&
                                                            ` The next use was earned at ${panel.thresholds[0]}.`}
                                                    </p>
                                                )}
                                            </div>
                                        )}
                                        {panel.drafts.length === 1 && (
                                            <div className="space-y-1 border-t border-box-border pt-3">
                                                <p className="font-medium">
                                                    {panel.drafts[0].problem
                                                        ? "On hold"
                                                        : "In progress"}
                                                </p>
                                                {panel.drafts[0].threshold && (
                                                    <p className="text-muted">
                                                        Earned at{" "}
                                                        {
                                                            panel.drafts[0]
                                                                .threshold
                                                        }
                                                        .
                                                    </p>
                                                )}
                                                {panel.drafts[0].problem && (
                                                    <p className="text-muted">
                                                        {
                                                            panel.drafts[0]
                                                                .problem
                                                        }
                                                    </p>
                                                )}
                                            </div>
                                        )}
                                        {panel.problem && (
                                            <p className="text-muted">
                                                {panel.problem}
                                            </p>
                                        )}
                                        {panel.drafts.length > 1 && (
                                            <div className="space-y-2">
                                                {panel.drafts.map(
                                                    (draft, index) => (
                                                        <div
                                                            key={draft.key}
                                                            className="flex flex-wrap items-center justify-between gap-2"
                                                        >
                                                            <time
                                                                dateTime={
                                                                    draft.when
                                                                }
                                                                className="text-muted"
                                                            >
                                                                Started{" "}
                                                                {
                                                                    draft.whenLabel
                                                                }
                                                            </time>
                                                            {draft.threshold && (
                                                                <span className="text-muted">
                                                                    Earned at{" "}
                                                                    {
                                                                        draft.threshold
                                                                    }
                                                                    .
                                                                </span>
                                                            )}
                                                            {draft.problem && (
                                                                <p className="text-muted">
                                                                    {
                                                                        draft.problem
                                                                    }
                                                                </p>
                                                            )}
                                                            <ButtonLink
                                                                href={
                                                                    draft.href
                                                                }
                                                                variant={
                                                                    draft.variant
                                                                }
                                                                size="sm"
                                                                aria-label={`${draft.label} ${index + 1}`}
                                                            >
                                                                {draft.problem
                                                                    ? "View"
                                                                    : "Resume"}{" "}
                                                                {index + 1} →
                                                            </ButtonLink>
                                                        </div>
                                                    ),
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </section>
                            ))}
                        </div>
                    </div>
                )}
            </div>
            <ModelScreenTabs tabs={model.tabs} />
        </div>
    );
}
export function EquipmentBudget({
    model,
    tradePointsHref,
}: {
    model: EquipmentModelData;
    tradePointsHref: string;
}) {
    if (!model.budget) return null;
    return (
        <>
            <div className="self-start rounded-box border border-box-border p-3">
                <p className="flex items-start gap-1.5 text-sm font-medium">
                    <FoundingMark />
                    {model.budget.title}
                </p>
                <p className="mt-0.5 text-xs text-muted">
                    {model.name} can spend these trade points at the Trading
                    Post while the {model.budget.actionLabel} action is open.
                    Equipment list purchases do not spend trade points.
                </p>
                <div className="mt-2 text-sm">
                    <Tally facts={model.budget.facts} />
                </div>
            </div>
            {model.visitLeft !== null && (
                <div className="self-start rounded-box border border-box-border p-3">
                    <p className="text-sm font-medium">Trading Post visit</p>
                    <p className="mt-0.5 text-xs text-muted">
                        The visit is open with{" "}
                        <strong>{model.visitLeft} TP</strong> left. Purchases
                        that spend trade points use {model.name}'s personal
                        allowance while the {model.budget.actionLabel} action is
                        open.
                    </p>
                    <ButtonLink
                        href={tradePointsHref}
                        size="xs"
                        className="mt-2"
                    >
                        Manage visit
                    </ButtonLink>
                </div>
            )}
        </>
    );
}

export function isEquipmentModel(value: unknown): value is EquipmentModelData {
    const object = (value: unknown): value is Record<string, unknown> =>
        !!value && typeof value === "object" && !Array.isArray(value);
    const texts = (value: Record<string, unknown>, names: string[]) =>
        names.every((name) => typeof value[name] === "string");
    const list = (
        value: unknown,
        valid: (value: unknown) => boolean,
    ): boolean => Array.isArray(value) && value.every(valid);
    const href = (value: unknown) => {
        try {
            return (
                typeof value === "string" &&
                new URL(value, window.location.href).origin ===
                    window.location.origin
            );
        } catch {
            return false;
        }
    };
    const fact = (value: unknown) =>
        object(value) &&
        texts(value, ["label", "value", "sub"]) &&
        typeof value.ruled === "boolean" &&
        typeof value.strong === "boolean";
    if (
        !object(value) ||
        !texts(value, ["name", "role"]) ||
        !isModelCard(value.card) ||
        !object(value.switcher)
    )
        return false;
    const switcher = value.switcher;
    return (
        list(
            value.tabs,
            (tab) =>
                object(tab) &&
                texts(tab, ["label", "href"]) &&
                href(tab.href) &&
                typeof tab.current === "boolean",
        ) &&
        texts(switcher, [
            "heading",
            "menuLabel",
            "placeholder",
            "empty",
            "source",
        ]) &&
        href(switcher.source) &&
        (switcher.next === null || typeof switcher.next === "number") &&
        list(
            switcher.items,
            (item) =>
                object(item) &&
                texts(item, ["label", "href"]) &&
                href(item.href),
        ) &&
        (value.visitLeft === null || typeof value.visitLeft === "number") &&
        (value.budget === null ||
            (object(value.budget) &&
                texts(value.budget, ["activity", "title", "actionLabel"]) &&
                list(value.budget.facts, fact))) &&
        list(
            value.panels,
            (panel) =>
                object(panel) &&
                texts(panel, [
                    "key",
                    "name",
                    "timing",
                    "startHref",
                    "problem",
                ]) &&
                href(panel.startHref) &&
                typeof panel.flagged === "boolean" &&
                (panel.availableUses === null ||
                    typeof panel.availableUses === "number") &&
                list(panel.thresholds, (item) => typeof item === "string") &&
                list(
                    panel.menu,
                    (item) =>
                        object(item) &&
                        texts(item, ["label", "href", "tone"]) &&
                        href(item.href) &&
                        ["default", "danger"].includes(String(item.tone)) &&
                        typeof item.separatorBefore === "boolean",
                ) &&
                list(
                    panel.prices,
                    (price) =>
                        object(price) && texts(price, ["label", "price"]),
                ) &&
                list(
                    panel.drafts,
                    (draft) =>
                        object(draft) &&
                        texts(draft, [
                            "key",
                            "href",
                            "label",
                            "variant",
                            "problem",
                            "threshold",
                            "when",
                            "whenLabel",
                        ]) &&
                        href(draft.href) &&
                        ["default", "primary"].includes(String(draft.variant)),
                ),
        )
    );
}
