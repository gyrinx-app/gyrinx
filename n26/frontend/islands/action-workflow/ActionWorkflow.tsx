import {
    type FormEvent,
    type ComponentProps,
    useId,
    useRef,
    useState,
} from "react";
import { flushSync } from "react-dom";
import { fieldErrors, type FormErrors } from "../../http/command";
import {
    Alert,
    ActionFacts,
    ActionText,
    ActionDetail,
    ActionFooterLink,
    ActionAttempts,
    ActionRollSummary,
    Breadcrumbs,
    BusyControlScope,
    Button,
    ButtonLink,
    Card,
    Field,
    FieldErrors,
    FlowProgress,
    type FlowStep,
    FormActions,
    FormSection,
    Input,
    PaymentFigures,
    RadioCard,
    RadioCards,
    Tally,
    WorkflowPage,
    useWorkflowForm,
} from "../../ui";
import type { AdvancementRollProps } from "./rollTypes";

type TallyFact = ComponentProps<typeof Tally>["facts"][number];
type Values = Record<string, string>;
type Roll = AdvancementRollProps;
type Facts = {
    stage: string;
    correction?: boolean;
    earned_threshold?: string;
    back_href?: string;
    back_label?: string;
    done_href?: string;
    cancel_href?: string;
    undo_href?: string;
    change_href?: string;
    selection_summary?: string;
    tracking_unavailable?: boolean;
    submit_label?: string;
    submit_variant?: ComponentProps<typeof Button>["variant"];
    roll_value?: number;
    advancement_title?: string;
    roll_explanation?: string;
    threshold_roll?: boolean;
    promotion_description?: string;
    decline_promotion?: boolean;
    skill_random?: boolean;
    skill_resolved?: boolean;
    skill_selected?: string;
    skill_title?: string;
    skill_description?: string;
    skill_confirmation?: string;
    skill_selected_group?: string;
    skill_empty?: string;
    show_outcome?: boolean;
    outcome_description?: string;
    retained_payment?: boolean;
    retained_roll?: boolean;
    hold_reason?: string;
    keeps_stashed_weapons?: boolean;
    recovery_only?: boolean;
    outcome: string;
    allowanceThreshold: boolean;
    steps: FlowStep[];
    prices: {
        label: string;
        available: string;
        price: string;
        remaining: string;
    }[];
    payments: TallyFact[][];
    receipt: { label: string; value: string }[];
    outcomes: { key: string; name: string; description: string }[];
    items: {
        key: string;
        name: string;
        current: string;
        tier: string;
        effect: string;
        before: number;
        after: number;
    }[];
    advancements: {
        key: string;
        name: string;
        minimum: number | null;
        rating: number;
        forcedRandom: boolean;
    }[];
    roll: Roll | null;
    skillRoll: Roll | null;
    skillGroups: {
        key: string;
        name: string;
        skills: { key: string; name: string }[];
    }[];
    attempts: {
        roll: number;
        result_name: string | null;
        is_available: boolean;
        unavailable_reason: string | null;
    }[];
    reviewChoice: {
        label: string;
        title: string;
        description: string;
        meta: string;
    } | null;
    changes: {
        kind: string;
        name: string;
        before: number;
        after: number;
        removed_count: number;
        slot_type: string;
    }[];
};
export type ActionWorkflowProps = {
    title: string;
    modelName: string;
    gangName: string;
    gangHref: string;
    modelHref: string;
    facts: Facts;
    values: Values;
    errors: FormErrors;
    initialConflict: boolean;
    fields: string[];
    hiddenFields: string[];
    action: string;
    commandHref: string;
    displayHref: string;
    csrfToken: string;
    recoveryKey: string;
    draftKey: string;
    draftScope: string;
    recoveryHref: string;
    signInHref: string;
    onNavigate?: (url: string) => void;
};
const metadata = [
    "draft_key",
    "gang_id",
    "command_key",
    "revision",
    "target_kind",
    "target_id",
    "target_step",
    "target_allowance",
    "target_pick",
    "target_allowance_present",
    "target_pick_present",
    "submitted_summary",
];

