export type RollChoiceOption = {
    value: string;
    label: string;
    /** Set when the next roll for this option reuses an earlier die. */
    carried: string;
};

export type RollChoices = {
    legend: string;
    name: string;
    value: string;
    errors: string[];
    options: RollChoiceOption[];
};

export type AdvancementRollProps = {
    dice: string;
    minimum: number;
    maximum: number;
    totalLabel: string;
    totalHelp: string;
    mode: string;
    rolled: string;
    modeErrors: string[];
    rolledErrors: string[];
    previousRoll: number | null;
    choices: RollChoices | null;
};
