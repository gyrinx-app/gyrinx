import { useState } from "react";
import {
    Button,
    ButtonLink,
    Dialog,
    Field,
    FormActions,
    NativeSelect,
} from "../../ui";

// The generator's Reroll dialog for one side job. The address names the
// side job, so the dialog opens when the page loads. Its form goes back to
// the generator with the scenario and reroll_set, and the server rolls.
export type ScenarioRerollProps = {
    title: string;
    action: string;
    cancelUrl: string;
    fields: [string, string][];
    sets: { value: string; label: string }[];
    set: string;
};

export const rerollNavigation = {
    assign(url: string) {
        window.location.assign(url);
    },
};

export function ScenarioReroll(props: ScenarioRerollProps) {
    const [set, setSet] = useState(props.set);
    return (
        <Dialog
            title={props.title}
            lead="Choose the set to roll on. The rest of the scenario stays the same."
            onDismiss={() => rerollNavigation.assign(props.cancelUrl)}
            onSubmit={(event) => {
                event.currentTarget.action = props.action;
                event.currentTarget.method = "get";
            }}
        >
            {props.fields.map(([name, value]) => (
                <input key={name} type="hidden" name={name} value={value} />
            ))}
            <Field label="Side job set" htmlFor="reroll-set">
                <NativeSelect
                    id="reroll-set"
                    name="reroll_set"
                    value={set}
                    onChange={(event) => setSet(event.target.value)}
                >
                    {props.sets.map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.label}
                        </option>
                    ))}
                </NativeSelect>
            </Field>
            <FormActions>
                <ButtonLink href={props.cancelUrl} variant="ghost">
                    Cancel
                </ButtonLink>
                <Button type="submit" variant="success">
                    Reroll
                </Button>
            </FormActions>
        </Dialog>
    );
}