type SavedFacts = {
    action: string;
    record: string;
    revision: number | null;
    state: string;
    outcome: string;
    selection: string;
    rolls: { roll: number; dice: string }[];
    attempts?: { result_name?: string | null }[];
};
function savedFacts(value: unknown): value is SavedFacts {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const facts = value as Record<string, unknown>;
    return (
        ["action", "record", "state", "outcome", "selection"].every(
            (name) => typeof facts[name] === "string",
        ) &&
        (facts.revision === null || typeof facts.revision === "number") &&
        (facts.attempts === undefined ||
            (Array.isArray(facts.attempts) &&
                facts.attempts.every(
                    (attempt) =>
                        attempt &&
                        typeof attempt === "object" &&
                        (attempt.result_name === undefined ||
                            attempt.result_name === null ||
                            typeof attempt.result_name === "string"),
                ))) &&
        Array.isArray(facts.rolls) &&
        facts.rolls.every(
            (roll) =>
                roll &&
                typeof roll === "object" &&
                typeof roll.roll === "number" &&
                typeof roll.dice === "string",
        )
    );
}

function draftValues(props: ActionWorkflowProps): {
    values: Values;
    conflict: boolean;
} {
    try {
        const retained = new URLSearchParams(
            sessionStorage.getItem(props.recoveryKey) || "",
        );
        if (retained.get("__workflow_rejected") === "1") {
            const key = retained.get("draft_key");
            // Known rejected drafts follow their exact stage. Unknown commands
            // stay global so opening another stage cannot bypass the retry.
            if (
                key &&
                (key !== props.draftKey ||
                    retained.get("revision") !== props.values.revision)
            ) {
                retained.delete("__workflow_rejected");
                sessionStorage.setItem(
                    key,
                    JSON.stringify({
                        revision: retained.get("revision"),
                        values: Object.fromEntries(retained),
                        summary: retained.get("submitted_summary"),
                    }),
                );
                sessionStorage.removeItem(props.recoveryKey);
            } else if (key === props.draftKey) {
                // A known rejection has no outstanding command. Reconfirm the
                // current payment facts with the newly issued review and key.
                for (const name of ["review", "command_key"])
                    if (name in props.values)
                        retained.set(name, props.values[name]);
                sessionStorage.setItem(props.recoveryKey, retained.toString());
            }
        }
        const draft = JSON.parse(
            sessionStorage.getItem(props.draftKey) || "null",
        );
        if (draft && typeof draft.values === "object") {
            const values = {
                ...props.values,
                ...Object.fromEntries(
                    Object.entries(draft.values as Values).filter(
                        ([name, value]) =>
                            props.fields.includes(name) &&
                            typeof value === "string",
                    ),
                ),
            };
            const conflict = draft.revision !== props.values.revision;
            if (!conflict) {
                values.command_key = props.values.command_key;
                if ("review" in props.values)
                    values.review = props.values.review;
            }
            if (conflict) {
                values.revision = String(draft.revision ?? "");
                values.submitted_summary =
                    typeof draft.summary === "string"
                        ? draft.summary
                        : "An earlier draft belongs to an older version of this flow.";
            }
            return { values, conflict };
        }
    } catch {
        /* A page can still be used when passive draft storage is unavailable. */
    }
    return { values: props.values, conflict: false };
}

