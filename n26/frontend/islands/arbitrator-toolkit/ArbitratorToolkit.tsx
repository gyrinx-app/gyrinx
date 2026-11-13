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
    Table,
    Alert,
    Link,
    Badge,
    Icon,
    TabLinks,
    Tooltip,
    useWorkflowForm,
    QuickSwitcher,
    RichText,
    RichTextEditor,
    type RichNode,
    type RichTextEditorConfig,
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
    immediate: boolean;
    report_enabled: boolean;
    report_days: number;
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
    immediate: true,
    report_enabled: false,
    report_days: 7,
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
    editHref?: string;
    name: string;
    icon: string;
    info: string;
    recipient: string;
    target: "gangs" | "players";
    assignmentKey: string;
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
    editor?: RichTextEditorConfig;
    narrativeNodes?: RichNode[];
    conflicted?: boolean;
    reviewHref?: string;
    recipientNames?: string[];
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
        bodyNodes?: RichNode[];
        editHref?: string;
        date: string;
    }[];
    alerts?: { value: string; label: string }[];
    enabledAlerts?: string[];
    tags?: Tag[];
    newTags?: string;
    alertTiming?: {
        immediate: boolean;
        report_enabled: boolean;
        report_days: number;
        next_report_at: string | null;
    };
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
        narrativeNodes?: RichNode[];
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
        ["tags", "Tags"],
        ["alerts", "Alerts"],
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
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {[
                    {
                        icon: "gift",
                        name: "Interventions",
                        text: "Give rewards and offer choices.",
                        href: p.newIntervention!,
                        button: "Make an intervention",
                    },
                    {
                        icon: "send",
                        name: "Communications",
                        text: "Send a message to players in this campaign.",
                        href: p.newCommunication!,
                        button: "Write a message",
                    },
                    {
                        icon: "tag",
                        name: "Tags",
                        text: "Assign tags to players or gangs.",
                        href: p.newTags!,
                        button: "Assign tags",
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
                                send rewards.
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
                                No communications yet. Write a message to
                                message your players.
                            </p>
                        )}
                        {p.communications?.map((c) => (
                            <div
                                key={c.id}
                                className="space-y-2 py-3 first:pt-0 last:pb-0"
                            >
                                <div className="flex items-center justify-between gap-3">
                                    <h3 className="font-semibold">{c.title}</h3>
                                    {c.editHref && (
                                        <ButtonLink
                                            size="sm"
                                            variant="ghost"
                                            href={c.editHref}
                                        >
                                            Edit
                                        </ButtonLink>
                                    )}
                                </div>
                                {c.bodyNodes ? (
                                    <RichText
                                        nodes={c.bodyNodes}
                                        className="text-sm"
                                    />
                                ) : (
                                    <p className="whitespace-pre-wrap text-sm">
                                        {c.body}
                                    </p>
                                )}
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
                        <p className="text-sm font-semibold">
                            Immediate alerts:{" "}
                            {p.alertTiming?.immediate === false ? "Off" : "On"}
                        </p>
                        <p className="text-sm font-semibold">
                            Wrap-up reports:{" "}
                            {p.alertTiming?.report_enabled
                                ? `Every ${p.alertTiming.report_days} ${p.alertTiming.report_days === 1 ? "day" : "days"}`
                                : "Off"}
                        </p>
                        {p.alertTiming?.next_report_at && (
                            <p className="text-sm text-muted">
                                Next report:{" "}
                                <time dateTime={p.alertTiming.next_report_at}>
                                    {new Date(
                                        p.alertTiming.next_report_at,
                                    ).toLocaleString()}
                                </time>
                            </p>
                        )}
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
                <div className="space-y-8">
                    <TagTable tags={p.tags ?? []} target="gangs" />
                    <TagTable tags={p.tags ?? []} target="players" />
                </div>
            )}
        </WorkflowLayout>
    );
}
function TagTable({ tags, target }: { tags: Tag[]; target: Tag["target"] }) {
    const groups = new Map<string, Tag[]>();
    for (const tag of tags.filter((tag) => tag.target === target)) {
        const recipients = groups.get(tag.assignmentKey) ?? [];
        recipients.push(tag);
        groups.set(tag.assignmentKey, recipients);
    }
    const title = target === "gangs" ? "Gang tags" : "Player tags";
    return (
        <Card header={<h2 className="font-semibold">{title}</h2>}>
            {groups.size ? (
                <Table className="max-sm:block [&_td]:align-top">
                    <caption className="sr-only">{title}</caption>
                    <thead className="max-sm:sr-only">
                        <tr>
                            <th scope="col">Tag</th>
                            <th scope="col">
                                {target === "gangs" ? "Gangs" : "Players"}
                            </th>
                            <th scope="col">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="max-sm:block">
                        {[...groups.values()].map((recipients) => {
                            const tag = recipients[0];
                            return (
                                <tr
                                    key={tag.assignmentKey}
                                    className="max-sm:grid max-sm:grid-cols-1"
                                >
                                    <td className="min-w-40 whitespace-normal max-sm:min-w-0">
                                        <span className="inline-flex items-center gap-2 font-semibold">
                                            {tag.name}
                                            <Glyph
                                                name={tag.icon}
                                                className="size-[1em]"
                                            />
                                        </span>
                                        {tag.info && (
                                            <p className="mt-1 whitespace-pre-wrap text-sm text-muted">
                                                {tag.info}
                                            </p>
                                        )}
                                    </td>
                                    <td>
                                        <span className="mb-2 block text-xs font-semibold text-muted sm:hidden">
                                            {target === "gangs"
                                                ? "Gangs"
                                                : "Players"}
                                        </span>
                                        <ul className="space-y-2">
                                            {recipients.map((recipient) => (
                                                <li
                                                    key={recipient.id}
                                                    className="flex items-center justify-between gap-3"
                                                >
                                                    <span>
                                                        {recipient.recipient}
                                                    </span>
                                                    <Link
                                                        href={
                                                            recipient.removeHref
                                                        }
                                                        tone="danger"
                                                        className="text-xs"
                                                        aria-label={`Remove ${tag.name} from ${recipient.recipient}`}
                                                    >
                                                        Remove
                                                    </Link>
                                                </li>
                                            ))}
                                        </ul>
                                    </td>
                                    <td>
                                        {tag.editHref && (
                                            <ButtonLink
                                                href={tag.editHref}
                                                size="sm"
                                                variant="ghost"
                                                aria-label={`Edit ${tag.name}`}
                                            >
                                                Edit
                                            </ButtonLink>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </Table>
            ) : (
                <p className="text-sm text-muted">
                    No {target === "gangs" ? "gang" : "player"} tags assigned
                    yet. Assign a tag to{" "}
                    {target === "gangs" ? "a gang" : "a player"}.
                </p>
            )}
        </Card>
    );
}
function Detail(p: ToolkitProps) {
    return (
        <WorkflowLayout
            footer={null}
            title={p.title!}
            lead={p.campaignName}
            breadcrumb={<Breadcrumb p={p} current={p.title} />}
        >
            {p.narrative &&
                (p.narrativeNodes ? (
                    <RichText nodes={p.narrativeNodes} className="text-sm" />
                ) : (
                    <p className="whitespace-pre-wrap text-sm">{p.narrative}</p>
                ))}
            <Card
                header={
                    <h2 className="font-semibold">
                        {p.mode === "choice"
                            ? `Choose exactly ${p.choices} ${p.choices === 1 ? "reward" : "rewards"}`
                            : p.rewards?.length === 1
                              ? "Reward"
                              : "Rewards"}
                    </h2>
                }
            >
                <ul className="list-disc space-y-3 pl-5">
                    {p.rewards?.map((r, i) => (
                        <li key={i} className="text-sm">
                            <div className="flex items-center gap-2">
                                <span>{r.label}</span>
                                {r.icon && (
                                    <Glyph
                                        name={r.icon}
                                        className="size-[1em]"
                                    />
                                )}
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
                                    Choose{" "}
                                    {p.choices === 1 ? "reward" : "rewards"}
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
                    All campaign players are notified of the offer.
                </p>
            )}
        </WorkflowLayout>
    );
}
function TagAssignmentFields({
    p,
    data,
    set,
}: {
    p: ToolkitProps;
    data: Payload;
    set: (part: Partial<Payload>) => void;
}) {
    const [search, setSearch] = useState("");
    const players = data.target === "players";
    const targets = players ? (p.players ?? []) : (p.gangs ?? []);
    const selected = players ? data.players : data.gangs;
    const update = (index: number, part: Partial<Reward>) =>
        set({
            rewards: data.rewards
                .slice(0, 1)
                .map((r, i) => (i === index ? { ...r, ...part } : r)),
        });
    return (
        <>
            <FormSection title="Tags">
                {data.rewards.slice(0, 1).map((tag, index) => (
                    <Card key={index}>
                        <div className="space-y-4">
                            <Field
                                label="Tag name *"
                                htmlFor={`tag-title-${index}`}
                            >
                                <Input
                                    maxLength={80}
                                    required
                                    value={tag.name ?? ""}
                                    onChange={(e) =>
                                        update(index, { name: e.target.value })
                                    }
                                />
                            </Field>
                            <fieldset className="space-y-2">
                                <legend className="text-sm font-medium">
                                    Icon
                                </legend>
                                <div className="flex flex-wrap gap-2">
                                    {p.icons?.map((icon) => (
                                        <Tooltip
                                            key={icon}
                                            label={icon}
                                            size="sm"
                                        >
                                            <Button
                                                aria-label={icon}
                                                aria-pressed={tag.icon === icon}
                                                variant={
                                                    tag.icon === icon
                                                        ? "primary"
                                                        : "default"
                                                }
                                                onClick={() =>
                                                    update(index, { icon })
                                                }
                                            >
                                                <Glyph name={icon} />
                                            </Button>
                                        </Tooltip>
                                    ))}
                                </div>
                            </fieldset>
                            <Field
                                label="Information"
                                htmlFor={`tag-information-${index}`}
                            >
                                <Textarea
                                    rows={3}
                                    maxLength={1000}
                                    value={tag.info ?? ""}
                                    onChange={(e) =>
                                        update(index, { info: e.target.value })
                                    }
                                />
                            </Field>
                        </div>
                    </Card>
                ))}
            </FormSection>
            <FormSection title="Recipients">
                {p.actionKind !== "edit_tag" && (
                    <RadioCards legend="Apply to" min="12rem">
                        <RadioCard
                            name="tag_target"
                            value="gangs"
                            label="Gangs"
                            checked={!players}
                            onChange={() => set({ target: "gangs" })}
                        />
                        <RadioCard
                            name="tag_target"
                            value="players"
                            label="Players"
                            checked={players}
                            onChange={() => set({ target: "players" })}
                        />
                    </RadioCards>
                )}
                <RadioCards
                    legend={players ? "Which players?" : "Which gangs?"}
                    min="12rem"
                >
                    <RadioCard
                        name="tag_recipient_mode"
                        value="selected"
                        label={players ? "Selected players" : "Selected gangs"}
                        checked={data.recipients_mode === "selected"}
                        onChange={() => set({ recipients_mode: "selected" })}
                    />
                    <RadioCard
                        name="tag_recipient_mode"
                        value="all"
                        label={players ? "All players" : "All gangs"}
                        checked={data.recipients_mode === "all"}
                        onChange={() => set({ recipients_mode: "all" })}
                    />
                </RadioCards>
                {data.recipients_mode !== "all" && (
                    <>
                        <Field
                            label={players ? "Find a player" : "Find a gang"}
                            htmlFor="tag-recipient-search"
                        >
                            <Input
                                type="search"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter") e.preventDefault();
                                }}
                            />
                        </Field>
                        <Card>
                            {targets
                                .filter((t) =>
                                    (t.name + " " + t.owner)
                                        .toLowerCase()
                                        .includes(search.toLowerCase()),
                                )
                                .map((t) => (
                                    <CheckboxCardItem
                                        key={t.id}
                                        name="tag_recipients_display"
                                        value={t.id}
                                        label={t.name}
                                        meta={t.owner}
                                        checked={selected.includes(t.id)}
                                        onCheckedChange={(checked) =>
                                            set(
                                                players
                                                    ? {
                                                          players: checked
                                                              ? [
                                                                    ...data.players,
                                                                    t.id,
                                                                ]
                                                              : data.players.filter(
                                                                    (id) =>
                                                                        id !==
                                                                        t.id,
                                                                ),
                                                      }
                                                    : {
                                                          gangs: checked
                                                              ? [
                                                                    ...data.gangs,
                                                                    t.id,
                                                                ]
                                                              : data.gangs.filter(
                                                                    (id) =>
                                                                        id !==
                                                                        t.id,
                                                                ),
                                                      },
                                            )
                                        }
                                    />
                                ))}
                        </Card>
                    </>
                )}
                <p className="text-sm text-muted">
                    Recipients are notified automatically.
                </p>
            </FormSection>
        </>
    );
}

function ToolkitForm(p: ToolkitProps) {
    const action = p.actionKind!;
    const title = (
        {
            intervention: "Make an intervention",
            communication: "Write a message",
            alerts: "Set alerts",
            choose:
                p.receipt?.choices === 1 ? "Choose reward" : "Choose rewards",
            tags: "Assign tags",
            remove_tag: "Remove tag",
            edit_tag: "Edit tag",
            edit_communication: "Edit message",
        } as Record<string, string>
    )[action];
    const form = useWorkflowForm({
        values: p.values!,
        errors: p.errors!,
        initialConflict: p.conflicted,
        commandHref: p.commandHref!,
        csrfToken: p.csrfToken!,
        recoveryKey: p.recoveryKey!,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
            if (
                status === 409 &&
                data.code === "revision_conflict" &&
                data.errors
            )
                return {
                    kind: "conflict",
                    errors: data.errors as Record<string, string[]>,
                };
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
    const [uploading, setUploading] = useState(false);
    const updateReward = (index: number, part: Partial<Reward>) =>
        set({
            rewards: data.rewards.map((r, i) =>
                i === index ? { ...r, ...part } : r,
            ),
        });
    const targetPlayers = data.target === "players";
    const targets = targetPlayers ? (p.players ?? []) : (p.gangs ?? []);
    const selectedTargets = targetPlayers ? data.players : data.gangs;
    const targetNames =
        p.recipientNames ??
        (data.recipients_mode === "all"
            ? targets
            : targets.filter((g) => selectedTargets.includes(g.id))
        ).map((g) => g.name);
    const rewardKind = (kind: string) =>
        (
            ({
                profile: "Profile",
                resource: "Resource type",
                weapon: "Weapon",
                equipment: "Equipment",
                credits: "Credits",
            }) as Record<string, string>
        )[kind] || "Reward";
    const missingReward = (r: Reward) =>
        !r.kind ||
        !(Number.isInteger(r.amount) && r.amount > 0) ||
        (r.kind !== "credits" &&
            r.kind !== "tag" &&
            !p.catalogue?.some((c) => c.kind === r.kind && c.id === r.id));
    const invalidIntervention =
        action === "intervention" &&
        (!data.rewards.length ||
            data.rewards.some(missingReward) ||
            !["bundle", "choice"].includes(data.mode) ||
            !["all", "selected"].includes(data.recipients_mode) ||
            !targetNames.length);
    const rewardText = (r: Reward) => {
        if (!r.kind) return "Select a reward type.";
        if (!(Number.isInteger(r.amount) && r.amount > 0))
            return "Enter an amount greater than zero, using whole numbers.";
        if (missingReward(r))
            return r.kind === "resource"
                ? "Select a resource type."
                : r.kind === "profile"
                  ? "Select a fighter or vehicle."
                  : r.kind === "equipment"
                    ? "Select equipment."
                    : "Select a weapon.";
        return r.kind === "credits"
            ? `${r.amount}¢`
            : r.kind === "tag"
              ? r.name || "Unnamed tag"
              : `${r.amount} × ${p.catalogue?.find((c) => c.kind === r.kind && c.id === r.id)?.name}`;
    };
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
                        disabled={
                            form.pending ||
                            uploading ||
                            (!form.uncertain &&
                                (invalidIntervention || form.conflicted))
                        }
                    >
                        {form.uncertain
                            ? "Retry save"
                            : (
                                  {
                                      intervention: "Send intervention",
                                      communication: "Send message",
                                      alerts: "Save alerts",
                                      choose:
                                          p.receipt?.choices === 1
                                              ? "Confirm choice"
                                              : "Confirm choices",
                                      tags: "Assign tags",
                                      remove_tag: "Remove tag",
                                      edit_tag: "Save tag",
                                      edit_communication: "Save message",
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
            {form.conflicted && p.reviewHref && (
                <Button onClick={() => form.review(p.reviewHref!)}>
                    Review current version
                </Button>
            )}
            <fieldset disabled={form.frozen} className="space-y-8">
                {(action === "intervention" ||
                    action === "communication" ||
                    action === "edit_communication") && (
                    <>
                        <FormSection>
                            <Field label="Title *" htmlFor="toolkit-title">
                                <Input
                                    id="toolkit-title"
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
                            >
                                <RichTextEditor
                                    id="toolkit-body"
                                    label={
                                        action === "intervention"
                                            ? "Accompanying text"
                                            : "Message"
                                    }
                                    config={p.editor}
                                    csrfToken={p.csrfToken!}
                                    value={
                                        action === "intervention"
                                            ? data.narrative
                                            : data.body
                                    }
                                    disabled={form.frozen}
                                    onUploading={setUploading}
                                    onChange={(value) =>
                                        set(
                                            action === "intervention"
                                                ? { narrative: value }
                                                : { body: value },
                                        )
                                    }
                                />
                            </Field>
                        </FormSection>
                        {action === "intervention" && (
                            <FormSection title="Rewards *">
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
                                        label="Number of rewards to choose"
                                        htmlFor="toolkit-limit"
                                    >
                                        <Input
                                            id="toolkit-limit"
                                            type="number"
                                            step={1}
                                            min={1}
                                            max={Math.max(
                                                data.rewards.length,
                                                1,
                                            )}
                                            required
                                            value={data.choices}
                                            onChange={(e) => {
                                                const choices = Number(
                                                    e.target.value,
                                                );
                                                if (
                                                    Number.isInteger(choices) &&
                                                    choices >= 1 &&
                                                    choices <=
                                                        Math.max(
                                                            data.rewards.length,
                                                            1,
                                                        )
                                                )
                                                    set({ choices });
                                            }}
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
                                                    required
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
                                                    <option value="">
                                                        Select a type
                                                    </option>
                                                    {[
                                                        ["credits", "Credits"],
                                                        ["weapon", "Weapon"],
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
                                                    ].map(([value, label]) => (
                                                        <option
                                                            key={value}
                                                            value={value}
                                                        >
                                                            {label}
                                                        </option>
                                                    ))}
                                                </NativeSelect>
                                            </Field>
                                            {reward.kind ? (
                                                <>
                                                    {reward.kind !==
                                                        "credits" && (
                                                        <Field
                                                            label={rewardKind(
                                                                reward.kind,
                                                            )}
                                                            htmlFor={`reward-item-${index}`}
                                                        >
                                                            <QuickSwitcher
                                                                id={`reward-item-${index}`}
                                                                heading={
                                                                    reward.kind ===
                                                                    "profile"
                                                                        ? "Select a fighter or vehicle"
                                                                        : `Select ${reward.kind === "resource" ? "a resource type" : reward.kind === "equipment" ? "equipment" : "a weapon"}`
                                                                }
                                                                menuLabel={`Select ${rewardKind(reward.kind).toLowerCase()} ${index + 1}`}
                                                                placeholder={
                                                                    reward.kind ===
                                                                    "profile"
                                                                        ? "Search profiles"
                                                                        : `Search ${reward.kind === "resource" ? "resource types" : reward.kind === "equipment" ? "equipment" : "weapons"}`
                                                                }
                                                                empty={`No ${reward.kind === "resource" ? "resource types" : reward.kind === "profile" ? "profiles" : reward.kind === "equipment" ? "equipment" : "weapons"} match`}
                                                                triggerWords={
                                                                    p.catalogue?.find(
                                                                        (c) =>
                                                                            c.kind ===
                                                                                reward.kind &&
                                                                            c.id ===
                                                                                reward.id,
                                                                    )?.name ??
                                                                    (reward.kind ===
                                                                    "profile"
                                                                        ? "Select a fighter or vehicle"
                                                                        : `Select ${reward.kind === "resource" ? "a resource type" : reward.kind === "equipment" ? "equipment" : "a weapon"}`)
                                                                }
                                                                current={
                                                                    reward.id
                                                                }
                                                                items={
                                                                    p.catalogue
                                                                        ?.filter(
                                                                            (
                                                                                c,
                                                                            ) =>
                                                                                c.kind ===
                                                                                reward.kind,
                                                                        )
                                                                        .map(
                                                                            (
                                                                                c,
                                                                            ) => ({
                                                                                label: `${c.name} · ${c.detail}`,
                                                                                value: c.id,
                                                                            }),
                                                                        ) ?? []
                                                                }
                                                                onChoose={(
                                                                    id,
                                                                ) =>
                                                                    updateReward(
                                                                        index,
                                                                        { id },
                                                                    )
                                                                }
                                                            />
                                                        </Field>
                                                    )}
                                                    <Field
                                                        label={
                                                            reward.kind ===
                                                            "credits"
                                                                ? "Credits"
                                                                : "Quantity"
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
                                            ) : null}
                                        </div>
                                    </Card>
                                ))}
                                <Button
                                    variant="primary"
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
                                    <span className="inline-flex items-center gap-2 whitespace-nowrap">
                                        {" "}
                                        <Glyph name="plus" />
                                        Add{" "}
                                        {data.mode === "choice"
                                            ? "option"
                                            : "reward"}
                                    </span>
                                </Button>
                            </FormSection>
                        )}
                        {action === "edit_communication" ? (
                            <Card
                                header={
                                    <h2 className="font-semibold">
                                        Recipients
                                    </h2>
                                }
                            >
                                <p className="text-sm">
                                    {targetNames.join(", ")}
                                </p>
                            </Card>
                        ) : (
                            <FormSection title="Recipients *">
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
                                        checked={
                                            data.recipients_mode === "selected"
                                        }
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
                        )}
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
                                    description="Inform everyone in the campaign about this intervention."
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
                                    <span
                                        className={
                                            !targetNames.length
                                                ? "text-red-600 dark:text-red-400"
                                                : undefined
                                        }
                                    >
                                        {targetNames.join(", ") ||
                                            "Select at least one recipient."}
                                    </span>
                                </p>
                                {action === "intervention" ? (
                                    <>
                                        <p
                                            className={
                                                !data.mode
                                                    ? "text-red-600 dark:text-red-400"
                                                    : undefined
                                            }
                                        >
                                            {data.mode === "choice"
                                                ? `Each recipient chooses exactly ${data.choices} ${data.choices === 1 ? "reward" : "rewards"}.`
                                                : data.mode === "bundle"
                                                  ? "Each recipient receives all rewards."
                                                  : "Choose how rewards are applied."}
                                        </p>
                                        <ul className="list-disc space-y-1 pl-5">
                                            {data.rewards.map((r, i) => (
                                                <li
                                                    key={i}
                                                    className={
                                                        missingReward(r)
                                                            ? "text-red-600 dark:text-red-400"
                                                            : undefined
                                                    }
                                                >
                                                    {rewardText(r)}
                                                </li>
                                            ))}
                                        </ul>
                                    </>
                                ) : (
                                    <p>{data.title || "Add a title above."}</p>
                                )}
                            </div>
                        </Card>
                        {action === "intervention" && (
                            <Alert
                                tone="warning"
                                dismissible={false}
                                role="note"
                            >
                                Interventions cannot be undone once sent. Check
                                the rewards and recipients before sending.
                            </Alert>
                        )}
                    </>
                )}
                {(action === "tags" || action === "edit_tag") && (
                    <TagAssignmentFields p={p} data={data} set={set} />
                )}
                {action === "alerts" && (
                    <>
                        <FormSection title="Notify me when">
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
                        <FormSection title="Delivery times">
                            <CheckboxCard
                                name="immediate_display"
                                label="Send alerts immediately"
                                description="Receive a site notification each time a selected action takes place."
                                checked={data.immediate}
                                onCheckedChange={(immediate) =>
                                    set({ immediate })
                                }
                            />
                            <CheckboxCard
                                name="report_display"
                                label="Send a wrap-up report"
                                description="Receive a report even when none of the selected actions took place."
                                checked={data.report_enabled}
                                onCheckedChange={(report_enabled) =>
                                    set({ report_enabled })
                                }
                            >
                                <Field
                                    label="Send a report every *"
                                    htmlFor="report-days"
                                    description="Each report covers the period since the previous report."
                                >
                                    <Input
                                        type="number"
                                        min={1}
                                        max={365}
                                        disabled={!data.report_enabled}
                                        required={data.report_enabled}
                                        value={data.report_days}
                                        onChange={(e) =>
                                            set({
                                                report_days: Number(
                                                    e.target.value,
                                                ),
                                            })
                                        }
                                        rightAddon={
                                            <span className="text-sm text-muted">
                                                {data.report_days === 1
                                                    ? "day"
                                                    : "days"}
                                            </span>
                                        }
                                    />
                                </Field>
                            </CheckboxCard>
                        </FormSection>
                    </>
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
                                {p.receipt.narrativeNodes ? (
                                    <RichText
                                        nodes={p.receipt.narrativeNodes}
                                    />
                                ) : (
                                    <p className="whitespace-pre-wrap">
                                        {p.receipt.narrative}
                                    </p>
                                )}
                                <p>
                                    Choose exactly {p.receipt.choices}{" "}
                                    {p.receipt.choices === 1
                                        ? "reward"
                                        : "rewards"}
                                    . Applied when you confirm.
                                </p>
                            </div>
                        </Card>
                        <FormSection
                            title={
                                p.receipt.choices === 1
                                    ? "Your reward"
                                    : "Your rewards"
                            }
                        >
                            {p.receipt.choices === 1 ? (
                                <RadioCards
                                    legend="Choose one reward"
                                    min="100%"
                                >
                                    {p.receipt.rewards.map((r, index) => (
                                        <RadioCard
                                            key={index}
                                            name="choices_display"
                                            value={String(index)}
                                            label={r.label!}
                                            description={r.info}
                                            checked={data.selected.includes(
                                                index,
                                            )}
                                            onChange={() =>
                                                set({ selected: [index] })
                                            }
                                        />
                                    ))}
                                </RadioCards>
                            ) : (
                                p.receipt.rewards.map((r, index) => (
                                    <CheckboxCard
                                        key={index}
                                        name="choices_display"
                                        label={r.label!}
                                        description={r.info}
                                        checked={data.selected.includes(index)}
                                        disabled={
                                            !data.selected.includes(index) &&
                                            data.selected.length >=
                                                p.receipt!.choices
                                        }
                                        onCheckedChange={(checked) => {
                                            if (!checked)
                                                set({
                                                    selected:
                                                        data.selected.filter(
                                                            (i) => i !== index,
                                                        ),
                                                });
                                            else if (
                                                data.selected.length <
                                                p.receipt!.choices
                                            )
                                                set({
                                                    selected: [
                                                        ...data.selected,
                                                        index,
                                                    ],
                                                });
                                        }}
                                    />
                                ))
                            )}
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
