import { type FormEvent, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { fieldErrors } from "../../http/command";
import {
    Breadcrumbs,
    Button,
    ButtonLink,
    Callout,
    Field,
    FieldErrors,
    FormActions,
    HelpPopover,
    Icon,
    Input,
    NativeSelect,
    WorkflowLayout,
    useWorkflowForm,
} from "../../ui";
import { CrewPicker, type CrewModel } from "./CrewPicker";

type Selection = {
    id: string;
    name: string;
    profile?: string;
    role: string;
    card: string;
    override?: string;
};
type RosterRefusal = { requestKey: string; inputs: Record<string, string[]> };

type Acknowledgement = {
    action: string;
    revision: number;
    drawn: string[];
    selections: Selection[];
};
export type CrewWorkflowProps = {
    campaignName: string;
    campaignUrl: string;
    battleName: string;
    battleUrl: string;
    gangName: string;
    revision: number | null;
    models: CrewModel[];
    values: Record<string, string>;
    errors: Record<string, string[]>;
    crewHelp: { label: string; paragraphs: string[] };
    drawHelp: { label: string; paragraphs: string[] };
    action: string;
    commandHref: string;
    displayHref: string;
    csrfToken: string;
    recoveryKey: string;
    signInHref: string;
    initialConflict: boolean;
    readOnly: boolean;
    current: {
        revision: number;
        selections: { name: string; role: string; card: string }[];
    };
    acknowledgement: Acknowledgement | null;
    rosterChanged?: boolean;
    rosterRefusal?: RosterRefusal | null;
};

function isRosterRefusal(value: unknown): value is RosterRefusal {
    if (!value || typeof value !== "object") return false;
    const refusal = value as Partial<RosterRefusal>;
    return (
        typeof refusal.requestKey === "string" &&
        !!refusal.requestKey &&
        !!refusal.inputs &&
        typeof refusal.inputs === "object" &&
        !Array.isArray(refusal.inputs) &&
        Object.values(refusal.inputs).every(
            (values) =>
                Array.isArray(values) &&
                values.every((value) => typeof value === "string"),
        )
    );
}

function retainedSelections(value: string): Selection[] {
    try {
        const data: unknown = JSON.parse(value);
        if (!Array.isArray(data)) return [];
        return data.filter(
            (item): item is Selection =>
                item &&
                typeof item.name === "string" &&
                typeof item.role === "string" &&
                typeof item.card === "string",
        );
    } catch {
        return [];
    }
}

function isAcknowledgement(value: unknown): value is Acknowledgement {
    if (!value || typeof value !== "object") return false;
    const saved = value as Partial<Acknowledgement>;
    return (
        ["save", "draft", "draw"].includes(saved.action ?? "") &&
        typeof saved.revision === "number" &&
        Array.isArray(saved.drawn) &&
        saved.drawn.every((name) => typeof name === "string") &&
        Array.isArray(saved.selections) &&
        saved.selections.every(
            (selection) =>
                selection &&
                typeof selection.id === "string" &&
                typeof selection.name === "string" &&
                typeof selection.role === "string" &&
                typeof selection.card === "string",
        )
    );
}

function isCurrent(value: unknown): value is CrewWorkflowProps["current"] {
    if (!value || typeof value !== "object") return false;
    const current = value as Partial<CrewWorkflowProps["current"]>;
    return (
        typeof current.revision === "number" &&
        Array.isArray(current.selections) &&
        current.selections.every(
            (selection) =>
                selection &&
                typeof selection.name === "string" &&
                typeof selection.role === "string" &&
                typeof selection.card === "string",
        )
    );
}

export function CrewWorkflow(
    props: CrewWorkflowProps & {
        onNavigate?: (url: string) => void;
        onReload?: () => void;
    },
) {
    const [retainedBody] = useState(() => {
        try {
            const stored = sessionStorage.getItem(props.recoveryKey);
            if (!stored) return null;
            const body = new URLSearchParams(stored);
            return body;
        } catch {
            return null;
        }
    });
    const rejectedBody =
        retainedBody?.get("__workflow_rejected") === "1" ? retainedBody : null;
    const rejectedSnapshot = retainedSelections(
        rejectedBody?.get("submitted_snapshot") ?? "[]",
    );
    const rejectedRosterChanged =
        (!retainedBody && !!props.rosterChanged) ||
        rejectedSnapshot.some(
            (selection) =>
                !props.models.some((model) => model.id === selection.id),
        ) ||
        (!!rejectedBody &&
            Array.from(rejectedBody).some(
                ([name, value]) =>
                    name.startsWith("role_") &&
                    value !== "out" &&
                    !props.models.some((model) => model.role.name === name),
            ));
    const [acknowledged, setAcknowledged] = useState(
        retainedBody ? null : props.acknowledgement,
    );
    const [current, setCurrent] = useState(props.current);
    const [rosterRefusal, setRosterRefusal] = useState<
        (RosterRefusal & { errors: Record<string, string[]> }) | null
    >(
        !retainedBody && props.rosterRefusal
            ? { ...props.rosterRefusal, errors: props.errors }
            : null,
    );
    const [reloadNotice, setReloadNotice] = useState("");
    const submittedKey = useRef(props.values.request_key);
    const actions = useRef<HTMLDivElement>(null);
    const element = useRef<HTMLFormElement>(null);
    const form = useWorkflowForm({
        ...props,
        optionalRecoveryFields: Object.keys(props.values).filter(
            (name) =>
                /^(role_|card_|override_)/.test(name) ||
                name === "submitted_snapshot",
        ),
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string") {
                if (data.newer === true) {
                    if (!isAcknowledgement(data.acknowledged)) return null;
                    setAcknowledged(data.acknowledged);
                    return { kind: "completed" };
                }
                return { kind: "saved", nextUrl: data.nextUrl };
            }
            if (
                status === 422 &&
                data.code === "roster_changed" &&
                isRosterRefusal(data.rosterRefusal) &&
                data.rosterRefusal.requestKey === submittedKey.current &&
                fieldErrors(data.errors)
            ) {
                setRosterRefusal({
                    ...data.rosterRefusal,
                    errors: data.errors,
                });
                return { kind: "conflict", errors: data.errors };
            }
            if (
                (status === 422 || status === 409) &&
                fieldErrors(data.errors)
            ) {
                if (
                    data.code === "revision_conflict" &&
                    !isCurrent(data.current)
                )
                    return null;
                if (isCurrent(data.current)) setCurrent(data.current);
                return {
                    kind:
                        data.code === "revision_conflict"
                            ? "conflict"
                            : "invalid",
                    errors: data.errors,
                };
            }
            return null;
        },
        onComplete() {},
    });
    const { values, setValues, pending } = form;
    const uncertain = form.uncertain && !rosterRefusal;
    const errors = rosterRefusal?.errors ?? form.errors;
    submittedKey.current = values.request_key;
    const modelFields = new Set(
        props.models.flatMap((model) => [
            model.role.name,
            model.card.name,
            model.override.name,
        ]),
    );
    const unknownModelErrors = Object.keys(errors).some(
        (name) =>
            /^(role_|card_|override_)/.test(name) && !modelFields.has(name),
    );
    const modelErrors = props.models.flatMap((model) =>
        [model.role.name, model.card.name, model.override.name].flatMap(
            (name) =>
                (errors[name] ?? []).map(
                    (message) => `${model.name}: ${message}`,
                ),
        ),
    );
    const unavailableEquipment = rejectedBody
        ? props.models.filter(
              (model) =>
                  values[model.role.name] &&
                  values[model.role.name] !== "out" &&
                  values[model.card.name] &&
                  !model.card.choices.some(
                      (choice) => choice.value === values[model.card.name],
                  ),
          )
        : [];
    const selected = props.models.filter(
        (model) => values[model.role.name] && values[model.role.name] !== "out",
    );
    const starting = selected.filter(
        (model) => values[model.role.name] === "starting",
    ).length;
    const frozen =
        form.frozen ||
        props.readOnly ||
        rejectedRosterChanged ||
        !!rosterRefusal ||
        unknownModelErrors;
    const submittedSnapshot = JSON.stringify(
        props.models
            .filter((model) => values[model.role.name] !== "out")
            .map((model) => ({
                id: model.id,
                name: model.name,
                profile: model.profile,
                role: values[model.role.name],
                card:
                    model.card.choices.find(
                        (choice) => choice.value === values[model.card.name],
                    )?.label ?? values[model.card.name],
                override: values[model.override.name],
            })),
    );
    const missingSelections = Object.keys(values)
        .filter(
            (name) =>
                name.startsWith("role_") &&
                values[name] !== "out" &&
                !props.models.some((model) => model.role.name === name),
        )
        .map((name) => ({
            id: name.slice(5),
            name: "Model no longer on this roster",
            role: values[name],
            card: "Saved equipment selection",
        }));
    const currentSnapshot = JSON.stringify([
        ...retainedSelections(submittedSnapshot),
        ...missingSelections,
    ]);
    const retained = uncertain
        ? retainedSelections(values.submitted_snapshot)
        : [];
    const hasRecoverySnapshot = uncertain;
    const selectedCount = uncertain ? retained.length : selected.length;
    const startingCount = uncertain
        ? retained.filter((selection) => selection.role === "starting").length
        : starting;
    useEffect(() => {
        const target = actions.current;
        if (!target) return;
        const measure = () =>
            document.documentElement.style.setProperty(
                "--n26-battle-actions-height",
                `${target.getBoundingClientRect().height}px`,
            );
        measure();
        const observer = window.ResizeObserver
            ? new ResizeObserver(measure)
            : null;
        observer?.observe(target);
        window.addEventListener("resize", measure);
        return () => {
            observer?.disconnect();
            window.removeEventListener("resize", measure);
            document.documentElement.style.removeProperty(
                "--n26-battle-actions-height",
            );
        };
    }, [acknowledged]);
    async function submit(event: FormEvent<HTMLFormElement>) {
        if (rejectedRosterChanged && !uncertain) {
            event.preventDefault();
            return;
        }
        const submitter = (event.nativeEvent as SubmitEvent).submitter;
        if (!uncertain) {
            flushSync(() =>
                setValues((previous) => ({
                    ...previous,
                    action:
                        submitter instanceof HTMLButtonElement
                            ? submitter.value || "save"
                            : previous.action,
                    submitted_snapshot: currentSnapshot,
                })),
            );
        }
        await form.save(event);
    }
    function reloadRoster() {
        if (!rosterRefusal || pending) return;
        try {
            const draft = new URLSearchParams();
            Object.entries(rosterRefusal.inputs).forEach(([name, values]) =>
                values.forEach((value) => draft.append(name, value)),
            );
            draft.set("request_key", window.crypto.randomUUID());
            draft.set("submitted_snapshot", values.submitted_snapshot);
            draft.set("__workflow_rejected", "1");
            sessionStorage.setItem(props.recoveryKey, draft.toString());
        } catch {
            setReloadNotice(
                "Your browser could not keep this draft. Allow this site to store data, then reload the page.",
            );
            return;
        }
        (props.onNavigate ?? ((url) => window.location.assign(url)))(
            `${props.action}?recover=1`,
        );
    }
    const help = (data: CrewWorkflowProps["crewHelp"]) => (
        <HelpPopover label={data.label}>
            {data.paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
            ))}
        </HelpPopover>
    );
    return (
        <WorkflowLayout
            fullWidth
            title="Choose crew"
            lead={`${props.gangName} · ${props.battleName}`}
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: props.campaignName, href: props.campaignUrl },
                        { label: props.battleName, href: props.battleUrl },
                        { label: "Choose crew" },
                    ]}
                />
            }
            footer={null}
        >
            {acknowledged ? (
                <section className="space-y-4" aria-label="Saved crew change">
                    <Callout>
                        {acknowledged.action === "draw"
                            ? "The earlier draw was saved."
                            : "The earlier crew change was saved."}{" "}
                        Revision {acknowledged.revision}.{" "}
                        {props.readOnly
                            ? "This crew is archived."
                            : "The saved crew has changed since then."}
                    </Callout>
                    {acknowledged.drawn.length > 0 && (
                        <p>Drawn models: {acknowledged.drawn.join(", ")}.</p>
                    )}
                    <ul>
                        {acknowledged.selections.map((selection, index) => (
                            <li key={`${selection.id}-${index}`}>
                                {selection.name} ·{" "}
                                {selection.role === "reserve"
                                    ? "Reinforcements"
                                    : "Starting crew"}{" "}
                                · {selection.card}
                            </li>
                        ))}
                    </ul>
                    <ButtonLink
                        href={`${props.action}?recover=1`}
                        onClick={(event) => {
                            if (props.onNavigate) {
                                event.preventDefault();
                                props.onNavigate(`${props.action}?recover=1`);
                            }
                        }}
                    >
                        Review current crew
                    </ButtonLink>
                </section>
            ) : (
                <form
                    ref={element}
                    method="post"
                    action={props.action}
                    onSubmit={submit}
                    data-busy="off"
                    aria-busy={pending}
                    className="space-y-6"
                >
                    <input
                        type="hidden"
                        name="csrfmiddlewaretoken"
                        value={props.csrfToken}
                    />
                    <input
                        type="hidden"
                        name="request_key"
                        value={values.request_key}
                    />
                    <input
                        type="hidden"
                        name="revision"
                        value={values.revision}
                    />
                    <input type="hidden" name="action" value={values.action} />
                    <input
                        type="hidden"
                        name="random_count"
                        value={values.random_count}
                    />
                    <input
                        type="hidden"
                        name="random_role"
                        value={values.random_role}
                    />
                    <input
                        type="hidden"
                        name="submitted_snapshot"
                        value={
                            uncertain
                                ? values.submitted_snapshot
                                : rejectedRosterChanged && rejectedBody
                                  ? values.submitted_snapshot
                                  : currentSnapshot
                        }
                    />
                    {frozen &&
                        Object.entries(values)
                            .filter(([name]) =>
                                /^(role_|card_|override_)/.test(name),
                            )
                            .map(([name, value]) => (
                                <input
                                    key={name}
                                    type="hidden"
                                    name={name}
                                    value={value}
                                />
                            ))}
                    {rejectedBody &&
                        Array.from(rejectedBody)
                            .filter(
                                ([name]) =>
                                    /^(role_|card_|override_)/.test(name) &&
                                    !(name in values),
                            )
                            .map(([name, value]) => (
                                <input
                                    key={name}
                                    type="hidden"
                                    name={name}
                                    value={value}
                                />
                            ))}
                    <div className="flex items-center gap-2 text-sm text-muted">
                        <p>Select the starting crew and any reinforcements.</p>
                        {help(props.crewHelp)}
                    </div>
                    {(form.hasErrors || rosterRefusal || reloadNotice) && (
                        <div
                            ref={form.summary}
                            tabIndex={-1}
                            role="alert"
                            aria-label="Crew save errors"
                        >
                            <FieldErrors
                                errors={[
                                    ...(errors.__all__ ?? []),
                                    ...(errors.revision ?? []),
                                    ...modelErrors,
                                    ...(unknownModelErrors && !rosterRefusal
                                        ? [
                                              "The roster changed. Reload the page to show the current models. Your selections have been kept.",
                                          ]
                                        : []),
                                    ...(reloadNotice ? [reloadNotice] : []),
                                    ...(form.notice ? [form.notice] : []),
                                ]}
                            />
                            {!form.notice &&
                                !errors.__all__?.length &&
                                !modelErrors.length &&
                                !unknownModelErrors &&
                                !rosterRefusal && (
                                    <p>
                                        Check the highlighted fields. Your
                                        selections have been kept.
                                    </p>
                                )}
                        </div>
                    )}
                    {form.conflicted && !rosterRefusal && (
                        <Callout>
                            <p>
                                The saved crew is now revision{" "}
                                {current.revision}. Review it before making
                                another change.
                            </p>
                            <ul>
                                {current.selections.map((selection, index) => (
                                    <li key={index}>
                                        {selection.name} · {selection.role} ·{" "}
                                        {selection.card}
                                    </li>
                                ))}
                            </ul>
                            <Button
                                type="button"
                                onClick={() =>
                                    form.review(`${props.action}?recover=1`)
                                }
                            >
                                Review current crew
                            </Button>
                        </Callout>
                    )}
                    {rejectedRosterChanged && !uncertain && !rosterRefusal && (
                        <Callout>
                            <p>
                                The roster changed while you were editing this
                                crew. Review the current roster before saving.
                            </p>
                            <ul>
                                {rejectedSnapshot.map((selection) => (
                                    <li key={selection.id}>
                                        {selection.name} · {selection.card}
                                    </li>
                                ))}
                            </ul>
                            <Button
                                type="button"
                                onClick={() =>
                                    (
                                        props.onNavigate ??
                                        ((url) => window.location.replace(url))
                                    )(`${props.action}?recover=1`)
                                }
                            >
                                Review current crew
                            </Button>
                        </Callout>
                    )}
                    {!!unavailableEquipment.length &&
                        !uncertain &&
                        !rosterRefusal && (
                            <Callout>
                                <p>
                                    These equipment sets are no longer
                                    available. Choose another set before saving.
                                </p>
                                <ul>
                                    {unavailableEquipment.map((model) => {
                                        const earlier = rejectedSnapshot.find(
                                            (selection) =>
                                                selection.id === model.id,
                                        );
                                        return (
                                            <li key={model.id}>
                                                {model.name}
                                                {earlier?.card
                                                    ? `: ${earlier.card}`
                                                    : ""}
                                            </li>
                                        );
                                    })}
                                </ul>
                            </Callout>
                        )}
                    {props.readOnly && (
                        <Callout>
                            This crew is archived. You can retry an earlier save
                            here.
                        </Callout>
                    )}
                    {hasRecoverySnapshot && (
                        <section
                            className="space-y-2"
                            aria-label="Unconfirmed crew selections"
                        >
                            <h2 className="font-semibold">
                                Selections in the earlier save
                            </h2>
                            {values.action === "draw" && (
                                <p>
                                    Draw {values.random_count} models into{" "}
                                    {values.random_role === "reserve"
                                        ? "reinforcements"
                                        : "the starting crew"}
                                    .
                                </p>
                            )}
                            <ul>
                                {retained.map((selection, index) => (
                                    <li key={`${selection.id}-${index}`}>
                                        {selection.name} ·{" "}
                                        {selection.role === "reserve"
                                            ? "Reinforcements"
                                            : "Starting crew"}{" "}
                                        · {selection.card}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}
                    <fieldset
                        disabled={frozen}
                        hidden={hasRecoverySnapshot}
                        className={hasRecoverySnapshot ? "hidden" : "contents"}
                    >
                        <section
                            className="border border-box-border bg-surface p-4"
                            aria-labelledby="crew-draw-heading"
                        >
                            <div className="mb-3 flex items-center gap-2">
                                <h2
                                    id="crew-draw-heading"
                                    className="font-semibold"
                                >
                                    Randomly select models
                                </h2>
                                {help(props.drawHelp)}
                            </div>
                            <div className="grid grid-cols-2 items-end gap-3 sm:flex sm:flex-wrap">
                                <div className="min-w-0 sm:w-28">
                                    <Field
                                        label="Number"
                                        htmlFor="draw-count"
                                        errors={errors.random_count}
                                    >
                                        <Input
                                            type="number"
                                            id="draw-count"
                                            min="1"
                                            value={values.random_count}
                                            onChange={(event) =>
                                                setValues((previous) => ({
                                                    ...previous,
                                                    random_count:
                                                        event.target.value,
                                                }))
                                            }
                                        />
                                    </Field>
                                </div>
                                <div className="min-w-0 sm:w-64">
                                    <Field
                                        label="Draw into"
                                        htmlFor="draw-role"
                                        errors={errors.random_role}
                                    >
                                        <NativeSelect
                                            id="draw-role"
                                            value={values.random_role}
                                            onChange={(event) =>
                                                setValues((previous) => ({
                                                    ...previous,
                                                    random_role:
                                                        event.target.value,
                                                }))
                                            }
                                        >
                                            {!["starting", "reserve"].includes(
                                                values.random_role,
                                            ) && (
                                                <option
                                                    value={values.random_role}
                                                    disabled
                                                >
                                                    Select a crew role
                                                </option>
                                            )}
                                            <option value="starting">
                                                Starting crew
                                            </option>
                                            <option value="reserve">
                                                Reinforcements
                                            </option>
                                        </NativeSelect>
                                    </Field>
                                </div>
                                <Button
                                    type="submit"
                                    value="draw"
                                    busy={pending && values.action === "draw"}
                                    className="col-span-2 w-full sm:w-auto"
                                >
                                    <span className="inline-flex items-center gap-2">
                                        <Icon name="dices" className="size-4" />
                                        Draw and save draft
                                    </span>
                                </Button>
                            </div>
                        </section>
                        <CrewPicker
                            models={props.models}
                            values={values}
                            errors={errors}
                            onChange={(name, value) =>
                                setValues((previous) => ({
                                    ...previous,
                                    [name]: value,
                                }))
                            }
                        />
                    </fieldset>
                    <div
                        ref={actions}
                        className="n26-battle-actions"
                        data-battle-actions
                        aria-label="Save crew"
                    >
                        <div className="n26-site-container flex flex-wrap items-center justify-between gap-3">
                            <div
                                className="text-sm"
                                role="status"
                                aria-live="polite"
                            >
                                <p className="font-semibold">
                                    {selectedCount}{" "}
                                    {selectedCount === 1 ? "model" : "models"}{" "}
                                    selected
                                </p>
                                <p className="text-xs text-muted">
                                    {startingCount} starting ·{" "}
                                    {selectedCount - startingCount}{" "}
                                    reinforcements
                                    {props.revision !== null &&
                                        ` · Revision ${values.revision}`}
                                </p>
                            </div>
                            <FormActions className="w-full sm:w-auto">
                                <ButtonLink
                                    href={props.battleUrl}
                                    variant="ghost"
                                >
                                    Back
                                </ButtonLink>
                                {rosterRefusal ? (
                                    <Button
                                        type="button"
                                        onClick={reloadRoster}
                                        disabled={pending}
                                    >
                                        Reload page
                                    </Button>
                                ) : uncertain ? (
                                    <Button
                                        type="submit"
                                        disabled={pending || form.conflicted}
                                        busy={pending}
                                    >
                                        Retry{" "}
                                        {values.action === "draw"
                                            ? "draw"
                                            : "save"}
                                    </Button>
                                ) : (
                                    <>
                                        <Button
                                            type="submit"
                                            value="draft"
                                            disabled={frozen}
                                            busy={
                                                pending &&
                                                values.action === "draft"
                                            }
                                        >
                                            Save draft
                                        </Button>
                                        <Button
                                            type="submit"
                                            value="save"
                                            variant="success"
                                            disabled={frozen}
                                            busy={
                                                pending &&
                                                values.action === "save"
                                            }
                                        >
                                            Save crew
                                        </Button>
                                    </>
                                )}
                                {form.hasErrors &&
                                    !form.conflicted &&
                                    !rosterRefusal && (
                                        <>
                                            <Button
                                                type="button"
                                                disabled={pending}
                                                onClick={() =>
                                                    element.current &&
                                                    form.recoverAt(
                                                        `${props.action}?recover=1`,
                                                        element.current,
                                                    )
                                                }
                                            >
                                                Reload page
                                            </Button>
                                            <Button
                                                type="button"
                                                disabled={pending}
                                                onClick={() =>
                                                    element.current &&
                                                    form.recoverAt(
                                                        props.signInHref,
                                                        element.current,
                                                    )
                                                }
                                            >
                                                Sign in again
                                            </Button>
                                        </>
                                    )}
                            </FormActions>
                        </div>
                    </div>
                </form>
            )}
        </WorkflowLayout>
    );
}
