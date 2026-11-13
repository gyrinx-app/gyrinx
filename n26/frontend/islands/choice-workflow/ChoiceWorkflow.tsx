import {
    Fragment,
    type ComponentProps,
    type FormEvent,
    useId,
    useRef,
    useState,
} from "react";
import { fieldErrors } from "../../http/command";
import {
    Alert,
    BusyControlScope,
    Breadcrumbs,
    Button,
    ButtonLink,
    Dialog,
    FieldErrors,
    FormActions,
    FormSection,
    Input,
    Link,
    QuickSwitcher,
    RadioCard,
    RadioCards,
    UserLink,
    WorkflowPage,
    choiceRecipes as recipes,
    useWorkflowForm,
} from "../../ui";

export type ChoiceOption = {
    key: string;
    name: string;
    band: string;
    current: boolean;
    remark: string;
    summary: string;
    rating: number;
    removalRating: number | null;
    control: string;
};
export type ChoiceOffer = {
    label: string;
    takesSeveral: boolean;
    empty: boolean;
    groups: {
        name: string;
        caption: string;
        lifted: boolean;
        options: ChoiceOption[];
    }[];
};
type ChoiceQuestion = {
    key: string;
    headingId?: string;
    label: string;
    bearer: string;
    chosen: string | null;
    settled: boolean;
    rollHref: string;
    offer: ChoiceOffer;
};
export type ChoiceWorkflowProps = {
    title: string;
    lead: string;
    gangName: string;
    gangHref: string;
    owner: ComponentProps<typeof UserLink>;
    back: string;
    switcher: ComponentProps<typeof QuickSwitcher> | null;
    offer: ChoiceOffer | null;
    rollTable: { dice: string; lowest: number; highest: number } | null;
    roll: {
        key: string;
        total: number;
        dice: string;
        faces: number[];
        landed: string[];
        entered: boolean;
        applied: string;
        threshold: boolean;
        add: { key: string; name: string } | null;
    } | null;
    blocks?: {
        heading: string;
        description: string;
        skippable: boolean;
        questions: ChoiceQuestion[];
    }[];
    mayContinue?: boolean;
    outstanding?: string;
    skipHref?: string;
    values: Record<string, string>;
    errors: Record<string, string[]>;
    action: string;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
    arrivalRecoveryKey?: string;
    recoveryHref: string;
    signInHref: string;
    recoveryOnly: boolean;
    terminal: boolean;
    dialog: boolean;
    messages: {
        text: string;
        tone: "success" | "error" | "warning" | "info";
    }[];
};

function Die({ value }: { value: number }) {
    const faces = recipes.die.faces as Record<string, readonly boolean[]>;
    return (
        <span
            className={recipes.die.root}
            role="img"
            aria-label={`A die showing ${value}`}
        >
            {(faces[String(value)] ?? []).map((filled, index) => (
                <span
                    key={index}
                    className={filled ? recipes.die.filledPip : recipes.die.pip}
                />
            ))}
        </span>
    );
}

