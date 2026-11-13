import {
    useEffect,
    useRef,
    useState,
    type ComponentProps,
    type ReactNode,
} from "react";
import { fieldErrors } from "../../http/command";
import {
    Alert,
    Breadcrumbs,
    Button,
    Dialog,
    DateInput,
    Field,
    FieldDescription,
    FieldErrors,
    FormActions,
    FlowProgress,
    Input,
    NativeSelect,
    Table,
    Textarea,
    Toggle,
    WorkflowPage,
    useWorkflowForm,
} from "../../ui";
import { PlanSteps } from "./PlanSteps";
import { SetupDraft } from "./SetupDraft";
import { RewardSettings } from "./RewardSettings";
import {
    restoreSetupDraft,
    retainSetupDraft,
    setupDraftKey,
    setupStageHref,
} from "./setupState";
import type { Editor, Phase } from "./types";

const visible: Record<string, string[]> = {
    setup: [
        "template_id",
        "mode",
        "current_number",
        "date_mode",
        "date_start",
        "cycle_interval",
        "cycle_unit",
    ],
    cycle: [
        "phase_id",
        "custom_name",
        "starts_on",
        "ends_on",
        "description",
        "effects",
    ],
    phase: ["name", "description", "effects"],
    "add-phase": ["name", "description", "effects"],
    "duplicate-phase": ["name"],
    "delete-phase": ["current_choice"],
    "delete-cycle": ["current_choice"],
    start: ["start_target"],
    plan: ["mode", "date_mode", "date_start", "cycle_interval", "cycle_unit"],
};

function EditorFrame({
    page,
    back,
    footer,
    breadcrumb,
    busy,
    ...props
}: ComponentProps<typeof Dialog> & {
    page: boolean;
    back: string;
    footer: ReactNode;
    breadcrumb?: ReactNode;
    busy?: boolean;
}) {
    const heading = useRef<HTMLHeadingElement>(null);
    useEffect(() => {
        if (page) heading.current?.focus({ preventScroll: true });
    }, [page]);
    if (!page)
        return (
            <Dialog {...props}>
                {props.children}
                {footer}
            </Dialog>
        );
    return (
        <WorkflowPage
            title={props.title}
            lead={props.lead}
            headingRef={heading}
            breadcrumb={
                breadcrumb ?? (
                    <Breadcrumbs
                        items={[
                            { label: "Phases & cycles", href: back },
                            { label: props.title },
                        ]}
                    />
                )
            }
            {...props.formProps}
            onSubmit={props.onSubmit}
            aria-busy={busy}
            footer={footer}
        >
            <div className="space-y-4">{props.children}</div>
        </WorkflowPage>
    );
}