function RollControls({
    props,
    values,
    errors,
    frozen,
    change,
}: {
    props: Roll;
    values: Values;
    errors: FormErrors;
    frozen: boolean;
    change: (name: string, value: string) => void;
}) {
    const id = useId();
    const carried = props.choices?.options.find(
        (option) => option.value === values.skill_set_id,
    )?.carried;
    return (
        <div className="space-y-5">
            {props.choices && (
                <RadioCards
                    legend={props.choices.legend}
                    min="min(100%, 18rem)"
                    errors={errors.skill_set_id || []}
                >
                    {props.choices.options.map((option) => (
                        <RadioCard
                            key={option.value}
                            name="skill_set_id"
                            value={option.value}
                            label={option.label}
                            checked={values.skill_set_id === option.value}
                            disabled={frozen}
                            onChange={() =>
                                change("skill_set_id", option.value)
                            }
                        />
                    ))}
                </RadioCards>
            )}
            {props.previousRoll !== null && (
                <ActionText tone="note">
                    Recorded roll: {props.previousRoll}. Earlier rolls stay in
                    the history if you change it.
                </ActionText>
            )}
            {carried ? (
                <ActionText tone="note">{carried}</ActionText>
            ) : (
                <>
                    <RadioCards
                        legend={`Roll ${props.dice}`}
                        min="min(100%, 18rem)"
                        errors={errors.roll_mode || []}
                    >
                        <RadioCard
                            name="roll_mode"
                            value="roll"
                            label="Roll in Gyrinx"
                            checked={values.roll_mode === "roll"}
                            disabled={frozen}
                            onChange={() => change("roll_mode", "roll")}
                        />
                        <RadioCard
                            name="roll_mode"
                            value="record"
                            label="Record my roll"
                            checked={values.roll_mode === "record"}
                            disabled={frozen}
                            onChange={() => change("roll_mode", "record")}
                        />
                    </RadioCards>
                    <Field
                        label={props.totalLabel}
                        htmlFor={id}
                        description={props.totalHelp}
                        errors={errors.rolled || []}
                    >
                        <Input
                            id={id}
                            name="rolled"
                            type="number"
                            min={props.minimum}
                            max={props.maximum}
                            inputMode="numeric"
                            disabled={frozen || values.roll_mode !== "record"}
                            required={values.roll_mode === "record"}
                            value={values.rolled || ""}
                            onChange={(event) =>
                                change("rolled", event.target.value)
                            }
                        />
                    </Field>
                </>
            )}
        </div>
    );
}

function readable(
    props: ActionWorkflowProps,
    values: Values,
    decline: boolean,
) {
    const f = props.facts;
    const parts = [props.title, props.modelName];
    if (decline) parts.push("Keep current rank and roll 2D6");
    const outcome = f.outcomes.find((row) => row.key === values.outcome);
    const item = f.items.find((row) => row.key === values.selection);
    const advancement = f.advancements.find(
        (row) => row.key === values.pickable_id,
    );
    const skill = f.skillGroups
        .flatMap((group) => group.skills)
        .find((row) => row.key === values.skill_id);
    const roll = f.roll || f.skillRoll;
    const category = roll?.choices?.options.find(
        (row) => row.value === values.skill_set_id,
    );
    if (outcome) parts.push(outcome.name);
    if (item) parts.push(`${item.name}: ${item.tier}`);
    if (advancement) parts.push(advancement.name);
    if (skill) parts.push(skill.name);
    if (category) parts.push(category.label);
    if (roll && !decline)
        parts.push(
            category?.carried ||
                (values.roll_mode === "record"
                    ? `Record ${values.rolled} on ${roll.dice}`
                    : `Roll ${roll.dice} in Gyrinx`),
        );
    if (f.reviewChoice)
        parts.push(f.reviewChoice.title, f.reviewChoice.description);
    if (f.selection_summary) parts.push(f.selection_summary);
    parts.push(decline ? "" : f.submit_label || "");
    return parts.filter(Boolean).join("\n");
}