function Offer({
    offer,
    name,
    value,
    frozen,
    change,
    question = "",
    labelledBy,
}: {
    offer: ChoiceOffer;
    name: string;
    value: string;
    frozen: boolean;
    change: (value: string) => void;
    question?: string;
    labelledBy?: string;
}) {
    if (offer.empty)
        return (
            <p className={recipes.picks.empty}>
                {offer.takesSeveral
                    ? "Nothing is available to choose here."
                    : "No options are available yet. Other choices can make options available here."}
            </p>
        );
    return (
        <fieldset className={recipes.picks.root} aria-labelledby={labelledBy}>
            {offer.groups.map((group, index) =>
                offer.takesSeveral ? (
                    <fieldset key={index}>
                        {group.name && (
                            <legend className={recipes.picks.legend}>
                                {group.name}{" "}
                                <span className={recipes.picks.caption}>
                                    {group.caption}
                                </span>
                            </legend>
                        )}
                        <ul className={recipes.picks.list}>
                            {group.options.map((option) => (
                                <li
                                    key={option.key}
                                    className={recipes.picks.option}
                                >
                                    {option.band && (
                                        <span className={recipes.picks.band}>
                                            {option.band}
                                        </span>
                                    )}
                                    <span className={recipes.picks.body}>
                                        <span className={recipes.picks.name}>
                                            {option.name}
                                        </span>
                                        {option.summary && (
                                            <span
                                                className={
                                                    recipes.picks.summary
                                                }
                                            >
                                                {option.summary}
                                            </span>
                                        )}
                                        {option.control === "both" &&
                                        option.rating !==
                                            option.removalRating ? (
                                            <>
                                                <span
                                                    className={
                                                        recipes.picks.rating
                                                    }
                                                >
                                                    Rating per added pick{" "}
                                                    {option.rating}¢
                                                </span>
                                                <span
                                                    className={
                                                        recipes.picks
                                                            .removalRating
                                                    }
                                                >
                                                    Rating of next removed pick{" "}
                                                    {option.removalRating}¢
                                                </span>
                                            </>
                                        ) : (
                                            !!option.rating && (
                                                <span
                                                    className={
                                                        recipes.picks.rating
                                                    }
                                                >
                                                    Rating {option.rating}¢
                                                </span>
                                            )
                                        )}
                                        {option.remark && (
                                            <span
                                                className={recipes.picks.remark}
                                            >
                                                {option.remark}
                                            </span>
                                        )}
                                    </span>
                                    {["remove", "both"].includes(
                                        option.control,
                                    ) && (
                                        <Button
                                            type="submit"
                                            size="sm"
                                            variant="text-danger"
                                            disabled={frozen}
                                            data-intent="remove"
                                            data-thing={option.key}
                                            data-question={question}
                                            data-summary={`Remove ${option.name} — ${offer.label}.`}
                                            aria-label={`Remove ${option.name}`}
                                        >
                                            Remove
                                        </Button>
                                    )}
                                    {["choose", "both"].includes(
                                        option.control,
                                    ) && (
                                        <Button
                                            type="submit"
                                            size="sm"
                                            variant={
                                                group.lifted
                                                    ? "primary"
                                                    : "text"
                                            }
                                            disabled={frozen}
                                            data-intent="choose"
                                            data-thing={option.key}
                                            data-question={question}
                                            data-summary={`Add ${option.name} — ${offer.label}.`}
                                            aria-label={`Add ${option.name}${option.control === "both" ? " again" : ""}`}
                                        >
                                            Add
                                            {option.control === "both"
                                                ? " again"
                                                : ""}
                                        </Button>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </fieldset>
                ) : (
                    <RadioCards
                        key={index}
                        legend={group.name}
                        description={group.caption}
                    >
                        {group.options.map((option) => (
                            <RadioCard
                                key={option.key}
                                name={name}
                                value={option.key}
                                label={option.name}
                                description={option.remark}
                                checked={value === option.key}
                                disabled={frozen}
                                wrap={false}
                                onChange={() => change(option.key)}
                                details={
                                    <>
                                        {option.summary && (
                                            <span className="block">
                                                {option.summary}
                                            </span>
                                        )}
                                        {!!option.rating && (
                                            <span className="block text-muted">
                                                Rating {option.rating}¢
                                            </span>
                                        )}
                                    </>
                                }
                            />
                        ))}
                    </RadioCards>
                ),
            )}
        </fieldset>
    );
}

type ArrivalRecovery = {
    values: Record<string, string>;
    draftKey: string | null;
    blocked: boolean;
};

function arrivalDraftKey(
    base: string,
    values: URLSearchParams | Record<string, string>,
) {
    const value = (name: string) =>
        values instanceof URLSearchParams
            ? (values.get(name) ?? "")
            : (values[name] ?? "");
    let asks: unknown = value("asks");
    try {
        asks = JSON.parse(String(asks));
    } catch {
        /* Keep unsupported drafts separate for server validation. */
    }
    return `${base}:draft:${JSON.stringify([asks, value("next")])}`;
}

function stringMap(value: string | null): Record<string, string> | null {
    try {
        const parsed: unknown = JSON.parse(value ?? "null");
        return parsed &&
            typeof parsed === "object" &&
            !Array.isArray(parsed) &&
            Object.values(parsed).every((value) => typeof value === "string")
            ? (parsed as Record<string, string>)
            : null;
    } catch {
        return null;
    }
}

function questionState(question: ChoiceQuestion) {
    return JSON.stringify([
        question.chosen,
        question.settled,
        question.offer.groups
            .flatMap((group) => group.options)
            .filter((option) => option.current)
            .map((option) => option.key)
            .sort(),
    ]);
}

function retainArrivalReturn(
    props: ChoiceWorkflowProps,
    nextUrl: string,
    intent: string,
) {
    const namespace = props.arrivalRecoveryKey;
    if (
        !namespace ||
        props.blocks !== undefined ||
        !["choose", "remove"].includes(intent)
    )
        return;
    try {
        const global = sessionStorage.getItem(namespace);
        if (
            global &&
            new URLSearchParams(global).get("__workflow_rejected") !== "1"
        )
            return;
        const marker = JSON.parse(
            sessionStorage.getItem(`${namespace}:nested`) ?? "null",
        ) as {
            draftKey?: unknown;
            picker?: unknown;
            question?: unknown;
        } | null;
        if (
            !marker ||
            typeof marker.draftKey !== "string" ||
            typeof marker.question !== "string" ||
            !marker.draftKey.startsWith(`${namespace}:draft:`) ||
            marker.picker !==
                new URL(props.action, window.location.href).pathname
        )
            return;
        const stored = sessionStorage.getItem(marker.draftKey);
        if (!stored) return;
        const retained = new URLSearchParams(stored);
        const target = new URL(nextUrl, window.location.href);
        const asks: unknown = JSON.parse(retained.get("asks") ?? "null");
        const returned = target.searchParams.getAll("ask");
        if (!Array.isArray(asks) || !asks.includes(marker.question)) return;
        // A confirmed nested answer wins even when it matches the starting state.
        const selected = stringMap(retained.get("selection")) ?? {};
        delete selected[marker.question];
        retained.set("selection", JSON.stringify(selected));
        sessionStorage.setItem(marker.draftKey, retained.toString());
        if (
            target.origin !== window.location.origin ||
            target.pathname !== retained.get("__arrival_path") ||
            target.searchParams.get("next") !== retained.get("next") ||
            !asks.every(
                (key) => typeof key === "string" && returned.includes(key),
            )
        )
            return;
        retained.set("asks", JSON.stringify(returned));
        const targetKey = arrivalDraftKey(namespace, retained);
        const existing = new URLSearchParams(
            sessionStorage.getItem(targetKey) ?? "",
        );
        for (const field of ["selection", "__arrival_baseline"])
            retained.set(
                field,
                JSON.stringify({
                    ...stringMap(existing.get(field)),
                    ...stringMap(retained.get(field)),
                }),
            );
        const merged = stringMap(retained.get("selection")) ?? {};
        delete merged[marker.question];
        retained.set("selection", JSON.stringify(merged));
        sessionStorage.setItem(targetKey, retained.toString());
        sessionStorage.removeItem(`${namespace}:nested`);
    } catch {
        // A confirmed save remains confirmed if passive storage is unavailable.
    }
}

function prepareArrivalRecovery(props: ChoiceWorkflowProps): ArrivalRecovery {
    if (props.blocks === undefined)
        return { values: props.values, draftKey: null, blocked: false };
    const draftKey = arrivalDraftKey(props.recoveryKey, props.values);
    try {
        const global = sessionStorage.getItem(props.recoveryKey);
        if (global) {
            const retained = new URLSearchParams(global);
            if (retained.get("__workflow_rejected") !== "1")
                return { values: props.values, draftKey, blocked: false };
            // Unsent navigation drafts are stored separately from submitted commands.
            sessionStorage.setItem(
                arrivalDraftKey(props.recoveryKey, retained),
                global,
            );
            sessionStorage.removeItem(props.recoveryKey);
        }
        const stored = sessionStorage.getItem(draftKey);
        const retained = stored ? new URLSearchParams(stored) : null;
        const complete =
            retained &&
            Object.keys(props.values)
                .filter((name) => name !== "summary")
                .every((name) => retained.has(name));
        const values = { ...props.values };
        if (complete) {
            const selected = stringMap(retained.get("selection")) ?? {};
            const baseline = stringMap(retained.get("__arrival_baseline"));
            values.selection = JSON.stringify(
                Object.fromEntries(
                    props.blocks
                        .flatMap((block) => block.questions)
                        .filter(
                            (question) =>
                                question.key in selected &&
                                (baseline
                                    ? baseline[question.key] ===
                                      questionState(question)
                                    : !question.chosen &&
                                      !question.settled &&
                                      !question.offer.groups.some((group) =>
                                          group.options.some(
                                              (option) => option.current,
                                          ),
                                      )),
                        )
                        .map((question) => [
                            question.key,
                            selected[question.key],
                        ]),
                ),
            );
        }
        return { values, draftKey, blocked: false };
    } catch {
        return { values: props.values, draftKey, blocked: true };
    }
}

export function ChoiceWorkflow(
    props: ChoiceWorkflowProps & {
        onNavigate?: (url: string) => void;
        onReload?: () => void;
    },
) {
    const formRef = useRef<HTMLFormElement>(null);
    const ownRollId = useId();
    const [busyControl, setBusyControl] = useState<string | null>(null);
    const [arrivalRecovery] = useState(() => prepareArrivalRecovery(props));
    const submittedIntent = useRef("");
    const workflow = useWorkflowForm({
        ...props,
        values: arrivalRecovery.values,
        optionalRecoveryFields: ["summary"],
        initialConflict: props.terminal,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string") {
                retainArrivalReturn(
                    props,
                    data.nextUrl,
                    submittedIntent.current,
                );
                return { kind: "saved", nextUrl: data.nextUrl };
            }
            if (
                status === 409 &&
                data.code === "choice_unavailable" &&
                fieldErrors(data.errors)
            )
                return { kind: "conflict", errors: data.errors };
            if (status === 422 && fieldErrors(data.errors))
                return { kind: "invalid", errors: data.errors };
            return null;
        },
    });
    const isArrivals = props.blocks !== undefined;
    const values = workflow.values;
    let selected: Record<string, string> = {};
    try {
        const decoded: unknown = JSON.parse(values.selection || "{}");
        if (decoded && typeof decoded === "object" && !Array.isArray(decoded))
            selected = decoded as Record<string, string>;
    } catch {
        /* The server validates a retained selection before writing. */
    }
    const frozen = workflow.frozen || arrivalRecovery.blocked;
    function update(name: string, value: string) {
        workflow.setValues((current) => ({ ...current, [name]: value }));
    }
    function save(event: FormEvent<HTMLFormElement>) {
        if (arrivalRecovery.blocked) {
            event.preventDefault();
            return;
        }
        if (arrivalRecovery.draftKey) {
            try {
                sessionStorage.removeItem(arrivalRecovery.draftKey);
            } catch {
                /* The command controller still verifies storage before sending. */
            }
        }
        const submitter = (event.nativeEvent as SubmitEvent).submitter;
        setBusyControl(
            submitter instanceof HTMLElement
                ? (submitter.dataset.busyId ?? null)
                : null,
        );
        if (workflow.uncertain) submittedIntent.current = values.act;
        if (!workflow.uncertain) {
            const button = (event.nativeEvent as SubmitEvent).submitter;
            const intent =
                button instanceof HTMLButtonElement
                    ? button.dataset.intent
                    : undefined;
            const thing =
                button instanceof HTMLButtonElement
                    ? (button.dataset.thing ?? "")
                    : "";
            const question =
                button instanceof HTMLButtonElement
                    ? (button.dataset.question ?? "")
                    : "";
            const summary =
                button instanceof HTMLButtonElement
                    ? (button.dataset.summary ?? "")
                    : "";
            const next: Record<string, string> = {
                ...values,
                act: intent ?? (isArrivals ? "continue" : "choose"),
                summary: summary || values.summary || "Save selected choices.",
            };
            submittedIntent.current = next.act;
            if (intent === "choose" && thing) next.thing = thing;
            next.remove = intent === "remove" ? thing : "";
            if (isArrivals) {
                next.choice = question;
                if (next.act === "continue") {
                    const names = new Map<string, string>();
                    for (const block of props.blocks!)
                        for (const asked of block.questions) {
                            const chosen = asked.offer.groups
                                .flatMap((group) => group.options)
                                .find(
                                    (option) =>
                                        option.key === selected[asked.key],
                                );
                            if (chosen)
                                names.set(
                                    asked.key,
                                    `${asked.label} for ${asked.bearer}: ${chosen.name}`,
                                );
                        }
                    next.summary = names.size
                        ? Array.from(names.values()).join("; ")
                        : "Continue without changing choices.";
                }
            }
            for (const [name, value] of Object.entries(next)) {
                const control = event.currentTarget.elements.namedItem(name);
                if (control instanceof HTMLInputElement) control.value = value;
            }
            workflow.setValues(next);
        }
        window.history.replaceState(
            window.history.state,
            "",
            props.recoveryHref,
        );
        return workflow.save(event);
    }
    function leave(url: string) {
        if (frozen) return;
        (props.onNavigate ?? ((href) => window.location.assign(href)))(url);
    }
    function openArrivalRoll(url: string, question: string) {
        if (frozen || !formRef.current || !arrivalRecovery.draftKey) return;
        try {
            const retained = new URLSearchParams();
            new FormData(formRef.current).forEach((value, name) =>
                retained.append(name, String(value)),
            );
            retained.delete("csrfmiddlewaretoken");
            retained.set("__workflow_rejected", "1");
            retained.set(
                "__arrival_baseline",
                JSON.stringify(
                    Object.fromEntries(
                        props
                            .blocks!.flatMap((block) => block.questions)
                            .map((question) => [
                                question.key,
                                questionState(question),
                            ]),
                    ),
                ),
            );
            retained.set(
                "__arrival_path",
                new URL(props.action, window.location.href).pathname,
            );
            sessionStorage.setItem(
                arrivalRecovery.draftKey,
                retained.toString(),
            );
            sessionStorage.setItem(
                `${props.recoveryKey}:nested`,
                JSON.stringify({
                    draftKey: arrivalRecovery.draftKey,
                    question,
                    picker: new URL(url, window.location.href).pathname,
                }),
            );
        } catch {
            workflow.recoverAt(url, formRef.current);
            return;
        }
        leave(url);
    }
    const errors = workflow.hasErrors ? (
        <div ref={workflow.summary} tabIndex={-1} role="alert">
            {workflow.notice && <Alert tone="error">{workflow.notice}</Alert>}
            {Object.entries(workflow.errors).map(([name, messages]) => (
                <FieldErrors key={name} errors={messages} />
            ))}
            {workflow.uncertain && !workflow.conflicted && (
                <p>
                    Submitted choice:{" "}
                    {values.summary || "Original selected choices"}
                </p>
            )}
            {workflow.uncertain && !workflow.conflicted && (
                <Button
                    type="submit"
                    variant="success"
                    disabled={workflow.pending}
                >
                    Retry save
                </Button>
            )}
            {workflow.conflicted && (
                <Button
                    type="button"
                    variant="primary"
                    onClick={() => workflow.review(props.back)}
                >
                    Return to gang
                </Button>
            )}
            {!!workflow.notice && !workflow.conflicted && !workflow.pending && (
                <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                        if (formRef.current)
                            workflow.recoverAt(
                                props.signInHref,
                                formRef.current,
                            );
                    }}
                >
                    Sign in again
                </Button>
            )}
        </div>
    ) : null;
    const hidden = (
        <>
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={props.csrfToken}
            />
            {Object.entries(values).map(([name, value]) => (
                <input key={name} type="hidden" name={name} value={value} />
            ))}
        </>
    );
    const canContinue =
        isArrivals &&
        props.blocks!.every(
            (block) =>
                block.skippable ||
                block.questions.every(
                    (question) => question.settled || !!selected[question.key],
                ),
        );
    const actions = (
        <FormActions>
            {isArrivals ? (
                <>
                    <Button
                        type="submit"
                        variant="success"
                        data-intent="continue"
                        disabled={frozen || !canContinue}
                    >
                        Continue
                    </Button>
                    {props.skipHref && (
                        <ButtonLink
                            href={props.skipHref}
                            variant="ghost"
                            onClick={(event) => {
                                if (frozen) event.preventDefault();
                            }}
                        >
                            Skip
                        </ButtonLink>
                    )}
                </>
            ) : props.offer && !props.offer.takesSeveral ? (
                <Button type="submit" variant="success" disabled={frozen}>
                    Save
                </Button>
            ) : null}
            <ButtonLink
                href={props.back}
                variant="ghost"
                onClick={(event) => {
                    if (frozen) event.preventDefault();
                }}
            >
                Cancel
            </ButtonLink>
        </FormActions>
    );
    const content = (
        <>
            {hidden}
            {props.messages.map((message, index) => (
                <Alert key={index} tone={message.tone} dismissible>
                    {message.text}
                </Alert>
            ))}
            {arrivalRecovery.blocked && (
                <Alert tone="error">
                    Your browser could not restore these choices. Check this
                    site’s storage settings, then reload.
                </Alert>
            )}
            {errors}
            {props.recoveryOnly ? (
                <p>
                    This choice is no longer available. Retry an unconfirmed
                    save to check its original result.
                </p>
            ) : isArrivals ? (
                <div className={recipes.nextPage.root}>
                    {props.blocks!.map((block, index) => (
                        <section
                            key={index}
                            className={recipes.arrivalBlock.root}
                        >
                            <div className={recipes.arrivalBlock.header}>
                                <h2 className={recipes.arrivalBlock.heading}>
                                    {block.heading}
                                </h2>
                                {block.description && (
                                    <div
                                        className={
                                            recipes.arrivalBlock.description
                                        }
                                    >
                                        {block.description
                                            .split(/\n\s*\n/)
                                            .map((paragraph, i) => (
                                                <p key={i}>
                                                    {paragraph
                                                        .split(/\r?\n/)
                                                        .map(
                                                            (
                                                                line,
                                                                lineIndex,
                                                            ) => (
                                                                <Fragment
                                                                    key={
                                                                        lineIndex
                                                                    }
                                                                >
                                                                    {lineIndex >
                                                                        0 && (
                                                                        <br />
                                                                    )}
                                                                    {line}
                                                                </Fragment>
                                                            ),
                                                        )}
                                                </p>
                                            ))}
                                    </div>
                                )}
                            </div>
                            {block.questions.map((question, questionIndex) => (
                                <div
                                    key={`${question.key}:${questionIndex}`}
                                    className={recipes.arrivalQuestion.root}
                                >
                                    <div
                                        className={
                                            recipes.arrivalQuestion.header
                                        }
                                    >
                                        <h3
                                            id={question.headingId}
                                            className={
                                                recipes.arrivalQuestion.heading
                                            }
                                        >
                                            {question.label}{" "}
                                            <span
                                                className={
                                                    recipes.arrivalQuestion
                                                        .caption
                                                }
                                            >
                                                for {question.bearer}
                                            </span>
                                        </h3>
                                        {question.chosen ? (
                                            <p
                                                className={
                                                    recipes.arrivalQuestion
                                                        .status
                                                }
                                            >
                                                Chosen: {question.chosen}
                                            </p>
                                        ) : (
                                            !question.settled && (
                                                <p
                                                    className={
                                                        recipes.arrivalQuestion
                                                            .status
                                                    }
                                                >
                                                    Not chosen yet.
                                                </p>
                                            )
                                        )}
                                        {question.rollHref && (
                                            <p
                                                className={
                                                    recipes.arrivalQuestion
                                                        .status
                                                }
                                            >
                                                You can roll for this choice.{" "}
                                                <Link
                                                    href={question.rollHref}
                                                    onClick={(event) => {
                                                        event.preventDefault();
                                                        openArrivalRoll(
                                                            question.rollHref,
                                                            question.key,
                                                        );
                                                    }}
                                                >
                                                    Roll on its own page
                                                </Link>{" "}
                                                and come back here.
                                            </p>
                                        )}
                                    </div>
                                    <Offer
                                        offer={question.offer}
                                        name={`display-${index}-${question.key}`}
                                        question={question.key}
                                        labelledBy={question.headingId}
                                        value={
                                            selected[question.key] ??
                                            question.offer.groups
                                                .flatMap(
                                                    (group) => group.options,
                                                )
                                                .find(
                                                    (option) => option.current,
                                                )?.key ??
                                            ""
                                        }
                                        frozen={frozen}
                                        change={(value) =>
                                            update(
                                                "selection",
                                                JSON.stringify({
                                                    ...selected,
                                                    [question.key]: value,
                                                }),
                                            )
                                        }
                                    />
                                </div>
                            ))}
                        </section>
                    ))}
                    {!canContinue && (
                        <p className={recipes.nextPage.hint}>
                            Choose {props.outstanding} to continue.
                        </p>
                    )}
                </div>
            ) : (
                <>
                    {props.roll && (
                        <section className={recipes.rollResult.root}>
                            <span className={recipes.rollResult.result}>
                                {props.roll.faces.length ? (
                                    <span className={recipes.rollResult.faces}>
                                        {props.roll.faces.map((face, index) => (
                                            <span
                                                className={
                                                    recipes.rollResult.face
                                                }
                                                key={index}
                                            >
                                                <Die value={face} />
                                            </span>
                                        ))}
                                    </span>
                                ) : (
                                    <span
                                        className={recipes.rollResult.numeric}
                                        aria-hidden="true"
                                    >
                                        {props.roll.total}
                                    </span>
                                )}
                                <span className={recipes.rollResult.body}>
                                    <span
                                        className={recipes.rollResult.heading}
                                    >
                                        Rolled {props.roll.total}{" "}
                                        <span
                                            className={
                                                recipes.rollResult.diceLabel
                                            }
                                        >
                                            on a {props.roll.dice}
                                        </span>
                                    </span>
                                    <span
                                        className={
                                            recipes.rollResult.description
                                        }
                                    >
                                        {props.roll.applied ? (
                                            `Already applied: ${props.roll.applied}. Roll again for another result.`
                                        ) : props.roll.landed.length ? (
                                            <>
                                                {props.roll.threshold
                                                    ? "High enough for"
                                                    : "Landed on"}{" "}
                                                {props.roll.landed.map(
                                                    (name, index) => (
                                                        <span key={index}>
                                                            {index > 0 && ", "}
                                                            <strong
                                                                className={
                                                                    recipes
                                                                        .rollResult
                                                                        .landing
                                                                }
                                                            >
                                                                {name}
                                                            </strong>
                                                        </span>
                                                    ),
                                                )}
                                                .
                                            </>
                                        ) : (
                                            `This table has no result for ${props.roll.total}.`
                                        )}{" "}
                                        {props.roll.entered && "Manual roll."}
                                    </span>
                                </span>
                            </span>
                            {!props.roll.applied && (
                                <span className={recipes.rollResult.actions}>
                                    {props.roll.add && (
                                        <Button
                                            type="submit"
                                            variant="primary"
                                            className={recipes.rollResult.add}
                                            disabled={frozen}
                                            data-intent="choose"
                                            data-thing={props.roll.add.key}
                                            data-summary={`Add ${props.roll.add.name} from roll ${props.roll.total}.`}
                                        >
                                            Add {props.roll.add.name}
                                        </Button>
                                    )}
                                    <Button
                                        type="submit"
                                        variant="ghost"
                                        size="sm"
                                        disabled={frozen}
                                        data-intent="roll"
                                        data-summary={`Roll ${props.roll.dice} again.`}
                                    >
                                        Roll again
                                    </Button>
                                </span>
                            )}
                        </section>
                    )}
                    {props.rollTable && (
                        <FormSection
                            title="Roll"
                            description="The roll is recorded in the gang’s history immediately, whether or not you choose a result."
                        >
                            <div className={recipes.rollTable.root}>
                                <Button
                                    type="submit"
                                    variant="primary"
                                    disabled={frozen}
                                    data-intent="roll"
                                    data-summary={`Roll ${props.rollTable.dice}.`}
                                >
                                    Roll a {props.rollTable.dice}
                                </Button>
                                <div
                                    role="separator"
                                    className={recipes.rollTable.divider}
                                >
                                    <span className={recipes.divider.line} />
                                    <span className={recipes.divider.label}>
                                        or
                                    </span>
                                    <span className={recipes.divider.line} />
                                </div>
                                <span
                                    className={
                                        recipes.rollTable.verticalDivider
                                    }
                                    aria-hidden="true"
                                />
                                <div className={recipes.rollTable.manual}>
                                    <div
                                        className={
                                            recipes.rollTable.inputWrapper
                                        }
                                    >
                                        <Input
                                            type="number"
                                            inputMode="numeric"
                                            value={values.rolled || ""}
                                            disabled={frozen}
                                            placeholder={`Your own roll (${props.rollTable.lowest}–${props.rollTable.highest})`}
                                            aria-label="The roll you made yourself"
                                            onChange={(event) =>
                                                update(
                                                    "rolled",
                                                    event.target.value,
                                                )
                                            }
                                            onKeyDown={(event) => {
                                                if (event.key === "Enter") {
                                                    event.preventDefault();
                                                    const button =
                                                        document.getElementById(
                                                            ownRollId,
                                                        );
                                                    if (
                                                        button instanceof
                                                        HTMLButtonElement
                                                    )
                                                        event.currentTarget.form?.requestSubmit(
                                                            button,
                                                        );
                                                }
                                            }}
                                        />
                                    </div>
                                    <Button
                                        id={ownRollId}
                                        type="submit"
                                        variant="default"
                                        disabled={frozen}
                                        data-intent="enter"
                                        data-summary={`Record own roll ${values.rolled || ""}.`}
                                    >
                                        Enter
                                    </Button>
                                </div>
                            </div>
                        </FormSection>
                    )}
                    {(props.roll || props.rollTable) && (
                        <div
                            role="separator"
                            className={`${recipes.divider.root} py-6`}
                        >
                            <span className={recipes.divider.line} />
                            <span className={recipes.divider.label}>
                                or add a result by hand
                            </span>
                            <span className={recipes.divider.line} />
                        </div>
                    )}
                    {props.offer && (
                        <Offer
                            offer={props.offer}
                            name="display-choice"
                            value={values.thing || ""}
                            frozen={frozen}
                            change={(value) => {
                                update("thing", value);
                                const label = props
                                    .offer!.groups.flatMap(
                                        (group) => group.options,
                                    )
                                    .find(
                                        (option) => option.key === value,
                                    )?.name;
                                update(
                                    "summary",
                                    `Choose ${label || value} — ${props.offer!.label}.`,
                                );
                            }}
                        />
                    )}
                </>
            )}
        </>
    );
    if (props.dialog)
        return (
            <BusyControlScope value={workflow.pending ? busyControl : null}>
                <Dialog
                    title={props.title}
                    lead={props.lead}
                    pending={frozen}
                    onDismiss={() => leave(props.back)}
                    onSubmit={save}
                    formProps={{
                        ref: formRef,
                        method: "post",
                        action: props.action,
                    }}
                >
                    {content}
                    {actions}
                </Dialog>
            </BusyControlScope>
        );
    return (
        <BusyControlScope value={workflow.pending ? busyControl : null}>
            <WorkflowPage
                ref={formRef}
                title={props.title}
                lead={props.lead}
                action={props.action}
                method="post"
                onSubmit={save}
                aria-busy={workflow.pending}
                breadcrumb={
                    <Breadcrumbs
                        items={[
                            { label: <UserLink {...props.owner} /> },
                            { label: props.gangName, href: props.back },
                            { label: props.title },
                        ]}
                    />
                }
                trailing={
                    props.switcher ? (
                        <QuickSwitcher {...props.switcher} />
                    ) : undefined
                }
                footer={actions}
            >
                {content}
            </WorkflowPage>
        </BusyControlScope>
    );
}
