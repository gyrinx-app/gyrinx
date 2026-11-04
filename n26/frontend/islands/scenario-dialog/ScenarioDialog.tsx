import { useState } from "react";
import {
    Button,
    ButtonLink,
    Dialog,
    Field,
    FieldErrors,
    FormActions,
    NativeSelect,
} from "../../ui";

export type ScenarioDialogProps = {
    mode: string;
    action: string;
    cancelUrl: string;
    selectionUrl: string;
    csrfToken: string;
    rolls: Record<string, number | string>;
    campaigns: { value: string; label: string }[];
    campaign: string;
    battles: {
        value: string;
        label: string;
        revision: number;
        hasScenario: boolean;
    }[];
    battle: string;
    revision: number | string | null;
    errors: Record<string, string[]>;
};

export const scenarioNavigation = {
    assign(url: string) {
        window.location.assign(url);
    },
};

export function ScenarioDialog(props: ScenarioDialogProps) {
    const connecting = props.mode === "save";
    const [battle, setBattle] = useState(props.battle);
    const selected = props.battles.find((option) => option.value === battle);
    const [revision, setRevision] = useState(props.revision);
    function chooseCampaign(value: string) {
        const url = new URL(props.selectionUrl, window.location.href);
        if (value) url.searchParams.set("campaign", value);
        else url.searchParams.delete("campaign");
        scenarioNavigation.assign(url.href);
    }
    return (
        <Dialog
            title={connecting ? "Connect to battle" : "Create a battle"}
            lead={
                connecting
                    ? "Connect this scenario to an existing battle."
                    : "Select a campaign to create a battle using this scenario."
            }
            onDismiss={() => scenarioNavigation.assign(props.cancelUrl)}
            onSubmit={(event) => {
                event.currentTarget.action = props.action;
                event.currentTarget.method = "post";
            }}
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={props.csrfToken}
            />
            {Object.entries(props.rolls).map(([key, value]) => (
                <input key={key} type="hidden" name={key} value={value} />
            ))}
            <FieldErrors errors={props.errors.__all__ ?? []} />
            <Field
                label="Campaign *"
                htmlFor="scenario-campaign"
                errors={props.errors.campaign}
            >
                <NativeSelect
                    name="campaign"
                    required
                    defaultValue={props.campaign}
                    onChange={
                        connecting
                            ? (event) => chooseCampaign(event.target.value)
                            : undefined
                    }
                >
                    <option value="">Select a campaign</option>
                    {props.campaigns.map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.label}
                        </option>
                    ))}
                </NativeSelect>
            </Field>
            {connecting && props.campaign && (
                <>
                    <Field
                        label="Battle *"
                        htmlFor="scenario-battle"
                        errors={props.errors.battle}
                    >
                        <NativeSelect
                            name="battle"
                            required
                            value={battle}
                            onChange={(event) => {
                                setBattle(event.target.value);
                                setRevision(
                                    props.battles.find(
                                        (option) =>
                                            option.value === event.target.value,
                                    )?.revision ?? null,
                                );
                            }}
                        >
                            <option value="">Select a battle</option>
                            {props.battles.map((option) => (
                                <option key={option.value} value={option.value}>
                                    {option.label}
                                </option>
                            ))}
                        </NativeSelect>
                    </Field>
                    <input
                        type="hidden"
                        name="revision"
                        value={revision ?? ""}
                    />
                    <FieldErrors errors={props.errors.revision ?? []} />
                    {props.battles.length === 0 && (
                        <p className="text-sm text-muted">
                            No battles in this campaign yet. Create a battle
                            first.
                        </p>
                    )}
                    {selected?.hasScenario && (
                        <p className="text-sm text-muted">
                            Connecting replaces this battle’s generated
                            scenario.
                        </p>
                    )}
                </>
            )}
            <FormActions>
                <ButtonLink href={props.cancelUrl} variant="ghost">
                    Cancel
                </ButtonLink>
                <Button
                    type="submit"
                    variant="success"
                    disabled={connecting && !selected}
                >
                    {connecting ? "Connect scenario" : "Continue"}
                </Button>
            </FormActions>
        </Dialog>
    );
}
