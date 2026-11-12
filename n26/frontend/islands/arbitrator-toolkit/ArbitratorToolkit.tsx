import { useState, type ComponentProps } from "react";
import {
    WorkflowLayout,
    WorkflowPage,
    Breadcrumbs,
    Button,
    ButtonLink,
    FormActions,
    FormSection,
    Field,
    FieldErrors,
    Input,
    Textarea,
    NativeSelect,
    RadioCards,
    RadioCard,
    CheckboxCard,
    CheckboxCardItem,
    Card,
    Link,
    Badge,
    Icon,
    TabLinks,
    Tooltip,
    useWorkflowForm,
} from "../../ui";

type Reward = {
    kind: string;
    amount: number;
    id?: string;
    name?: string;
    icon?: string;
    info?: string;
    label?: string;
};
type Payload = {
    title: string;
    narrative: string;
    body: string;
    mode: string;
    choices: number;
    rewards: Reward[];
    recipients_mode: string;
    target: string;
    gangs: string[];
    players: string[];
    inform_all: boolean;
    events: string[];
    selected: number[];
    receipt?: string;
    tag?: string;
};
const empty: Payload = {
    title: "",
    narrative: "",
    body: "",
    mode: "bundle",
    choices: 1,
    rewards: [],
    recipients_mode: "selected",
    target: "gangs",
    gangs: [],
    players: [],
    inform_all: false,
    events: [],
    selected: [],
};
type Tag = {
    id: string;
    name: string;
    icon: string;
    info: string;
    gang: string;
    removeHref: string;
};
type Receipt = {
    id: string;
    gang: string;
    gangHref: string;
    resolved: boolean;
    selected: number[];
    chooseHref: string;
};
export type ToolkitProps = {
    campaignName: string;
    campaignHref: string;
    toolkitHref: string;
    isArbitrator: boolean;
    screen: "home" | "form" | "detail";
    tab?: string;
    interventions?: {
        id: string;
        title: string;
        href: string;
        mode: string;
        summary: string;
        date: string;
        recipients: number;
        pending: number;
    }[];
    communications?: {
        id: string;
        title: string;
        body: string;
        date: string;
    }[];
    alerts?: { value: string; label: string }[];
    enabledAlerts?: string[];
    tags?: Tag[];
    newIntervention?: string;
    newCommunication?: string;
    editAlerts?: string;
    actionKind?: string;
    icons?: string[];
    alertEvents?: { value: string; label: string }[];
    catalogue?: {
        id: string;
        kind: string;
        name: string;
        detail: string;
        rating: number;
    }[];
    gangs?: { id: string; name: string; owner: string }[];
    players?: { id: string; name: string; owner: string }[];
    receipt?: {
        title: string;
        gang: string;
        choices: number;
        rewards: Reward[];
        narrative: string;
    } | null;
    tag?: { name: string; gang: string } | null;
    values?: { request_key: string; payload: string };
    errors?: Record<string, string[]>;
    csrfToken?: string;
    commandHref?: string;
    recoveryKey?: string;
    title?: string;
    narrative?: string;
    mode?: string;
    choices?: number;
    rewards?: Reward[];
    informAll?: boolean;
    receipts?: Receipt[];
};
function Glyph({
    name,
    ...props
}: { name: string } & Omit<ComponentProps<typeof Icon>, "name">) {
    return (
        <Icon
            {...props}
            name={name as ComponentProps<typeof Icon>["name"]}
            strokeWidth={1.7}
        />
    );
}
function date(value: string) {
    return new Date(value).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}
