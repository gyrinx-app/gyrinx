import { useId, useState } from "react";
import { Button, Field, Input } from "../../ui";

export type CounterAdjustmentProps = {
    value: number;
    recorded: number;
    change: string;
    errors: string[];
    maximum: number;
    isIncome?: boolean;
    inputValue?: string;
};

export function CounterAdjustment(props: CounterAdjustmentProps) {
    return props.isIncome ? (
        <IncomeAdjustment {...props} />
    ) : (
        <AmountAdjustment {...props} />
    );
}

function IncomeAdjustment(props: CounterAdjustmentProps) {
    const id = useId();
    const [value, setValue] = useState(props.inputValue ?? String(props.value));
    const contributions = props.value - props.recorded;
    const amount = Number(value);
    const valid = value.trim() !== "" && Number.isInteger(amount);
    return (
        <div className="space-y-5">
            <Field label="Income *" htmlFor={id} errors={props.errors}>
                <Input
                    id={id}
                    name="value"
                    type="number"
                    required
                    min={contributions}
                    max={contributions + 2147483647}
                    value={value}
                    onChange={(event) => setValue(event.target.value)}
                    className="h-16! text-left text-4xl! font-semibold tabular-nums"
                />
            </Field>
            <div className="space-y-2 text-sm text-muted">
                <p aria-live="polite" aria-atomic="true">
                    Contributions {contributions}¢ · manual adjustment{" "}
                    {valid ? `${amount - contributions}¢` : "—"}
                </p>
                <p>
                    The adjustment stays until you change or reset it. Add
                    collected income to your gang's credits.
                </p>
                <Button
                    type="submit"
                    name="reset"
                    value="1"
                    formNoValidate
                    size="sm"
                    disabled={!props.recorded}
                >
                    Reset adjustment
                </Button>
            </div>
        </div>
    );
}

function AmountAdjustment(props: CounterAdjustmentProps) {
    const id = useId();
    const [change, setChange] = useState(props.change);
    const amount = change.trim() === "" ? 0 : Number(change);
    const valid = Number.isInteger(amount) && Math.abs(amount) <= props.maximum;
    const delta = valid ? Math.max(-props.recorded, amount) : 0;
    const value = props.value + delta;
    return (
        <div className="space-y-5">
            <div
                className="space-y-1 text-left"
                aria-live="polite"
                aria-atomic="true"
            >
                <p className="text-sm text-muted">Value</p>
                <p
                    className="text-4xl font-semibold tabular-nums"
                    data-counter-preview
                >
                    {value}
                </p>
                <p
                    className="text-sm tabular-nums text-muted"
                    data-counter-delta
                >
                    {delta >= 0 ? "+" : ""}
                    {delta}
                </p>
            </div>
            <Field
                label="Change *"
                htmlFor={id}
                errors={props.errors}
                description="Use a positive number to add or a negative number to remove."
            >
                <Input
                    id={id}
                    name="change"
                    type="number"
                    required
                    min={-props.maximum}
                    max={props.maximum}
                    value={change}
                    onChange={(event) => setChange(event.target.value)}
                />
            </Field>
        </div>
    );
}