export function ScheduleEditor({
    editor,
    phases,
    onNavigate,
    onReload,
    navigation,
    breadcrumb,
}: {
    editor: Editor;
    phases: Phase[];
    onNavigate?: (url: string) => void;
    onReload?: () => void;
    breadcrumb?: ReactNode;
    navigation?: {
        pending: boolean;
        error: string;
        retry: () => void;
        setGuard: (value: boolean) => void;
    };
}) {
    const [confirmed, setConfirmed] = useState(false);
    const [current, setCurrent] = useState(editor.current);
    const [reviewUrl, setReviewUrl] = useState(editor.back);
    const setupCompleted = useRef(false);
    const [initialValues] = useState(() => restoreSetupDraft(editor));
    const form = useWorkflowForm({
        ...editor,
        values: initialValues,
        optionalRecoveryFields: [
            "date_start",
            "cycle_interval",
            "cycle_unit",
            "date_version",
            "date_mode",
            "shift_later",
            "setup_definition",
            "no_current",
            "current_choice",
            "start_target",
        ],
        onNavigate,
        onReload,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string") {
                setupCompleted.current = true;
                if (editor.kind === "setup") {
                    try {
                        sessionStorage.removeItem(setupDraftKey(editor));
                    } catch {
                        /* Confirmed saves do not depend on browser storage. */
                    }
                }
                if (navigation) setConfirmed(true);
                return { kind: "saved", nextUrl: data.nextUrl };
            }
            if (
                status === 409 &&
                data.code === "revision_conflict" &&
                fieldErrors(data.errors) &&
                data.current &&
                typeof data.current === "object" &&
                "cycle" in data.current &&
                typeof data.current.cycle === "string"
            ) {
                setCurrent(data.current as Editor["current"]);
                if (typeof data.reviewUrl === "string")
                    setReviewUrl(data.reviewUrl);
                return { kind: "conflict", errors: data.errors };
            }
            if (
                (status === 422 ||
                    (status === 409 && data.code === "request_key_conflict")) &&
                fieldErrors(data.errors)
            )
                return { kind: "invalid", errors: data.errors };
            return null;
        },
    });
    const { values, errors } = form;
    useEffect(() => {
        if (editor.kind === "setup" && !setupCompleted.current && !form.frozen)
            retainSetupDraft(editor, values);
    }, [editor, values, form.frozen]);
    const noCurrent =
        values.no_current === "on" || values.no_current === "True";
    const currentNumber = values.current_number || "1";
    const shiftContext = editor.context.shiftLater as
        { endsOn: string } | undefined;
    const shiftDays =
        shiftContext && values.ends_on
            ? (Date.parse(`${values.ends_on}T00:00:00Z`) -
                  Date.parse(`${shiftContext.endsOn}T00:00:00Z`)) /
              86400000
            : 0;
    const shiftLater =
        values.shift_later === "on" || values.shift_later === "True";
    const routeStage = Number(editor.context.setupStage ?? 1);
    const [setupStep, setSetupStep] = useState(routeStage);
    useEffect(() => setSetupStep(routeStage), [routeStage]);
    const setupStage = form.frozen ? 3 : setupStep;
    const stageHref = (stage: number) => setupStageHref(editor.action, stage);
    const goToStage = (stage: number) => {
        setSetupStep(stage);
        (onNavigate ?? ((href: string) => window.location.assign(href)))(
            stageHref(stage),
        );
    };
    const previousSetupStage = useRef(setupStage);
    useEffect(() => {
        if (
            editor.kind === "setup" &&
            previousSetupStage.current !== setupStage
        ) {
            document
                .getElementById("cycle-setup-step")
                ?.focus({ preventScroll: true });
        }
        previousSetupStage.current = setupStage;
    }, [editor.kind, setupStage]);
    const modeDrafts = useRef<Record<string, string>>({
        [values.mode]: values.steps,
    });
    const setGuard = navigation?.setGuard;
    useEffect(() => {
        setGuard?.(form.pending || form.uncertain || confirmed);
        return () => setGuard?.(false);
    }, [form.pending, form.uncertain, confirmed, setGuard]);
    const unavailable = editor.context.unavailable === true;
    const deletion =
        editor.kind === "delete-phase" || editor.kind === "delete-cycle";
    const currentChoices = (editor.context.currentChoices ?? []) as Array<{
        value: string;
        label: string;
    }>;
    const change = (name: string, value: string) =>
        form.setValues({ ...values, [name]: value });
    const datesOnly =
        editor.kind === "cycle" && editor.context.datesOnly === true;
    const fields = new Set(
        editor.kind === "setup"
            ? setupStage === 1
                ? ["template_id"]
                : setupStage === 2
                  ? [
                        "mode",
                        ...(noCurrent ? [] : ["current_number"]),
                        "date_mode",
                        "date_start",
                        "cycle_interval",
                        "cycle_unit",
                    ]
                  : []
            : datesOnly
              ? ["starts_on", "ends_on"]
              : (visible[editor.kind] ?? []),
    );
    const text = (
        name: string,
        label: string,
        options: {
            type?: string;
            required?: boolean;
            min?: string;
            max?: string;
            help?: string;
            describedBy?: string;
        } = {},
    ) => (
        <Field
            label={label}
            htmlFor={`cycle-${name}`}
            errors={errors[name]}
            description={options.help}
        >
            {options.type === "date" ? (
                <DateInput
                    name={name}
                    value={values[name] ?? ""}
                    required={options.required}
                    min={options.min}
                    max={options.max}
                    clearLabel={`Clear ${label.toLowerCase()}`}
                    aria-describedby={options.describedBy}
                    onValueChange={(value) => change(name, value)}
                />
            ) : (
                <Input
                    name={name}
                    value={values[name] ?? ""}
                    type={options.type ?? "text"}
                    required={options.required}
                    min={options.min}
                    max={options.max}
                    onChange={(event) => change(name, event.target.value)}
                />
            )}
        </Field>
    );
    const mode = (
        <Field label="Planning mode" htmlFor="cycle-mode" errors={errors.mode}>
            <NativeSelect
                name="mode"
                value={values.mode}
                onChange={(event) => {
                    const mode = event.target.value;
                    if (editor.kind !== "plan") return change("mode", mode);
                    modeDrafts.current[values.mode] = values.steps;
                    const proposed =
                        mode === "repeating"
                            ? editor.context.patternSteps
                            : editor.context.fixedSteps;
                    const steps =
                        modeDrafts.current[mode] ??
                        (Array.isArray(proposed)
                            ? JSON.stringify(proposed)
                            : values.steps);
                    form.setValues({ ...values, mode, steps });
                }}
            >
                <option value="fixed">Fixed plan</option>
                <option value="repeating">Repeating pattern</option>
            </NativeSelect>
        </Field>
    );
    const plannedDates = values.date_mode !== "manual";
    const dates = "date_start" in editor.values && (
        <section className="space-y-3" aria-label="Cycle dates">
            <Field
                label="Cycle dates"
                htmlFor="cycle-date_mode"
                errors={errors.date_mode}
            >
                <NativeSelect
                    name="date_mode"
                    value={values.date_mode ?? "planned"}
                    onChange={(event) =>
                        change("date_mode", event.target.value)
                    }
                >
                    <option value="manual">No planned dates</option>
                    <option value="planned">Plan cycle dates</option>
                </NativeSelect>
            </Field>
            <p className="text-base">
                You advance each cycle when the campaign is ready. Dates are for
                planning.
            </p>
            {plannedDates ? (
                <>
                    {text(
                        "date_start",
                        editor.kind === "setup" ||
                            (!values.date_mode && editor.context.needsDates)
                            ? "Cycle 1 starts"
                            : values.date_mode
                              ? `Cycle ${editor.context.nextCycleNumber ?? 1} starts`
                              : "First projected cycle starts",
                        { type: "date", required: true },
                    )}
                    <div className="grid grid-cols-2 gap-3">
                        {text("cycle_interval", "Cycle length", {
                            type: "number",
                            min: "1",
                            max: "520",
                            required: true,
                        })}
                        <Field
                            label="Unit"
                            htmlFor="cycle-cycle_unit"
                            errors={errors.cycle_unit}
                        >
                            <NativeSelect
                                name="cycle_unit"
                                value={values.cycle_unit}
                                onChange={(event) =>
                                    change("cycle_unit", event.target.value)
                                }
                            >
                                <option value="weeks">Weeks</option>
                                <option value="months">Calendar months</option>
                            </NativeSelect>
                        </Field>
                    </div>
                    <p className="text-sm text-muted">
                        Each range includes its start and end dates.
                    </p>
                </>
            ) : (
                <p className="text-sm text-muted">
                    Future cycles have no planned dates. You can add dates to
                    individual cycles. Existing dates are kept.
                </p>
            )}
        </section>
    );
    const navigate = (url: string) =>
        (onNavigate ?? ((href) => window.location.assign(href)))(url);
    const footer = (
        <FormActions>
            {editor.kind === "setup" && setupStage > 1 && (
                <Button
                    disabled={form.frozen || confirmed}
                    onClick={() => goToStage(setupStage - 1)}
                >
                    Back
                </Button>
            )}
            {form.conflicted || (unavailable && !form.uncertain) ? (
                <Button
                    variant="primary"
                    onClick={() =>
                        form.conflicted
                            ? form.review(reviewUrl)
                            : navigate(editor.back)
                    }
                >
                    Review current schedule
                </Button>
            ) : (
                <Button
                    type="submit"
                    busy={form.pending || (confirmed && navigation?.pending)}
                    variant={
                        editor.kind === "setup" && setupStage < 3
                            ? "primary"
                            : deletion
                              ? "danger"
                              : "success"
                    }
                    disabled={form.pending || confirmed || navigation?.pending}
                >
                    {form.uncertain
                        ? "Retry save"
                        : editor.kind === "setup"
                          ? setupStage === 1
                              ? "Customise schedule"
                              : setupStage === 2
                                ? "Review schedule"
                                : "Set up phases & cycles"
                          : [
                                  "advance",
                                  "start",
                                  "finish",
                                  "delete-phase",
                                  "delete-cycle",
                              ].includes(editor.kind)
                            ? editor.heading
                            : "Save"}
                </Button>
            )}
            <Button
                variant="ghost"
                disabled={
                    form.pending ||
                    form.uncertain ||
                    confirmed ||
                    navigation?.pending
                }
                onClick={() =>
                    form.conflicted
                        ? form.review(editor.back)
                        : navigate(editor.back)
                }
            >
                Cancel
            </Button>
        </FormActions>
    );
    return (
        <EditorFrame
            page={editor.kind === "plan" || editor.kind === "setup"}
            back={editor.back}
            footer={footer}
            title={editor.heading}
            breadcrumb={breadcrumb}
            busy={form.pending || navigation?.pending}
            lead={
                editor.kind === "setup"
                    ? setupStage === 1
                        ? "Choose a starting point. You can change its phases, cycle counts and dates before setting up your campaign."
                        : setupStage === 2
                          ? "Set the phases, timing and current cycle for your campaign."
                          : "Review phases, cycle counts and dates before setting up this campaign."
                    : editor.lead
            }
            formProps={{ method: "post", action: editor.action }}
            pending={
                form.pending ||
                form.uncertain ||
                confirmed ||
                navigation?.pending
            }
            onSubmit={(event) => {
                if (unavailable && !form.uncertain) event.preventDefault();
                else if (editor.kind === "setup" && setupStage < 3) {
                    event.preventDefault();
                    goToStage(setupStage + 1);
                } else void form.save(event);
            }}
            onDismiss={() => {
                if (
                    !form.pending &&
                    !form.uncertain &&
                    !confirmed &&
                    !navigation?.pending
                )
                    form.conflicted
                        ? form.review(editor.back)
                        : navigate(editor.back);
            }}
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={editor.csrfToken}
            />
            {Object.entries(values)
                .filter(([name]) => !fields.has(name))
                .map(([name, value]) => (
                    <input key={name} type="hidden" name={name} value={value} />
                ))}
            {editor.context.selectStart === true && !unavailable ? (
                <Field
                    label="Cycle to start"
                    htmlFor="cycle-start_target"
                    errors={errors.start_target}
                >
                    <NativeSelect
                        name="start_target"
                        value={values.start_target ?? ""}
                        required
                        disabled={form.frozen || confirmed}
                        onChange={(event) =>
                            change("start_target", event.target.value)
                        }
                    >
                        <option value="">Choose a cycle</option>
                        {(
                            editor.context.startChoices as Array<{
                                value: string;
                                label: string;
                            }>
                        ).map((choice) => (
                            <option key={choice.value} value={choice.value}>
                                {choice.label}
                            </option>
                        ))}
                    </NativeSelect>
                </Field>
            ) : (
                editor.kind === "start" && (
                    <input
                        type="hidden"
                        name="start_target"
                        value={values.start_target ?? ""}
                    />
                )
            )}
            {deletion && !unavailable && (
                <div className="space-y-3">
                    <p>
                        {Number(editor.context.savedCount)}{" "}
                        {editor.kind === "delete-phase" ? "saved " : ""}
                        {Number(editor.context.savedCount) === 1
                            ? "cycle will"
                            : "cycles will"}{" "}
                        be removed from the schedule.
                        {editor.kind === "delete-phase" &&
                            (editor.context.repeating
                                ? " This phase will also be removed from every repetition of the future pattern."
                                : ` ${Number(editor.context.futureCount)} projected cycles will also be removed.`)}
                    </p>
                    {Number(editor.context.projectedPrefix) > 0 && (
                        <p>
                            Earlier projected cycles will be saved to keep their
                            original numbers. The future pattern will remain
                            unchanged.
                        </p>
                    )}
                    <p>
                        {Number(editor.context.battleCount) > 0 && (
                            <>
                                {Number(editor.context.battleCount)}{" "}
                                {Number(editor.context.battleCount) === 1
                                    ? "battle will"
                                    : "battles will"}{" "}
                                have no phase.{" "}
                            </>
                        )}
                        Battles and results will be kept. Recorded actions and
                        cycle history will be kept.
                    </p>
                    {editor.context.replacesCurrent === true ? (
                        <Field
                            label="Current cycle after deletion"
                            htmlFor="cycle-current_choice"
                            errors={errors.current_choice}
                        >
                            <NativeSelect
                                name="current_choice"
                                value={values.current_choice ?? ""}
                                required
                                disabled={form.frozen || confirmed}
                                onChange={(event) =>
                                    change("current_choice", event.target.value)
                                }
                            >
                                <option value="">Choose a current cycle</option>
                                <option value="none">No current cycle</option>
                                {currentChoices.map((choice) => (
                                    <option
                                        key={choice.value}
                                        value={choice.value}
                                    >
                                        {choice.label}
                                    </option>
                                ))}
                            </NativeSelect>
                        </Field>
                    ) : (
                        <input
                            type="hidden"
                            name="current_choice"
                            value={values.current_choice ?? ""}
                        />
                    )}
                    <p className="text-sm text-muted">
                        Deleting does not start a cycle, give rewards or send
                        notifications.
                    </p>
                </div>
            )}
            {form.hasErrors && (
                <Alert
                    tone="error"
                    dismissible={false}
                    ref={form.summary}
                    tabIndex={-1}
                    aria-label="Schedule save errors"
                >
                    <FieldErrors
                        errors={[
                            ...Object.values(errors).flat(),
                            ...(form.notice ? [form.notice] : []),
                        ]}
                    />
                </Alert>
            )}
            {form.conflicted && current && (
                <Alert tone="warning" dismissible={false}>
                    <p className="font-medium">Current schedule</p>
                    <p>
                        {current.cycle}
                        {current.phase ? ` · ${current.phase}` : ""}
                    </p>
                    <p className="mt-2">
                        Your draft remains below. Review the current schedule
                        before making another change.
                    </p>
                </Alert>
            )}
            {navigation?.error && (
                <Alert tone="error" dismissible={false}>
                    <p>
                        {confirmed && "Saved. "}
                        {navigation.error}
                    </p>
                    <Button
                        size="sm"
                        disabled={!confirmed && form.frozen}
                        onClick={navigation.retry}
                    >
                        Try again
                    </Button>
                </Alert>
            )}
            <div
                className={
                    editor.kind === "plan" || editor.kind === "setup"
                        ? "px-1"
                        : "max-h-[60vh] overflow-y-auto px-1"
                }
            >
                <fieldset
                    disabled={
                        form.frozen ||
                        unavailable ||
                        confirmed ||
                        navigation?.pending
                    }
                    className="space-y-4"
                >
                    {editor.kind === "setup" && (
                        <section className="space-y-4">
                            <FlowProgress
                                steps={[
                                    "Starting schedule",
                                    "Customise schedule",
                                    "Review schedule",
                                ].map((label, index) => ({
                                    label,
                                    current: index + 1 === setupStage,
                                    complete: index + 1 < setupStage,
                                    href:
                                        !form.frozen && index + 1 < setupStage
                                            ? stageHref(index + 1)
                                            : "",
                                }))}
                            />
                            <h2
                                id="cycle-setup-step"
                                tabIndex={-1}
                                className={
                                    setupStage === 3
                                        ? "sr-only"
                                        : "text-sm font-medium"
                                }
                            >
                                {setupStage === 1
                                    ? "Choose a starting schedule"
                                    : setupStage === 2
                                      ? "Customise your campaign"
                                      : "Review schedule"}
                            </h2>
                            {setupStage === 1 && (
                                <Field
                                    label="Starting schedule"
                                    htmlFor="cycle-template"
                                    errors={errors.template_id}
                                    description="Start with a custom schedule or use a template. You can edit every phase before saving."
                                >
                                    <NativeSelect
                                        name="template_id"
                                        value={values.template_id}
                                        onChange={(event) => {
                                            const template =
                                                editor.templates.find(
                                                    (item) =>
                                                        item.id ===
                                                        event.target.value,
                                                );
                                            form.setValues({
                                                ...values,
                                                template_id: event.target.value,
                                                setup_definition:
                                                    template?.definition
                                                        ? JSON.stringify(
                                                              template.definition,
                                                          )
                                                        : JSON.stringify(
                                                              editor.context
                                                                  .customDefinition,
                                                          ),
                                            });
                                        }}
                                    >
                                        <option value="">Custom</option>
                                        {editor.templates.map((template) => (
                                            <option
                                                key={template.id}
                                                value={template.id}
                                            >
                                                {template.name}
                                            </option>
                                        ))}
                                    </NativeSelect>
                                </Field>
                            )}
                            <SetupDraft
                                value={values.setup_definition ?? ""}
                                review={setupStage !== 2}
                                onChange={(value) =>
                                    change("setup_definition", value)
                                }
                            />
                            {setupStage === 2 && (
                                <>
                                    {mode}
                                    <Toggle
                                        label="No current cycle"
                                        checked={noCurrent}
                                        onCheckedChange={(checked) =>
                                            change(
                                                "no_current",
                                                checked ? "on" : "",
                                            )
                                        }
                                    />
                                    {!noCurrent &&
                                        text(
                                            "current_number",
                                            "Current cycle number",
                                            {
                                                type: "number",
                                                help: "Starts at Cycle 1 if left blank.",
                                                min: "1",
                                                max: "1000",
                                            },
                                        )}
                                    {dates}
                                </>
                            )}
                            {setupStage === 3 && (
                                <>
                                    <Table
                                        hover={false}
                                        className="border border-box-border [&_tbody_th]:font-semibold [&_tbody_th]:text-ink-900 dark:[&_tbody_th]:text-ink-100 [&_tbody_th]:whitespace-normal"
                                    >
                                        <caption className="pb-2 text-left font-semibold">
                                            Schedule settings
                                        </caption>
                                        <tbody>
                                            <tr>
                                                <th
                                                    scope="row"
                                                    className="w-1/2"
                                                >
                                                    Campaign length
                                                </th>
                                                <td className="text-right">
                                                    {values.mode === "repeating"
                                                        ? "Repeating"
                                                        : "Fixed"}
                                                </td>
                                            </tr>
                                            <tr>
                                                <th
                                                    scope="row"
                                                    className="w-1/2"
                                                >
                                                    Cycle dates
                                                </th>
                                                <td className="text-right">
                                                    {plannedDates
                                                        ? "Planned dates"
                                                        : "No planned dates"}
                                                </td>
                                            </tr>
                                            {plannedDates && (
                                                <>
                                                    <tr>
                                                        <th
                                                            scope="row"
                                                            className="w-1/2"
                                                        >
                                                            Cycle 1 starts
                                                        </th>
                                                        <td className="text-right">
                                                            <time
                                                                dateTime={
                                                                    values.date_start
                                                                }
                                                            >
                                                                {values.date_start
                                                                    ? new Date(
                                                                          `${values.date_start}T00:00:00Z`,
                                                                      ).toLocaleDateString(
                                                                          "en-GB",
                                                                          {
                                                                              day: "numeric",
                                                                              month: "short",
                                                                              year: "numeric",
                                                                              timeZone:
                                                                                  "UTC",
                                                                          },
                                                                      )
                                                                    : "Not set"}
                                                            </time>
                                                        </td>
                                                    </tr>
                                                    <tr>
                                                        <th
                                                            scope="row"
                                                            className="w-1/2"
                                                        >
                                                            Cycle length
                                                        </th>
                                                        <td className="text-right">
                                                            {
                                                                values.cycle_interval
                                                            }{" "}
                                                            {Number(
                                                                values.cycle_interval,
                                                            ) === 1
                                                                ? values.cycle_unit.slice(
                                                                      0,
                                                                      -1,
                                                                  )
                                                                : values.cycle_unit}
                                                        </td>
                                                    </tr>
                                                </>
                                            )}
                                            <tr>
                                                <th
                                                    scope="row"
                                                    className="w-1/2"
                                                >
                                                    Current cycle
                                                </th>
                                                <td className="text-right">
                                                    {noCurrent
                                                        ? "None"
                                                        : `Cycle ${currentNumber}`}
                                                </td>
                                            </tr>
                                        </tbody>
                                    </Table>
                                    <p className="text-base">
                                        {noCurrent
                                            ? "No cycle will be started. Cycles remain previews until you edit, use or start them."
                                            : `Cycles 1 through ${currentNumber} will be saved${plannedDates ? " with dates" : ""}. Later cycles remain previews until recorded.`}{" "}
                                        Your campaign keeps its own phases and
                                        pattern.
                                    </p>
                                </>
                            )}
                            {setupStage === 3 &&
                                editor.context.activates === true &&
                                !noCurrent && (
                                    <Alert tone="warning" dismissible={false}>
                                        Selecting “Set up phases &amp; cycles”
                                        starts Cycle {currentNumber}. This will
                                        send notifications to players
                                        participating in the campaign.
                                    </Alert>
                                )}
                        </section>
                    )}
                    {fields.has("name") &&
                        text("name", "Phase name", { required: true })}
                    {editor.kind === "cycle" && (
                        <>
                            {!datesOnly && (
                                <>
                                    <Field
                                        label="Phase"
                                        htmlFor="cycle-phase"
                                        errors={errors.phase_id}
                                    >
                                        <NativeSelect
                                            name="phase_id"
                                            value={values.phase_id}
                                            onChange={(event) =>
                                                change(
                                                    "phase_id",
                                                    event.target.value,
                                                )
                                            }
                                        >
                                            {phases.map((phase) => (
                                                <option
                                                    key={phase.id}
                                                    value={phase.id}
                                                >
                                                    {phase.name} · {phase.count}{" "}
                                                    saved cycles
                                                </option>
                                            ))}
                                        </NativeSelect>
                                    </Field>
                                    {text("custom_name", "Custom cycle name", {
                                        help: "Leave blank to use its cycle number.",
                                    })}
                                </>
                            )}
                            <div className="space-y-1">
                                <div className="grid gap-3 sm:grid-cols-2">
                                    {text("starts_on", "Start date", {
                                        type: "date",
                                        describedBy: "cycle-dates-help",
                                    })}
                                    {text("ends_on", "End date", {
                                        type: "date",
                                        describedBy: "cycle-dates-help",
                                    })}
                                </div>
                                <FieldDescription id="cycle-dates-help">
                                    Enter both dates or leave both blank.
                                </FieldDescription>
                            </div>
                        </>
                    )}
                    {editor.kind === "cycle" &&
                        shiftContext &&
                        (shiftDays !== 0 || shiftLater) && (
                            <section
                                className="space-y-1"
                                aria-label="Later cycle dates"
                            >
                                <Toggle
                                    label="Move later cycle dates too"
                                    checked={shiftLater}
                                    onCheckedChange={(checked) =>
                                        change(
                                            "shift_later",
                                            checked ? "on" : "",
                                        )
                                    }
                                />
                                <p className="text-xs text-muted">
                                    {Number.isFinite(shiftDays) &&
                                    shiftDays !== 0
                                        ? `${Math.abs(shiftDays)} ${Math.abs(shiftDays) === 1 ? "day" : "days"} ${shiftDays < 0 ? "earlier" : "later"}. `
                                        : ""}
                                    Moves later saved dates and previews,
                                    keeping their lengths and gaps unchanged.
                                </p>
                            </section>
                        )}
                    {fields.has("description") && (
                        <Field
                            label="Description and rules"
                            htmlFor="cycle-description"
                            errors={errors.description}
                        >
                            <Textarea
                                name="description"
                                rows={4}
                                value={values.description}
                                onChange={(event) =>
                                    change("description", event.target.value)
                                }
                            />
                        </Field>
                    )}
                    {fields.has("effects") && (
                        <Field
                            label="Effects"
                            htmlFor="cycle-effects"
                            errors={errors.effects}
                        >
                            <Textarea
                                name="effects"
                                rows={3}
                                value={values.effects}
                                onChange={(event) =>
                                    change("effects", event.target.value)
                                }
                            />
                        </Field>
                    )}
                    {["phase", "add-phase"].includes(editor.kind) && (
                        <RewardSettings
                            value={values.rewards}
                            onChange={(value) => change("rewards", value)}
                        />
                    )}
                    {editor.kind === "plan" && (
                        <>
                            {dates}
                            {mode}
                            <PlanSteps
                                value={values.steps}
                                phases={phases}
                                disabled={form.frozen}
                                onChange={(value) => change("steps", value)}
                                startsAfterOrder={
                                    values.mode === "fixed" &&
                                    typeof editor.context.startsAfterOrder ===
                                        "number"
                                        ? editor.context.startsAfterOrder
                                        : undefined
                                }
                            />
                        </>
                    )}
                </fieldset>
            </div>
        </EditorFrame>
    );
}
