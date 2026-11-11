export type Counter = {
    id: string;
    name: string;
    prefix: string;
    listName: string;
    entered: string;
    editable: boolean;
    before: number;
    base: number;
    after: number;
    fromResults: number;
    limit: number;
    minusLabel: string;
    plusLabel: string;
};
export type Option = { value: string; label: string };
export type Effect = {
    id: string;
    selected: string;
    label: string;
    name: string;
    retainedOption: boolean;
    retainedChoices: { key: string; selected: string[] }[];
    questions: {
        key: string;
        label: string;
        multiple: boolean;
        required: boolean;
        selected: string[];
        options: Option[];
    }[];
};
export type ReportModel = {
    id: string;
    name: string;
    prefix: string;
    profileName: string;
    ownedBy: string;
    participated: boolean;
    xp: string;
    xpAvailable: boolean;
    xpBefore: number;
    xpHelp: string;
    status: string;
    statusLabel: string;
    statusColour: string;
    statusOptions: Option[];
    statusConflict: string;
    statusChanges: boolean;
    finalStatusLabel: string;
    finalStatusColour: string;
    equipment: string;
    equipmentLabel: string;
    equipmentApplies: boolean;
    equipmentChanged: boolean;
    equipmentDisposition: string;
    equipmentNames: string[];
    equipmentExclusions: string[];
    addEffectLabel: string;
    effectGroups: { label: string; options: Option[] }[];
    effects: Effect[];
    counters: Counter[];
    counterEffects: boolean;
    note: string;
    noteLabel: string;
    noteHelp: string;
    noteLimit: number;
    errors: string[];
};
export type ReportDisplay = {
    reportId: string;
    title: string;
    lead: string;
    breadcrumbs: { label: string; href?: string }[];
    participationConfirmed: boolean;
    applied: boolean;
    correcting: boolean;
    receiptHref: string;
    generation: string;
    revision: number;
    review: string;
    savedAt: string;
    toolbar: {
        countOne: string;
        countMany: string;
        plusOne: string;
        plusMany: string;
        minusOne: string;
        minusMany: string;
    };
    models: ReportModel[];
    mission: {
        creditLines: {
            id: string;
            amount: string;
            reason: string;
            amountErrors: string[];
            reasonErrors: string[];
            removeLabel: string;
        }[];
        canAddLine: boolean;
        totalText: string;
        counters: Counter[];
        counterEffects: boolean;
    };
    territory: null | {
        name: string;
        heading: string;
        outcome: string;
        currentHolder: string;
        applied: boolean;
        note: string;
    };
    preview: {
        rows: { id: string; label: string; value: string }[];
        models: { id: string; name: string; lines: string[]; error: string }[];
    };
    errors: string[];
    showErrors: boolean;
};
export type PostBattleProps = ReportDisplay & {
    action: string;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
    messages: { text: string; level: number }[];
    initialConflict?: boolean;
    currentDisplay?: ReportDisplay;
    submissionKey?: string;
    onNavigate?: (url: string) => void;
    onReload?: () => void;
};

export function fields(display: ReportDisplay): URLSearchParams {
    const body = new URLSearchParams();
    for (const line of display.mission.creditLines) {
        body.append("credit_line", line.id);
        body.set(`credit-${line.id}-amount`, line.amount);
        body.set(`credit-${line.id}-reason`, line.reason);
    }
    for (const counter of display.mission.counters) {
        if (!counter.editable) continue;
        body.append(counter.listName, counter.id);
        body.set(counter.prefix, counter.entered);
    }
    for (const model of display.models) {
        const p = model.prefix;
        body.append("model_id", model.id);
        if (model.participated) body.set(`${p}-participated`, "on");
        for (const [key, value] of Object.entries({
            xp: model.xp,
            status: model.status,
            equipment: model.equipment,
            note: model.note,
        }))
            body.set(`${p}-${key}`, value);
        for (const counter of model.counters) {
            if (!counter.editable) continue;
            body.append(counter.listName, counter.id);
            body.set(counter.prefix, counter.entered);
        }
        for (const effect of model.effects) {
            body.append(`${p}-effect`, effect.id);
            const ep = `effect-${effect.id}`;
            body.set(`${ep}-pick`, effect.selected);
            for (const question of [
                ...effect.retainedChoices,
                ...effect.questions,
            ]) {
                body.append(`${ep}-question`, question.key);
                for (const value of question.selected)
                    body.append(`${ep}-choice-${question.key}`, value);
            }
        }
    }
    if (display.participationConfirmed)
        body.set("participation_confirmed", "on");
    return body;
}

export function value(form: { draft: URLSearchParams }, name: string) {
    return form.draft.get(name) || "";
}
