import { useId, useLayoutEffect, useRef, useState } from "react";
import {
    Button,
    ButtonLink,
    CheckboxCardItem,
    Field,
    FieldErrors,
    FormActions,
    Input,
    RadioCard,
    RadioCards,
} from "../../ui";

export type CampaignRollProps = {
    rolled: {
        label: string;
        helpText: string;
        value: string;
        errors: string[];
    };
    allocating?: boolean;
    inputId: string;
    avoidDuplicates?: {
        label: string;
        helpText: string;
        checked: boolean;
    } | null;
    table: string;
    tableErrors: string[];
    tables: {
        value: string;
        label: string;
        die: string;
        lowest: number;
        highest: number;
        availableCount?: number;
    }[];
    cancelUrl: string;
    /** The control focused before mount: rolled, submit, cancel or table:<value>. */
    focused?: string;
};

/** One roll on a campaign table, with the dialog's Cancel and submit. */
export function CampaignRoll(props: CampaignRollProps) {
    const duplicateHelpId = useId();
    const [avoidDuplicates, setAvoidDuplicates] = useState(
        props.avoidDuplicates?.checked ?? false,
    );
    const [table, setTable] = useState(props.table);
    const [rolled, setRolled] = useState(props.rolled.value);
    const rollRef = useRef<HTMLInputElement>(null);
    const cancelRef = useRef<HTMLAnchorElement>(null);
    const submitRef = useRef<HTMLButtonElement>(null);
    const only = props.tables.length === 1 ? props.tables[0] : null;
    const selected = props.tables.find((option) => option.value === table);

    useLayoutEffect(() => {
        const refs = { rolled: rollRef, cancel: cancelRef, submit: submitRef };
        refs[props.focused as keyof typeof refs]?.current?.focus();
    }, [props.focused]);

    return (
        <>
            {only ? (
                <>
                    <input type="hidden" name="table" value={only.value} />
                    <dl className="space-y-1">
                        <dt className="text-base font-semibold text-ink-900 dark:text-ink-100">
                            Table
                        </dt>
                        <dd className="text-base">
                            {only.label}{" "}
                            <span className="text-muted">· {only.die}</span>
                        </dd>
                    </dl>
                    {props.tableErrors.length > 0 && (
                        <FieldErrors errors={props.tableErrors} />
                    )}
                </>
            ) : (
                <RadioCards
                    legend="Table"
                    errors={props.tableErrors}
                    min="12rem"
                >
                    {props.tables.map((option) => (
                        <RadioCard
                            key={option.value}
                            name="table"
                            value={option.value}
                            label={option.label}
                            description={option.die}
                            checked={table === option.value}
                            onChange={() => setTable(option.value)}
                            autoFocus={
                                props.focused === `table:${option.value}`
                            }
                        />
                    ))}
                </RadioCards>
            )}
            {props.allocating && selected && (
                <p className="text-sm text-muted">
                    {selected.availableCount
                        ? `${selected.availableCount} matching territories available in the pool.`
                        : "No unclaimed territories from this table in the pool."}
                </p>
            )}
            <Field
                label={props.rolled.label}
                htmlFor={props.inputId}
                errors={props.rolled.errors}
                descriptionPlacement="before"
                description={
                    <div className="text-sm text-muted">
                        {props.rolled.helpText}{" "}
                        {selected && (
                            <span className="block">
                                A {selected.die} roll is {selected.lowest} to{" "}
                                {selected.highest}.
                            </span>
                        )}
                    </div>
                }
            >
                <Input
                    ref={rollRef}
                    id={props.inputId}
                    name="rolled"
                    type="number"
                    min={1}
                    inputMode="numeric"
                    autoComplete="off"
                    value={rolled}
                    onChange={(event) => setRolled(event.target.value)}
                />
            </Field>
            {/* The dialog closes on a click of a link to its own cancel address. */}
            {props.avoidDuplicates && (
                <div>
                    <CheckboxCardItem
                        name="avoid_duplicates"
                        value="on"
                        label={props.avoidDuplicates.label}
                        checked={avoidDuplicates}
                        disabled={rolled !== ""}
                        onCheckedChange={setAvoidDuplicates}
                        describedBy={duplicateHelpId}
                    />
                    <p id={duplicateHelpId} className="mt-1 text-sm text-muted">
                        {rolled !== ""
                            ? "Your own roll is recorded as entered."
                            : props.avoidDuplicates.helpText}
                    </p>
                </div>
            )}
            <FormActions>
                <ButtonLink
                    ref={cancelRef}
                    href={props.cancelUrl}
                    variant="ghost"
                >
                    Cancel
                </ButtonLink>
                <Button
                    ref={submitRef}
                    type="submit"
                    variant="success"
                    disabled={
                        props.allocating && selected?.availableCount === 0
                    }
                >
                    {props.allocating
                        ? rolled
                            ? "Use my roll and allocate"
                            : "Roll and allocate"
                        : rolled
                          ? "Use my roll"
                          : "Roll"}
                </Button>
            </FormActions>
        </>
    );
}