export function ActionWorkflow(props: ActionWorkflowProps) {
    const f = props.facts;
    const formRef = useRef<HTMLFormElement>(null);
    const submittedDraft = useRef(props.draftKey);
    const [initial] = useState(() => draftValues(props));
    const [reviewHref, setReviewHref] = useState(props.action);
    const [busyControl, setBusyControl] = useState<string | null>(null);
    const [acknowledged, setAcknowledged] = useState<{
        nextUrl: string;
        facts: SavedFacts;
    } | null>(null);
    const navigate =
        props.onNavigate || ((href: string) => window.location.assign(href));
    const workflow = useWorkflowForm({
        values: initial.values,
        errors: props.errors,
        initialConflict: props.initialConflict || initial.conflict,
        commandHref: props.commandHref,
        csrfToken: props.csrfToken,
        recoveryKey: props.recoveryKey,
        optionalRecoveryFields: Object.keys(initial.values).filter(
            (name) => !metadata.includes(name),
        ),
        onNavigate: navigate,
        onComplete: () => undefined,
        interpret(status, data) {
            if (
                status === 200 &&
                data.saved === true &&
                typeof data.nextUrl === "string" &&
                savedFacts(data.facts)
            ) {
                try {
                    if (submittedDraft.current.startsWith(props.draftScope))
                        sessionStorage.removeItem(submittedDraft.current);
                } catch {
                    /* Confirmed command recovery is cleared by the controller. */
                }
                if (data.replayed === true) {
                    setAcknowledged({
                        nextUrl:
                            typeof data.reviewUrl === "string" && data.reviewUrl
                                ? data.reviewUrl
                                : data.nextUrl,
                        facts: data.facts,
                    });
                    return { kind: "completed" };
                }
                return { kind: "saved", nextUrl: data.nextUrl };
            }
            if (status === 409 && fieldErrors(data.errors)) {
                if (
                    data.code === "revision_conflict" ||
                    data.code === "unavailable"
                ) {
                    if (typeof data.reviewUrl === "string" && data.reviewUrl)
                        setReviewHref(data.reviewUrl);
                    return { kind: "conflict", errors: data.errors };
                }
                return { kind: "invalid", errors: data.errors };
            }
            if (status === 422 && fieldErrors(data.errors))
                return { kind: "invalid", errors: data.errors };
            return null;
        },
    });
    const { values, errors, frozen } = workflow;
    submittedDraft.current = values.draft_key || props.draftKey;
    function change(name: string, value: string) {
        const next = { ...values, [name]: value };
        workflow.setValues(next);
        try {
            sessionStorage.setItem(
                props.draftKey,
                JSON.stringify({
                    revision: props.values.revision,
                    values: Object.fromEntries(
                        props.fields.map((key) => [key, next[key]]),
                    ),
                    summary: readable(props, next, false),
                }),
            );
        } catch {
            /* Command recovery checks storage before sending. */
        }
    }
    function save(event: FormEvent<HTMLFormElement>) {
        const submitter = (event.nativeEvent as SubmitEvent).submitter;
        const decline = submitter?.getAttribute("data-intent") === "decline";
        setBusyControl(submitter?.getAttribute("data-busy-id") || null);
        if (!workflow.uncertain && !workflow.conflicted) {
            try {
                window.history.replaceState(
                    window.history.state,
                    "",
                    props.recoveryHref,
                );
            } catch {
                event.preventDefault();
                setStorageNotice(
                    "Your browser could not keep this page ready for recovery. Reload the page and try again.",
                );
                return;
            }
            // The readable snapshot and exact submitted body must describe the same click.
            flushSync(() =>
                workflow.setValues((current) => ({
                    ...current,
                    submitted_summary: readable(props, current, decline),
                    decline_promotion: decline ? "1" : "",
                })),
            );
        }
        void workflow.save(event);
    }
    const [storageNotice, setStorageNotice] = useState("");
    function review() {
        try {
            if (submittedDraft.current.startsWith(props.draftScope))
                sessionStorage.removeItem(submittedDraft.current);
        } catch {
            setStorageNotice(
                "Your browser could not clear this draft. Check this site’s storage settings, then try again.",
            );
            return;
        }
        workflow.review(reviewHref);
    }
    const leave = (href: string) => navigate(href);
    const link = (
        href: string | undefined,
        label: string,
        variant: ComponentProps<typeof ButtonLink>["variant"] = "ghost",
    ) =>
        href && (
            <ActionFooterLink
                kind={
                    href === f.cancel_href || href === f.undo_href
                        ? "danger"
                        : href === f.back_href
                          ? "back"
                          : undefined
                }
                href={href}
                variant={variant}
                aria-disabled={frozen}
                onClick={(event) => {
                    event.preventDefault();
                    if (!frozen) leave(href);
                }}
            >
                {label}
            </ActionFooterLink>
        );
    const summary =
        values.submitted_summary || "The earlier action is retained for retry.";
    const recovery = (
        <>
            {storageNotice && (
                <Alert tone="error" dismissible={false}>
                    {storageNotice}
                </Alert>
            )}
            {workflow.hasErrors && (
                <div ref={workflow.summary} tabIndex={-1} role="alert">
                    <Alert tone="error" dismissible={false}>
                        <h2>The action could not be confirmed</h2>
                        {workflow.notice && <p>{workflow.notice}</p>}
                        <FieldErrors errors={Object.values(errors).flat()} />
                    </Alert>
                </div>
            )}
            {workflow.hasErrors &&
                !workflow.uncertain &&
                !workflow.conflicted && (
                    <FormActions>
                        <Button
                            disabled={workflow.pending}
                            onClick={() =>
                                formRef.current &&
                                workflow.recoverAt(
                                    props.recoveryHref,
                                    formRef.current,
                                )
                            }
                        >
                            Reload
                        </Button>
                        <Button
                            disabled={workflow.pending}
                            onClick={() =>
                                formRef.current &&
                                workflow.recoverAt(
                                    props.signInHref,
                                    formRef.current,
                                )
                            }
                        >
                            Sign in again
                        </Button>
                    </FormActions>
                )}
            {(workflow.uncertain || workflow.conflicted) && (
                <FormSection title="Earlier save">
                    <p className="whitespace-pre-line">{summary}</p>
                    <p>
                        These are the selections sent earlier. The current flow
                        may have changed.
                    </p>
                </FormSection>
            )}
            {acknowledged && (
                <Alert tone="success" dismissible={false}>
                    <h2>Earlier action confirmed</h2>
                    <p className="whitespace-pre-line">{summary}</p>
                    <p>
                        Saved revision{" "}
                        {String(acknowledged.facts.revision ?? "")}. This
                        confirms the original action.
                    </p>
                    {acknowledged.facts.selection && (
                        <p>{acknowledged.facts.selection}</p>
                    )}
                    {(acknowledged.facts.attempts || []).map(
                        (attempt, index) =>
                            attempt.result_name && (
                                <p key={`result-${index}`}>
                                    Recorded result: {attempt.result_name}
                                </p>
                            ),
                    )}
                    {acknowledged.facts.rolls.map((roll, index) => (
                        <p key={index}>
                            Recorded {roll.dice}: {roll.roll}
                        </p>
                    ))}
                    <ButtonLink
                        href={acknowledged.nextUrl}
                        onClick={(event) => {
                            event.preventDefault();
                            navigate(acknowledged.nextUrl);
                        }}
                    >
                        Review current flow
                    </ButtonLink>
                </Alert>
            )}
        </>
    );
    const footer = (
        <FormActions>
            {workflow.conflicted ? (
                <Button onClick={review}>Review current flow</Button>
            ) : workflow.uncertain ? (
                <>
                    <Button
                        type="submit"
                        variant="primary"
                        disabled={workflow.pending}
                    >
                        Retry save
                    </Button>
                    <Button
                        disabled={workflow.pending}
                        onClick={() =>
                            formRef.current &&
                            workflow.recoverAt(
                                props.recoveryHref,
                                formRef.current,
                            )
                        }
                    >
                        Reload
                    </Button>
                    <Button
                        disabled={workflow.pending}
                        onClick={() =>
                            formRef.current &&
                            workflow.recoverAt(
                                props.signInHref,
                                formRef.current,
                            )
                        }
                    >
                        Sign in again
                    </Button>
                </>
            ) : (
                !acknowledged && (
                    <>
                        {f.back_href &&
                            link(
                                f.back_href,
                                f.back_label || "← Back to model",
                            )}
                        {f.cancel_href &&
                            !["done", "cancel", "by-hand"].includes(f.stage) &&
                            !f.correction &&
                            link(f.cancel_href, "Cancel")}
                        {link(f.undo_href, "Undo advancement")}
                        {link(f.done_href, "Done", "primary")}
                        {f.submit_label && !f.recovery_only && (
                            <Button
                                type="submit"
                                variant={f.submit_variant || "primary"}
                                disabled={frozen}
                            >
                                {f.submit_label}
                            </Button>
                        )}
                    </>
                )
            )}
        </FormActions>
    );
    return (
        <BusyControlScope value={workflow.pending ? busyControl : null}>
            <WorkflowPage
                ref={formRef}
                title={props.title}
                lead={props.modelName}
                action={props.action}
                method="post"
                onSubmit={save}
                aria-busy={workflow.pending}
                onClickCapture={(event) => {
                    if (
                        frozen &&
                        event.target instanceof Element &&
                        event.target.closest("a[href]")
                    )
                        event.preventDefault();
                }}
                breadcrumb={
                    <Breadcrumbs
                        items={[
                            { label: props.gangName, href: props.gangHref },
                            { label: props.modelName, href: props.modelHref },
                            { label: props.title },
                        ]}
                    />
                }
                footer={footer}
            >
                {metadata.map((name) => (
                    <input
                        type="hidden"
                        key={name}
                        name={name}
                        value={values[name] || ""}
                    />
                ))}
                {props.hiddenFields
                    .filter((name) => !metadata.includes(name))
                    .map((name) => (
                        <input
                            type="hidden"
                            key={name}
                            name={name}
                            value={values[name] || ""}
                        />
                    ))}
                {f.decline_promotion && (
                    <>
                        <input
                            type="hidden"
                            name="request_key"
                            value={values.request_key || ""}
                        />
                        {values.decline_promotion && (
                            <input
                                type="hidden"
                                name="decline_promotion"
                                value={values.decline_promotion}
                            />
                        )}
                    </>
                )}
                <input
                    type="hidden"
                    name="csrfmiddlewaretoken"
                    value={props.csrfToken}
                />
                {recovery}
                {!acknowledged && (
                    <>
                        {f.earned_threshold && (
                            <p>Earned at {f.earned_threshold}.</p>
                        )}
                        <FlowProgress steps={f.steps} className="max-w-3xl" />
                        {f.prices.length > 0 && (
                            <FormSection title="Price">
                                {f.prices.map((price, index) => (
                                    <PaymentFigures
                                        key={index}
                                        figures={price}
                                    />
                                ))}
                            </FormSection>
                        )}
                        {!f.tracking_unavailable && !f.recovery_only && (
                            <>
                                {f.stage === "start" && (
                                    <RadioCards
                                        legend="Choose a result"
                                        min="min(100%, 18rem)"
                                        errors={errors.outcome || []}
                                    >
                                        {f.outcomes.map((outcome) => (
                                            <RadioCard
                                                key={outcome.key}
                                                name="outcome"
                                                value={outcome.key}
                                                label={outcome.name}
                                                description={
                                                    outcome.description
                                                }
                                                wrap
                                                checked={
                                                    values.outcome ===
                                                    outcome.key
                                                }
                                                disabled={frozen}
                                                onChange={() =>
                                                    change(
                                                        "outcome",
                                                        outcome.key,
                                                    )
                                                }
                                            />
                                        ))}
                                    </RadioCards>
                                )}
                                {["choose", "correct"].includes(f.stage) && (
                                    <FormSection title="Choose tier">
                                        {!!errors.selection?.length && (
                                            <FieldErrors
                                                errors={errors.selection}
                                            />
                                        )}
                                        {f.items.length ? (
                                            f.items.map((item) => (
                                                <RadioCards
                                                    key={item.key}
                                                    legend={item.name}
                                                    description={`Current: ${item.current}`}
                                                    min="min(100%, 18rem)"
                                                >
                                                    <RadioCard
                                                        name="selection"
                                                        value={item.key}
                                                        label={item.tier}
                                                        details={
                                                            <ActionDetail>
                                                                Model rating{" "}
                                                                {item.before}¢ →{" "}
                                                                {item.after}¢
                                                            </ActionDetail>
                                                        }
                                                        description={
                                                            item.effect
                                                        }
                                                        wrap
                                                        checked={
                                                            values.selection ===
                                                            item.key
                                                        }
                                                        disabled={frozen}
                                                        onChange={() =>
                                                            change(
                                                                "selection",
                                                                item.key,
                                                            )
                                                        }
                                                    ></RadioCard>
                                                </RadioCards>
                                            ))
                                        ) : (
                                            <ActionText>
                                                No carried item has an available
                                                tier.
                                            </ActionText>
                                        )}
                                    </FormSection>
                                )}
                                {f.stage === "roll" && f.roll && (
                                    <RollControls
                                        props={f.roll}
                                        values={values}
                                        errors={errors}
                                        frozen={frozen}
                                        change={change}
                                    />
                                )}
                                {f.stage === "advancement" && (
                                    <FormSection
                                        title={f.advancement_title}
                                        description={f.promotion_description}
                                    >
                                        <ActionRollSummary
                                            value={f.roll_value}
                                            explanation={f.roll_explanation}
                                        />
                                        <RadioCards
                                            legend=""
                                            min="min(100%, 18rem)"
                                            errors={errors.pickable_id || []}
                                        >
                                            {f.advancements.length ? (
                                                f.advancements.map((option) => (
                                                    <RadioCard
                                                        key={option.key}
                                                        name="pickable_id"
                                                        value={option.key}
                                                        label={option.name}
                                                        details={
                                                            <>
                                                                {f.threshold_roll && (
                                                                    <ActionDetail>
                                                                        Roll{" "}
                                                                        {
                                                                            option.minimum
                                                                        }
                                                                        +
                                                                    </ActionDetail>
                                                                )}
                                                                <ActionDetail>
                                                                    Rating +
                                                                    {
                                                                        option.rating
                                                                    }
                                                                    ¢
                                                                </ActionDetail>
                                                                {option.forcedRandom && (
                                                                    <ActionDetail>
                                                                        Roll for
                                                                        this
                                                                        skill.
                                                                    </ActionDetail>
                                                                )}
                                                            </>
                                                        }
                                                        wrap
                                                        checked={
                                                            values.pickable_id ===
                                                            option.key
                                                        }
                                                        disabled={frozen}
                                                        onChange={() =>
                                                            change(
                                                                "pickable_id",
                                                                option.key,
                                                            )
                                                        }
                                                    ></RadioCard>
                                                ))
                                            ) : (
                                                <ActionText>
                                                    No advancement can change
                                                    this model.
                                                </ActionText>
                                            )}
                                        </RadioCards>
                                        {f.decline_promotion && (
                                            <Button
                                                type="submit"
                                                data-intent="decline"
                                                formNoValidate
                                                disabled={frozen}
                                            >
                                                Keep current rank and roll 2D6
                                            </Button>
                                        )}
                                    </FormSection>
                                )}
                                {f.stage === "skill" && (
                                    <FormSection
                                        title={f.skill_title}
                                        description={f.skill_description}
                                    >
                                        {f.skill_random ? (
                                            f.skill_resolved ? (
                                                <Card>
                                                    <div className="space-y-2">
                                                        <p className="text-sm text-muted">
                                                            Current result
                                                        </p>
                                                        <h3 className="text-lg font-semibold">
                                                            {f.skill_selected}
                                                        </h3>
                                                        {f.skill_selected_group && (
                                                            <ActionText>
                                                                {
                                                                    f.skill_selected_group
                                                                }
                                                            </ActionText>
                                                        )}
                                                        <p>
                                                            {
                                                                f.skill_confirmation
                                                            }
                                                        </p>
                                                    </div>
                                                </Card>
                                            ) : f.correction ? (
                                                <ActionText>
                                                    This result needs a recorded
                                                    D6 roll. Choose a result
                                                    supported by the existing
                                                    rolls.
                                                </ActionText>
                                            ) : f.skillRoll?.choices?.options
                                                  .length ? (
                                                <RollControls
                                                    props={f.skillRoll}
                                                    values={values}
                                                    errors={errors}
                                                    frozen={frozen}
                                                    change={change}
                                                />
                                            ) : (
                                                <ActionText>
                                                    {f.skill_empty}
                                                </ActionText>
                                            )
                                        ) : (
                                            <>
                                                {!!errors.skill_id?.length && (
                                                    <FieldErrors
                                                        errors={errors.skill_id}
                                                    />
                                                )}
                                                {f.skillGroups.length ? (
                                                    f.skillGroups.map(
                                                        (group) => (
                                                            <RadioCards
                                                                key={group.key}
                                                                legend={
                                                                    group.name
                                                                }
                                                                min="min(100%, 18rem)"
                                                            >
                                                                {group.skills.map(
                                                                    (skill) => (
                                                                        <RadioCard
                                                                            key={
                                                                                skill.key
                                                                            }
                                                                            name="skill_id"
                                                                            value={
                                                                                skill.key
                                                                            }
                                                                            label={
                                                                                skill.name
                                                                            }
                                                                            checked={
                                                                                values.skill_id ===
                                                                                skill.key
                                                                            }
                                                                            disabled={
                                                                                frozen
                                                                            }
                                                                            onChange={() =>
                                                                                change(
                                                                                    "skill_id",
                                                                                    skill.key,
                                                                                )
                                                                            }
                                                                        />
                                                                    ),
                                                                )}
                                                            </RadioCards>
                                                        ),
                                                    )
                                                ) : (
                                                    <ActionText>
                                                        {f.skill_empty}
                                                    </ActionText>
                                                )}
                                                {f.skillGroups.length > 0 && (
                                                    <ActionText>
                                                        {f.skill_confirmation}
                                                    </ActionText>
                                                )}
                                            </>
                                        )}
                                        {f.attempts.length > 0 && (
                                            <details
                                                className="text-sm"
                                                open={
                                                    f.skill_random &&
                                                    !f.skill_resolved
                                                }
                                            >
                                                <summary className="cursor-pointer font-semibold text-muted">
                                                    Roll history
                                                </summary>
                                                <div className="mt-3">
                                                    <ActionAttempts
                                                        attempts={f.attempts}
                                                    />
                                                </div>
                                            </details>
                                        )}
                                    </FormSection>
                                )}
                                {[
                                    "review",
                                    "done",
                                    "on-hold",
                                    "undo",
                                    "by-hand",
                                    "cancel",
                                ].includes(f.stage) && (
                                    <ActionFacts
                                        facts={f}
                                        modelName={props.modelName}
                                        frozen={frozen}
                                        onNavigate={leave}
                                    />
                                )}
                                {f.stage === "review" &&
                                    f.payments.length > 0 && (
                                        <FormSection title="Payment">
                                            <div className="space-y-5">
                                                {f.payments.map(
                                                    (facts, index) => (
                                                        <div
                                                            key={index}
                                                            className="max-w-sm"
                                                        >
                                                            <Tally
                                                                facts={facts}
                                                            />
                                                        </div>
                                                    ),
                                                )}
                                            </div>
                                        </FormSection>
                                    )}
                                {f.stage === "reopen" && (
                                    <FormSection title="Undo marking as applied">
                                        <p>
                                            Make this earned use available again
                                            for {props.modelName}?
                                        </p>
                                        <p>
                                            Its recorded rolls and choices are
                                            kept.
                                        </p>
                                    </FormSection>
                                )}
                            </>
                        )}
                    </>
                )}
            </WorkflowPage>
        </BusyControlScope>
    );
}
