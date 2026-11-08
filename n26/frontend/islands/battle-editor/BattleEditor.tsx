import { useEffect, useState } from "react";
import { fieldErrors } from "../../http/command";
import { CycleNavigator, type CycleOptions } from "./CycleNavigator";
import {
    BattleScenario,
    type BattleScenarioProps,
} from "../../scenarios/BattleScenario";
import {
    Breadcrumbs,
    Button,
    Field,
    FieldErrors,
    FormSection,
    Input,
    NativeSelect,
    WorkflowPage,
    useWorkflowForm,
} from "../../ui";

type Choice = { value: string; label: string };
export type BattleEditorProps = {
    campaignName: string;
    campaignHref: string;
    heading: string;
    editing: boolean;
    archived?: boolean;
    action: string;
    commandHref: string;
    back: string;
    csrfToken: string;
    values: Record<string, string>;
    choices: Record<string, Choice[]>;
    labels: Record<string, string>;
    errors: Record<string, string[]>;
    initialConflict: boolean;
    current: { revision: number; scenario: string; date: string } | null;
    recoveryKey: string;
    cycles: CycleOptions | null;
    cycleOptionsHref: string;
    scenario: BattleScenarioProps | null;
    onNavigate?: (url: string) => void;
    onReload?: () => void;
};
function identities(value: string | undefined): string[] {
    try {
        const parsed: unknown = JSON.parse(value ?? "[]");
        return Array.isArray(parsed) &&
            parsed.every((item) => typeof item === "string")
            ? parsed
            : [];
    } catch {
        return [];
    }
}
export function BattleEditor(props: BattleEditorProps) {
    useEffect(() => {
        const id = window.location.hash.slice(1);
        if (id === "outcome" || id === "stakes")
            document.getElementById(id)?.scrollIntoView?.();
    }, []);
    const [current, setCurrent] = useState(props.current);
    const [reviewUrl, setReviewUrl] = useState(props.action);
    const [scenarioBusy, setScenarioBusy] = useState(false);
    const [cycleBusy, setCycleBusy] = useState(false);
    const form = useWorkflowForm({
        ...props,
        optionalRecoveryFields: Object.keys(props.values).filter(
            (name) =>
                ![
                    "request_key",
                    "scenario",
                    "date",
                    "gangs",
                    ...(props.editing ? ["revision", "result", "winners"] : []),
                ].includes(name),
        ),
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
            if (
                status === 409 &&
                data.code === "revision_conflict" &&
                fieldErrors(data.errors) &&
                data.current &&
                typeof data.current === "object" &&
                "scenario" in data.current &&
                typeof data.current.scenario === "string"
            ) {
                setCurrent(data.current as BattleEditorProps["current"]);
                if (typeof data.reviewUrl === "string")
                    setReviewUrl(data.reviewUrl);
                return { kind: "conflict", errors: data.errors };
            }
            if (status === 422 && fieldErrors(data.errors))
                return { kind: "invalid", errors: data.errors };
            return null;
        },
    });
    const { values, errors } = form;
    const change = (name: string, value: string) =>
        form.setValues((current) => ({ ...current, [name]: value }));
    const navigate = (url: string) =>
        (props.onNavigate ?? ((href) => window.location.assign(href)))(url);
    const scenarioKeys = props.scenario
        ? [
              ...props.scenario.tables.map((table) => table.key),
              ...(props.scenario.sideJobKeys ?? []),
          ]
        : [];
    const fields = new Set([
        "scenario",
        "date",
        "result",
        "stake",
        "stake_awarded_to",
    ]);
    function checkboxList(name: "gangs" | "winners", label: string) {
        const selected = identities(values[name]);
        return (
            <fieldset className="space-y-2">
                <legend className="font-medium">{label}</legend>
                <FieldErrors errors={errors[name] ?? []} />
                {(props.choices[name] ?? []).map((choice) => (
                    <label
                        key={choice.value}
                        className="flex min-h-11 items-center gap-3"
                    >
                        <input
                            type="checkbox"
                            className="size-4 accent-[var(--color-accent)] focus-ring"
                            checked={selected.includes(choice.value)}
                            onChange={(event) =>
                                change(
                                    name,
                                    JSON.stringify(
                                        event.target.checked
                                            ? [...selected, choice.value]
                                            : selected.filter(
                                                  (id) => id !== choice.value,
                                              ),
                                    ),
                                )
                            }
                        />
                        {choice.label}
                    </label>
                ))}
                {!props.choices[name]?.length && (
                    <p className="text-sm text-muted">
                        No gangs in this campaign yet.
                    </p>
                )}
            </fieldset>
        );
    }
    function select(name: string) {
        return (
            name in values && (
                <Field
                    label={props.labels[name]}
                    htmlFor={`battle-${name}`}
                    errors={errors[name]}
                >
                    <NativeSelect
                        name={name}
                        value={values[name]}
                        onChange={(event) => change(name, event.target.value)}
                    >
                        {(props.choices[name] ?? []).map((choice) => (
                            <option key={choice.value} value={choice.value}>
                                {choice.label}
                            </option>
                        ))}
                    </NativeSelect>
                </Field>
            )
        );
    }
    return (
        <WorkflowPage
            title={props.heading}
            method="post"
            action={props.action}
            lead={
                props.editing
                    ? undefined
                    : "Record the battle before you play, then choose crews from its page. A participating player or the arbitrator records the outcome after the game."
            }
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: "Campaigns", href: "/n26/campaigns/" },
                        { label: props.campaignName, href: props.campaignHref },
                        { label: props.heading },
                    ]}
                />
            }
            onSubmit={(event) => {
                if (
                    scenarioBusy ||
                    cycleBusy ||
                    (props.archived && !form.uncertain)
                ) {
                    event.preventDefault();
                    return;
                }
                void form.save(event);
            }}
            aria-busy={form.pending}
            footer={
                <div className="flex flex-wrap items-center justify-end gap-3">
                    {form.conflicted ? (
                        <Button
                            variant="primary"
                            onClick={() => form.review(reviewUrl)}
                        >
                            Review current battle
                        </Button>
                    ) : (
                        <Button
                            type="submit"
                            variant="success"
                            disabled={
                                form.pending ||
                                scenarioBusy ||
                                cycleBusy ||
                                (props.archived && !form.uncertain)
                            }
                        >
                            {form.pending
                                ? "Saving…"
                                : form.uncertain
                                  ? "Retry save"
                                  : props.editing
                                    ? "Save changes"
                                    : "Record battle"}
                        </Button>
                    )}
                    <Button
                        variant="ghost"
                        disabled={form.pending || form.uncertain}
                        onClick={() =>
                            form.conflicted
                                ? form.review(props.back)
                                : navigate(props.back)
                        }
                    >
                        Cancel
                    </Button>
                </div>
            }
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={props.csrfToken}
            />
            {Object.entries(values)
                .filter(
                    ([name]) =>
                        !fields.has(name) && !scenarioKeys.includes(name),
                )
                .map(([name, value]) => (
                    <input key={name} type="hidden" name={name} value={value} />
                ))}
            {form.hasErrors && (
                <div
                    ref={form.summary}
                    tabIndex={-1}
                    role="alert"
                    aria-label="Battle save errors"
                >
                    <FieldErrors
                        errors={[
                            ...Object.values(errors).flat(),
                            ...(form.notice ? [form.notice] : []),
                        ]}
                    />
                </div>
            )}
            {form.conflicted && current && (
                <div className="rounded-control border border-box-border p-3">
                    <p className="font-medium">Current battle</p>
                    <p>
                        {current.scenario} · {current.date}
                    </p>
                    <p className="text-sm">
                        Your draft remains below. Review the current battle
                        before making another change.
                    </p>
                </div>
            )}
            {props.archived && (
                <p>
                    This battle is archived. You can retry an unresolved save.
                    Restore the battle before making another change.
                </p>
            )}
            <fieldset
                disabled={form.frozen || props.archived}
                className="space-y-6"
            >
                <FormSection title="Battle">
                    <Field
                        label="Name"
                        htmlFor="battle-scenario"
                        errors={errors.scenario}
                    >
                        <Input
                            name="scenario"
                            maxLength={200}
                            required={props.editing}
                            value={values.scenario}
                            onChange={(event) =>
                                change("scenario", event.target.value)
                            }
                        />
                    </Field>
                    <Field
                        label="Date *"
                        htmlFor="battle-date"
                        errors={errors.date}
                    >
                        <Input
                            name="date"
                            type="date"
                            required
                            value={values.date}
                            onChange={(event) =>
                                change("date", event.target.value)
                            }
                        />
                    </Field>
                    {props.cycles?.configured && (
                        <CycleNavigator
                            initial={props.cycles}
                            value={values.cycle ?? "null"}
                            onChange={(value) => change("cycle", value)}
                            readUrl={props.cycleOptionsHref}
                            errors={errors.cycle}
                            onBusyChange={setCycleBusy}
                        />
                    )}
                    {checkboxList("gangs", "Participants")}
                </FormSection>
                {props.scenario && (
                    <FormSection title="Scenario">
                        <BattleScenario
                            {...props.scenario}
                            disabled={form.frozen}
                            valueRolls={Object.fromEntries(
                                scenarioKeys.map((key) => [
                                    key,
                                    values[key] ?? "",
                                ]),
                            )}
                            onRollsChange={(rolls) =>
                                form.setValues((current) => ({
                                    ...current,
                                    ...Object.fromEntries(
                                        scenarioKeys.map((key) => [
                                            key,
                                            rolls[key] ?? "",
                                        ]),
                                    ),
                                }))
                            }
                            onBusyChange={setScenarioBusy}
                        />
                    </FormSection>
                )}

                {props.editing && (
                    <>
                        {"stake" in values && (
                            <div id="stakes" className="scroll-mt-24">
                                <FormSection title="Stakes">
                                    <p className="text-sm text-muted">
                                        Record the stake before or after the
                                        battle. Saving gives it to the gang you
                                        select. A correction moves it only while
                                        that gang still holds it.
                                    </p>
                                    {select("stake")}
                                    {select("stake_awarded_to")}
                                </FormSection>
                            </div>
                        )}
                        <div id="outcome" className="scroll-mt-24">
                            <FormSection title="After the game">
                                <p className="text-sm text-muted">
                                    Record the outcome once the battle is
                                    played. Saving does not change credits, XP
                                    or injuries.
                                </p>
                                {select("result")}
                                <p className="text-sm text-muted">
                                    Select winning participants for “Winner or
                                    winners”. Leave clear for a draw or an
                                    outcome not yet recorded.
                                </p>
                                {checkboxList("winners", "Winning gangs")}
                            </FormSection>
                        </div>
                    </>
                )}
            </fieldset>
        </WorkflowPage>
    );
}