function Breadcrumb({ p, current }: { p: ToolkitProps; current?: string }) {
    const toolkitLabel = (
        <span className="inline-flex items-center gap-1">
            <Glyph name="tool-case" />
            Arbitrator Toolkit
        </span>
    );
    return (
        <Breadcrumbs
            items={[
                { label: "Campaigns", href: "/n26/campaigns/" },
                { label: p.campaignName, href: p.campaignHref },
                ...(p.isArbitrator
                    ? current
                        ? [
                              { label: toolkitLabel, href: p.toolkitHref },
                              { label: current },
                          ]
                        : [{ label: toolkitLabel }]
                    : [{ label: current ?? "Intervention" }]),
            ]}
        />
    );
}
function Home(p: ToolkitProps) {
    const tab = p.tab ?? "interventions";
    const tabs = [
        ["interventions", "Interventions"],
        ["communications", "Communications"],
        ["alerts", "Alerts"],
        ["tags", "Tags"],
    ].map(([value, label]) => ({
        label,
        href: p.toolkitHref + "?tab=" + value,
        current: tab === value,
    }));
    return (
        <WorkflowLayout
            footer={null}
            fullWidth
            title="Arbitrator Toolkit"
            lead={p.campaignName}
            breadcrumb={<Breadcrumb p={p} />}
            actions={
                <ButtonLink href={p.campaignHref} size="sm">
                    Back to campaign
                </ButtonLink>
            }
        >
            <div className="grid gap-4 md:grid-cols-3">
                {[
                    {
                        icon: "gift",
                        name: "Interventions",
                        text: "Give rewards, offer choices and assign tags.",
                        href: p.newIntervention!,
                        button: "Make an intervention",
                    },
                    {
                        icon: "send",
                        name: "Communications",
                        text: "Send a message to players in this campaign.",
                        href: p.newCommunication!,
                        button: "Write a communication",
                    },
                    {
                        icon: "bell",
                        name: "Alerts",
                        text: `${p.enabledAlerts?.length ?? 0} campaign alerts enabled.`,
                        href: p.editAlerts!,
                        button: "Set alerts",
                    },
                ].map((item) => (
                    <Card key={item.name}>
                        <div className="flex h-full flex-col items-start gap-3">
                            <h2 className="flex items-center gap-2 text-base font-semibold">
                                <Glyph name={item.icon} />
                                {item.name}
                            </h2>
                            <p className="grow text-sm text-muted">
                                {item.text}
                            </p>
                            <ButtonLink
                                href={item.href}
                                size="sm"
                                variant="primary"
                            >
                                {item.button}
                            </ButtonLink>
                        </div>
                    </Card>
                ))}
            </div>
            <TabLinks label="Toolkit sections" tabs={tabs} />
            {tab === "interventions" && (
                <Card header={<h2 className="font-semibold">Interventions</h2>}>
                    <div className="divide-y divide-box-border">
                        {!p.interventions?.length && (
                            <p className="text-sm text-muted">
                                No interventions yet. Make an intervention to
                                send rewards or tags.
                            </p>
                        )}
                        {p.interventions?.map((i) => (
                            <div
                                key={i.id}
                                className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                            >
                                <div className="min-w-0">
                                    <Link href={i.href}>{i.title}</Link>
                                    <p className="mt-1 text-sm text-muted">
                                        {i.summary}
                                    </p>
                                    <p className="mt-1 text-xs text-muted">
                                        {date(i.date)} · {i.recipients}{" "}
                                        {i.recipients === 1
                                            ? "recipient"
                                            : "recipients"}
                                    </p>
                                </div>
                                <Badge color={i.pending ? "amber" : "ink"}>
                                    {i.pending
                                        ? `${i.pending} awaiting a choice`
                                        : "Applied"}
                                </Badge>
                            </div>
                        ))}
                    </div>
                </Card>
            )}
            {tab === "communications" && (
                <Card
                    header={
                        <h2 className="font-semibold">Sent communications</h2>
                    }
                >
                    <div className="divide-y divide-box-border">
                        {!p.communications?.length && (
                            <p className="text-sm text-muted">
                                No communications yet. Write a communication to
                                message your players.
                            </p>
                        )}
                        {p.communications?.map((c) => (
                            <div
                                key={c.id}
                                className="space-y-2 py-3 first:pt-0 last:pb-0"
                            >
                                <h3 className="font-semibold">{c.title}</h3>
                                <p className="whitespace-pre-wrap text-sm">
                                    {c.body}
                                </p>
                                <p className="text-xs text-muted">
                                    {date(c.date)}
                                </p>
                            </div>
                        ))}
                    </div>
                </Card>
            )}
            {tab === "alerts" && (
                <Card
                    header={<h2 className="font-semibold">Campaign alerts</h2>}
                >
                    <div className="space-y-4">
                        <p className="text-sm text-muted">
                            Enabled events send a site notification to you as
                            the arbitrator.
                        </p>
                        {p.alerts?.map((a) => (
                            <div
                                key={a.value}
                                className="flex items-center justify-between gap-3"
                            >
                                <span className="text-sm">{a.label}</span>
                                <Badge
                                    color={
                                        p.enabledAlerts?.includes(a.value)
                                            ? "amber"
                                            : "ink"
                                    }
                                >
                                    {p.enabledAlerts?.includes(a.value)
                                        ? "On"
                                        : "Off"}
                                </Badge>
                            </div>
                        ))}
                    </div>
                </Card>
            )}
            {tab === "tags" && (
                <Card
                    header={
                        <h2 className="font-semibold">Player and gang tags</h2>
                    }
                >
                    <div className="divide-y divide-box-border">
                        {!p.tags?.length && (
                            <p className="text-sm text-muted">
                                No tags assigned yet. Make an intervention to
                                assign a tag.
                            </p>
                        )}
                        {p.tags?.map((t) => (
                            <div
                                key={t.id}
                                className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
                            >
                                <div>
                                    <h3 className="flex items-center gap-2 font-semibold">
                                        <Glyph name={t.icon} />
                                        {t.name}
                                    </h3>
                                    <p className="mt-1 text-sm text-muted">
                                        {t.gang}
                                    </p>
                                    {t.info && (
                                        <p className="mt-1 whitespace-pre-wrap text-sm">
                                            {t.info}
                                        </p>
                                    )}
                                </div>
                                <ButtonLink
                                    href={t.removeHref}
                                    size="sm"
                                    variant="ghost"
                                >
                                    Remove
                                </ButtonLink>
                            </div>
                        ))}
                    </div>
                </Card>
            )}
        </WorkflowLayout>
    );
}
function Detail(p: ToolkitProps) {
    return (
        <WorkflowLayout
            footer={null}
            title={p.title!}
            lead={p.campaignName}
            breadcrumb={<Breadcrumb p={p} current={p.title} />}
            actions={
                p.isArbitrator ? (
                    <ButtonLink size="sm" href={p.toolkitHref}>
                        <Glyph name="tool-case" />
                        Arbitrator Toolkit
                    </ButtonLink>
                ) : undefined
            }
        >
            {p.narrative && (
                <p className="whitespace-pre-wrap text-sm">{p.narrative}</p>
            )}
            <Card
                header={
                    <h2 className="font-semibold">
                        {p.mode === "choice"
                            ? `Choose exactly ${p.choices} rewards`
                            : "Rewards"}
                    </h2>
                }
            >
                <ul className="space-y-3">
                    {p.rewards?.map((r, i) => (
                        <li key={i} className="text-sm">
                            <div className="flex items-center gap-2">
                                {r.icon && <Glyph name={r.icon} />}
                                <span>{r.label}</span>
                            </div>
                            {r.info && (
                                <p className="mt-1 text-muted">{r.info}</p>
                            )}
                        </li>
                    ))}
                </ul>
            </Card>
            <FormSection title="Recipients">
                {p.receipts?.map((r) => (
                    <Card key={r.id}>
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <Link href={r.gangHref}>{r.gang}</Link>
                            {r.resolved ? (
                                <Badge color="ink">Applied</Badge>
                            ) : r.chooseHref ? (
                                <ButtonLink
                                    href={r.chooseHref}
                                    variant="primary"
                                >
                                    Choose rewards
                                </ButtonLink>
                            ) : (
                                <Badge>Awaiting a choice</Badge>
                            )}
                        </div>
                        {r.resolved && (
                            <p className="mt-2 text-sm text-muted">
                                {r.selected
                                    .map((i) => p.rewards?.[i]?.label)
                                    .join(", ")}
                            </p>
                        )}
                    </Card>
                ))}
            </FormSection>
            {p.informAll && (
                <p className="text-sm text-muted">
                    All campaign players are notified of the offer and each
                    confirmed choice.
                </p>
            )}
        </WorkflowLayout>
    );
}
function ToolkitForm(p: ToolkitProps) {
    const action = p.actionKind!;
    const title = (
        {
            intervention: "Make an intervention",
            communication: "Write a communication",
            alerts: "Set alerts",
            choose: "Choose rewards",
            remove_tag: "Remove tag",
        } as Record<string, string>
    )[action];
    const form = useWorkflowForm({
        values: p.values!,
        errors: p.errors!,
        commandHref: p.commandHref!,
        csrfToken: p.csrfToken!,
        recoveryKey: p.recoveryKey!,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
            if (
                status === 422 &&
                data.errors &&
                typeof data.errors === "object"
            )
                return {
                    kind: "invalid",
                    errors: data.errors as Record<string, string[]>,
                };
            return null;
        },
    });
    let data: Payload;
    try {
        data = { ...empty, ...JSON.parse(form.values.payload) };
    } catch {
        data = { ...empty };
    }
    const set = (part: Partial<Payload>) =>
        form.setValues({
            ...form.values,
            payload: JSON.stringify({ ...data, ...part }),
        });
    const [search, setSearch] = useState("");
    const updateReward = (index: number, part: Partial<Reward>) =>
        set({
            rewards: data.rewards.map((r, i) =>
                i === index ? { ...r, ...part } : r,
            ),
        });
    const targetPlayers = data.target === "players";
    const targets = targetPlayers ? (p.players ?? []) : (p.gangs ?? []);
    const selectedTargets = targetPlayers ? data.players : data.gangs;
    const targetNames = (
        data.recipients_mode === "all"
            ? targets
            : targets.filter((g) => selectedTargets.includes(g.id))
    ).map((g) => g.name);
    const rewardText = (r: Reward) =>
        r.kind === "credits"
            ? `${r.amount}¢`
            : r.kind === "tag"
              ? r.name || "Unnamed tag"
              : `${r.amount} × ${p.catalogue?.find((c) => c.kind === r.kind && c.id === r.id)?.name || "Select a reward"}`;
    return (
        <WorkflowPage
            title={title}
            lead={p.campaignName}
            breadcrumb={<Breadcrumb p={p} current={title} />}
            method="post"
            onSubmit={form.save}
            aria-busy={form.pending}
            footer={
                <FormActions>
                    <Button
                        type="submit"
                        variant={action === "remove_tag" ? "danger" : "success"}
                        busy={form.pending}
                        disabled={form.pending}
                    >
                        {form.uncertain
                            ? "Retry save"
                            : (
                                  {
                                      intervention: "Send intervention",
                                      communication: "Send communication",
                                      alerts: "Save alerts",
                                      choose: "Confirm choices",
                                      remove_tag: "Remove tag",
                                  } as Record<string, string>
                              )[action]}
                    </Button>
                    <ButtonLink
                        href={p.isArbitrator ? p.toolkitHref : p.campaignHref}
                        variant="ghost"
                    >
                        Cancel
                    </ButtonLink>
                </FormActions>
            }
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={p.csrfToken}
            />
            <input
                type="hidden"
                name="request_key"
                value={form.values.request_key}
            />
            <input type="hidden" name="payload" value={form.values.payload} />
            {form.hasErrors && (
                <div ref={form.summary} tabIndex={-1} role="alert">
                    <FieldErrors
                        errors={[
                            ...Object.values(form.errors).flat(),
                            ...(form.notice ? [form.notice] : []),
                        ]}
                    />
                </div>
            )}
            <fieldset disabled={form.frozen} className="contents">
                {(action === "intervention" || action === "communication") && (
                    <>
                        <FormSection
                            title={
                                action === "intervention"
                                    ? "Intervention"
                                    : "Message"
                            }
                        >
                            <Field label="Title *" htmlFor="toolkit-title">
                                <Input
                                    name="title_display"
                                    required
                                    maxLength={200}
                                    value={data.title}
                                    onChange={(e) =>
                                        set({ title: e.target.value })
                                    }
                                />
                            </Field>
                            <Field
                                label={
                                    action === "intervention"
                                        ? "Accompanying text"
                                        : "Message *"
                                }
                                htmlFor="toolkit-body"
                                description={
                                    action === "intervention"
                                        ? "Included with the rewards and in notifications."
                                        : "The notification includes a link to this campaign."
                                }
                            >
                                <Textarea
                                    rows={4}
                                    required={action === "communication"}
                                    maxLength={10000}
                                    value={
                                        action === "intervention"
                                            ? data.narrative
                                            : data.body
                                    }
                                    onChange={(e) =>
                                        set(
                                            action === "intervention"
                                                ? { narrative: e.target.value }
                                                : { body: e.target.value },
                                        )
                                    }
                                />
                            </Field>
                        </FormSection>
                        {action === "intervention" && (
                            <FormSection title="Rewards">
                                <RadioCards legend="Apply rewards" min="12rem">
                                    <RadioCard
                                        name="reward_mode"
                                        value="bundle"
                                        label="All rewards"
                                        description="Every recipient receives everything listed."
                                        checked={data.mode === "bundle"}
                                        onChange={() => set({ mode: "bundle" })}
                                    />
                                    <RadioCard
                                        name="reward_mode"
                                        value="choice"
                                        label="Offer a choice"
                                        description="Each recipient confirms their own rewards."
                                        checked={data.mode === "choice"}
                                        onChange={() => set({ mode: "choice" })}
                                    />
                                </RadioCards>
                                {data.mode === "choice" && (
                                    <Field
                                        label="Number of rewards to choose *"
                                        htmlFor="toolkit-limit"
                                    >
                                        <Input
                                            type="number"
                                            min={1}
                                            max={Math.max(
                                                data.rewards.length,
                                                1,
                                            )}
                                            required
                                            value={data.choices}
                                            onChange={(e) =>
                                                set({
                                                    choices: Number(
                                                        e.target.value,
                                                    ),
                                                })
                                            }
                                        />
                                    </Field>
                                )}
                                {data.rewards.map((reward, index) => (
                                    <Card
                                        key={index}
                                        header={
                                            <div className="flex items-center justify-between gap-2">
                                                <h3 className="text-sm font-semibold">
                                                    {data.mode === "choice"
                                                        ? "Option"
                                                        : "Reward"}{" "}
                                                    {index + 1}
                                                </h3>
                                                {data.rewards.length > 1 && (
                                                    <Button
                                                        size="xs"
                                                        variant="ghost"
                                                        aria-label={`Remove reward ${index + 1}`}
                                                        onClick={() =>
                                                            set({
                                                                rewards:
                                                                    data.rewards.filter(
                                                                        (
                                                                            _,
                                                                            i,
                                                                        ) =>
                                                                            i !==
                                                                            index,
                                                                    ),
                                                            })
                                                        }
                                                    >
                                                        <Glyph name="x" />
                                                    </Button>
                                                )}
                                            </div>
                                        }
                                    >
                                        <div className="space-y-4">
                                            <Field
                                                label="Type"
                                                htmlFor={`reward-kind-${index}`}
                                            >
                                                <NativeSelect
                                                    value={reward.kind}
                                                    onChange={(e) =>
                                                        updateReward(index, {
                                                            kind: e.target
                                                                .value,
                                                            id: "",
                                                            amount: 1,
                                                            icon: "crosshair",
                                                            name: "",
                                                            info: "",
                                                        })
                                                    }
                                                >
                                                    {(targetPlayers
                                                        ? [
                                                              [
                                                                  "tag",
                                                                  "Player tag",
                                                              ],
                                                          ]
                                                        : [
                                                              [
                                                                  "credits",
                                                                  "Credits",
                                                              ],
                                                              [
                                                                  "weapon",
                                                                  "Weapon",
                                                              ],
                                                              [
                                                                  "equipment",
                                                                  "Equipment",
                                                              ],
                                                              [
                                                                  "resource",
                                                                  "Resource",
                                                              ],
                                                              [
                                                                  "profile",
                                                                  "Fighter or vehicle",
                                                              ],
                                                              [
                                                                  "tag",
                                                                  "Gang tag",
                                                              ],
                                                          ]
                                                    ).map(([value, label]) => (
                                                        <option
                                                            key={value}
                                                            value={value}
                                                        >
                                                            {label}
                                                        </option>
                                                    ))}
                                                </NativeSelect>
                                            </Field>
                                            {reward.kind === "tag" ? (
                                                <>
                                                    <Field
                                                        label="Tag name *"
                                                        htmlFor={`tag-name-${index}`}
                                                    >
                                                        <Input
                                                            required
                                                            maxLength={80}
                                                            value={
                                                                reward.name ??
                                                                ""
                                                            }
                                                            onChange={(e) =>
                                                                updateReward(
                                                                    index,
                                                                    {
                                                                        name: e
                                                                            .target
                                                                            .value,
                                                                    },
                                                                )
                                                            }
                                                        />
                                                    </Field>
                                                    <fieldset className="space-y-2">
                                                        <legend className="text-sm font-medium">
                                                            Icon
                                                        </legend>
                                                        <div className="flex flex-wrap gap-2">
                                                            {p.icons?.map(
                                                                (icon) => (
                                                                    <Tooltip
                                                                        key={
                                                                            icon
                                                                        }
                                                                        label={
                                                                            icon
                                                                        }
                                                                        size="sm"
                                                                    >
                                                                        <Button
                                                                            variant={
                                                                                reward.icon ===
                                                                                icon
                                                                                    ? "primary"
                                                                                    : "default"
                                                                            }
                                                                            aria-label={
                                                                                icon
                                                                            }
                                                                            aria-pressed={
                                                                                reward.icon ===
                                                                                icon
                                                                            }
                                                                            onClick={() =>
                                                                                updateReward(
                                                                                    index,
                                                                                    {
                                                                                        icon,
                                                                                    },
                                                                                )
                                                                            }
                                                                        >
                                                                            <Glyph
                                                                                name={
                                                                                    icon
                                                                                }
                                                                            />
                                                                        </Button>
                                                                    </Tooltip>
                                                                ),
                                                            )}
                                                        </div>
                                                    </fieldset>
                                                    <Field
                                                        label="Information"
                                                        htmlFor={`tag-info-${index}`}
                                                    >
                                                        <Textarea
                                                            rows={2}
                                                            maxLength={1000}
                                                            value={
                                                                reward.info ??
                                                                ""
                                                            }
                                                            onChange={(e) =>
                                                                updateReward(
                                                                    index,
                                                                    {
                                                                        info: e
                                                                            .target
                                                                            .value,
                                                                    },
                                                                )
                                                            }
                                                        />
                                                    </Field>
                                                </>
                                            ) : (
                                                <>
                                                    {reward.kind !==
                                                        "credits" && (
                                                        <Field
                                                            label={
                                                                reward.kind ===
                                                                "profile"
                                                                    ? "Profile *"
                                                                    : "Reward *"
                                                            }
                                                            htmlFor={`reward-item-${index}`}
                                                        >
                                                            <NativeSelect
                                                                required
                                                                value={
                                                                    reward.id ??
                                                                    ""
                                                                }
                                                                onChange={(e) =>
                                                                    updateReward(
                                                                        index,
                                                                        {
                                                                            id: e
                                                                                .target
                                                                                .value,
                                                                        },
                                                                    )
                                                                }
                                                            >
                                                                <option value="">
                                                                    Select{" "}
                                                                    {reward.kind ===
                                                                    "profile"
                                                                        ? "a fighter or vehicle"
                                                                        : "a reward"}
                                                                </option>
                                                                {p.catalogue
                                                                    ?.filter(
                                                                        (c) =>
                                                                            c.kind ===
                                                                            reward.kind,
                                                                    )
                                                                    .map(
                                                                        (c) => (
                                                                            <option
                                                                                key={
                                                                                    c.id
                                                                                }
                                                                                value={
                                                                                    c.id
                                                                                }
                                                                            >
                                                                                {
                                                                                    c.name
                                                                                }{" "}
                                                                                ·{" "}
                                                                                {
                                                                                    c.detail
                                                                                }
                                                                            </option>
                                                                        ),
                                                                    )}
                                                            </NativeSelect>
                                                        </Field>
                                                    )}
                                                    <Field
                                                        label={
                                                            reward.kind ===
                                                            "credits"
                                                                ? "Credits *"
                                                                : "Quantity *"
                                                        }
                                                        htmlFor={`reward-amount-${index}`}
                                                    >
                                                        <Input
                                                            type="number"
                                                            min={1}
                                                            max={
                                                                reward.kind ===
                                                                    "credits" ||
                                                                reward.kind ===
                                                                    "resource"
                                                                    ? 1000000
                                                                    : 20
                                                            }
                                                            required
                                                            value={
                                                                reward.amount
                                                            }
                                                            onChange={(e) =>
                                                                updateReward(
                                                                    index,
                                                                    {
                                                                        amount: Number(
                                                                            e
                                                                                .target
                                                                                .value,
                                                                        ),
                                                                    },
                                                                )
                                                            }
                                                        />
                                                    </Field>
                                                    {reward.kind ===
                                                        "profile" && (
                                                        <p className="text-sm text-muted">
                                                            Added to the roster
                                                            with its default
                                                            equipment. The gang
                                                            pays no credits.
                                                        </p>
                                                    )}
                                                    {(reward.kind ===
                                                        "weapon" ||
                                                        reward.kind ===
                                                            "equipment") && (
                                                        <p className="text-sm text-muted">
                                                            Added to the gang
                                                            stash. The gang pays
                                                            no credits.
                                                        </p>
                                                    )}
                                                </>
                                            )}
                                        </div>
                                    </Card>
                                ))}
                                <Button
                                    onClick={() =>
                                        set({
                                            rewards: [
                                                ...data.rewards,
                                                targetPlayers
                                                    ? {
                                                          kind: "tag",
                                                          amount: 1,
                                                          icon: "crosshair",
                                                          name: "",
                                                          info: "",
                                                      }
                                                    : {
                                                          kind: "credits",
                                                          amount: 30,
                                                      },
                                            ],
                                        })
                                    }
                                >
                                    <Glyph name="plus" />
                                    Add{" "}
                                    {data.mode === "choice"
                                        ? "option"
                                        : "reward"}
                                </Button>
                            </FormSection>
                        )}
                        <FormSection title="Recipients">
                            {action === "intervention" && (
                                <RadioCards legend="Apply to" min="12rem">
                                    <RadioCard
                                        name="recipient_target"
                                        value="gangs"
                                        label="Gangs"
                                        description="Rewards or tags for campaign gangs."
                                        checked={!targetPlayers}
                                        onChange={() =>
                                            set({ target: "gangs" })
                                        }
                                    />
                                    <RadioCard
                                        name="recipient_target"
                                        value="players"
                                        label="Players"
                                        description="Informational tags for campaign players."
                                        checked={targetPlayers}
                                        onChange={() =>
                                            set({
                                                target: "players",
                                                rewards: data.rewards.every(
                                                    (r) => r.kind === "tag",
                                                )
                                                    ? data.rewards
                                                    : [
                                                          {
                                                              kind: "tag",
                                                              amount: 1,
                                                              icon: "crosshair",
                                                              name: "",
                                                              info: "",
                                                          },
                                                      ],
                                            })
                                        }
                                    />
                                </RadioCards>
                            )}
                            <RadioCards
                                legend={
                                    targetPlayers
                                        ? "Which players?"
                                        : "Which gangs?"
                                }
                                min="12rem"
                            >
                                <RadioCard
                                    name="recipient_mode"
                                    value="selected"
                                    label={
                                        targetPlayers
                                            ? "Selected players"
                                            : "Selected gangs"
                                    }
                                    checked={data.recipients_mode !== "all"}
                                    onChange={() =>
                                        set({ recipients_mode: "selected" })
                                    }
                                />
                                <RadioCard
                                    name="recipient_mode"
                                    value="all"
                                    label={
                                        targetPlayers
                                            ? "All players"
                                            : "All gangs"
                                    }
                                    checked={data.recipients_mode === "all"}
                                    onChange={() =>
                                        set({ recipients_mode: "all" })
                                    }
                                />
                            </RadioCards>
                            {data.recipients_mode !== "all" && (
                                <>
                                    <Field
                                        label={
                                            targetPlayers
                                                ? "Find a player"
                                                : "Find a gang"
                                        }
                                        htmlFor="recipient-search"
                                    >
                                        <Input
                                            type="search"
                                            value={search}
                                            onChange={(e) =>
                                                setSearch(e.target.value)
                                            }
                                            onKeyDown={(e) => {
                                                if (e.key === "Enter")
                                                    e.preventDefault();
                                            }}
                                        />
                                    </Field>
                                    <Card>
                                        <div className="space-y-1">
                                            {targets
                                                .filter((g) =>
                                                    (g.name + " " + g.owner)
                                                        .toLowerCase()
                                                        .includes(
                                                            search.toLowerCase(),
                                                        ),
                                                )
                                                .map((g) => (
                                                    <CheckboxCardItem
                                                        key={g.id}
                                                        name="recipients_display"
                                                        value={g.id}
                                                        label={g.name}
                                                        meta={g.owner}
                                                        checked={selectedTargets.includes(
                                                            g.id,
                                                        )}
                                                        onCheckedChange={(
                                                            checked,
                                                        ) =>
                                                            set(
                                                                targetPlayers
                                                                    ? {
                                                                          players:
                                                                              checked
                                                                                  ? [
                                                                                        ...data.players,
                                                                                        g.id,
                                                                                    ]
                                                                                  : data.players.filter(
                                                                                        (
                                                                                            id,
                                                                                        ) =>
                                                                                            id !==
                                                                                            g.id,
                                                                                    ),
                                                                      }
                                                                    : {
                                                                          gangs: checked
                                                                              ? [
                                                                                    ...data.gangs,
                                                                                    g.id,
                                                                                ]
                                                                              : data.gangs.filter(
                                                                                    (
                                                                                        id,
                                                                                    ) =>
                                                                                        id !==
                                                                                        g.id,
                                                                                ),
                                                                      },
                                                            )
                                                        }
                                                    />
                                                ))}
                                            {!targets.length && (
                                                <p className="text-sm text-muted">
                                                    No recipients in this
                                                    campaign yet.
                                                </p>
                                            )}
                                        </div>
                                    </Card>
                                </>
                            )}
                        </FormSection>
                        {action === "intervention" && (
                            <FormSection title="Notifications">
                                <p className="text-sm text-muted">
                                    Recipients are notified automatically.
                                </p>
                                <CheckboxCard
                                    name="inform_all_display"
                                    label={
                                        targetPlayers
                                            ? "Inform all players"
                                            : "Inform all gangs"
                                    }
                                    checked={data.inform_all}
                                    onCheckedChange={(checked) =>
                                        set({ inform_all: checked })
                                    }
                                    description="Tell everyone in the campaign who received what. For a choice, announce the offer and each confirmed selection."
                                />
                            </FormSection>
                        )}
                        <Card
                            header={
                                <h2 className="font-semibold">
                                    Review before sending
                                </h2>
                            }
                        >
                            <div className="space-y-2 text-sm">
                                <p>
                                    <strong>To: </strong>
                                    {targetNames.join(", ") ||
                                        "Select recipients above."}
                                </p>
                                {action === "intervention" ? (
                                    <>
                                        <p>
                                            {data.mode === "choice"
                                                ? `Each recipient chooses exactly ${data.choices} rewards.`
                                                : "Each recipient receives all rewards."}
                                        </p>
                                        <ul className="list-disc space-y-1 pl-5">
                                            {data.rewards.map((r, i) => (
                                                <li key={i}>{rewardText(r)}</li>
                                            ))}
                                        </ul>
                                    </>
                                ) : (
                                    <p>{data.title || "Add a title above."}</p>
                                )}
                            </div>
                        </Card>
                    </>
                )}
                {action === "alerts" && (
                    <FormSection title="Notify me when">
                        <p className="text-sm text-muted">
                            These alerts send site notifications to the campaign
                            arbitrator.
                        </p>
                        {p.alertEvents?.map((event) => (
                            <CheckboxCard
                                key={event.value}
                                name="events_display"
                                label={event.label}
                                checked={data.events.includes(event.value)}
                                onCheckedChange={(checked) =>
                                    set({
                                        events: checked
                                            ? [...data.events, event.value]
                                            : data.events.filter(
                                                  (v) => v !== event.value,
                                              ),
                                    })
                                }
                            />
                        ))}
                    </FormSection>
                )}
                {action === "choose" && p.receipt && (
                    <>
                        <Card
                            header={
                                <h2 className="font-semibold">
                                    {p.receipt.title}
                                </h2>
                            }
                        >
                            <div className="space-y-2 text-sm">
                                <p>{p.receipt.gang}</p>
                                <p className="whitespace-pre-wrap">
                                    {p.receipt.narrative}
                                </p>
                                <p>
                                    Choose exactly {p.receipt.choices} rewards.
                                    They are applied when you confirm.
                                </p>
                            </div>
                        </Card>
                        <FormSection title="Your rewards">
                            {p.receipt.rewards.map((r, index) => (
                                <CheckboxCard
                                    key={index}
                                    name="choices_display"
                                    label={r.label!}
                                    description={r.info}
                                    checked={data.selected.includes(index)}
                                    onCheckedChange={(checked) =>
                                        set({
                                            selected: checked
                                                ? [...data.selected, index]
                                                : data.selected.filter(
                                                      (i) => i !== index,
                                                  ),
                                        })
                                    }
                                />
                            ))}
                            <p className="text-sm text-muted">
                                {data.selected.length} of {p.receipt.choices}{" "}
                                chosen
                            </p>
                        </FormSection>
                    </>
                )}
                {action === "remove_tag" && p.tag && (
                    <Card>
                        <p className="text-sm">
                            Remove <strong>{p.tag.name}</strong> from{" "}
                            {p.tag.gang}?
                        </p>
                    </Card>
                )}
            </fieldset>
        </WorkflowPage>
    );
}
export function ArbitratorToolkit(p: ToolkitProps) {
    return p.screen === "home" ? (
        <Home {...p} />
    ) : p.screen === "detail" ? (
        <Detail {...p} />
    ) : (
        <ToolkitForm {...p} />
    );
}
