export type DiceAmount = { count: number; sides: number; multiplier: number };
export type Credits = { fixed: number; dice: DiceAmount | null };
export type Reward = { credits: Credits; reputation: number };
export type Rewards = {
    win: Reward;
    draw: Reward;
    loss: Reward;
    entry_credits: Credits;
};
export type Step = { id: string; phase_id: string; count: number };
export type SetupDefinition = {
    phases: Array<{
        id: string;
        details: {
            name: string;
            description: string;
            effects: string;
            rewards: Rewards;
        };
    }>;
    steps: Step[];
};
export type Phase = {
    id: string;
    phaseId?: string;
    generated?: boolean;
    addCycleHref?: string;
    addPhaseHref?: string;
    moveHref?: string;
    number?: number;
    name: string;
    description: string;
    effects: string;
    rewards: Rewards;
    count: number;
    editHref: string;
    duplicateHref: string;
    deleteHref: string;
};
export type Cycle = {
    key: string;
    name: string;
    order: number;
    phaseId: string;
    occurrenceId?: string;
    editablePreview?: boolean;
    duplicateHref?: string;
    moveHref?: string;
    phaseName: string;
    state: string;
    startsOn: string;
    endsOn: string;
    description: string;
    effects: string;
    editHref: string;
    href: string;
    startedAt: string;
    endedAt: string;
    deleteHref?: string;
};
export type ReorderTarget = {
    id: string;
    label: string;
    kind: "cycle" | "phase";
    occurrenceId: string | null;
    afterId: string | null;
};
export type ScheduleReorder = {
    revision: number;
    sources: Array<{
        id: string;
        label: string;
        origin: string;
        targets: string[];
        moveHref: string;
    }>;
    targets: ReorderTarget[];
};
export type DropIntent = {
    sourceId: string;
    revision: number;
    destination: Record<string, string>;
    stale?: boolean;
};
export type Editor = {
    dropIntent?: DropIntent;
    kind: string;
    heading: string;
    lead: string;
    context: Record<string, unknown>;
    values: Record<string, string>;
    errors: Record<string, string[]>;
    initialConflict: boolean;
    current: { revision: number | null; cycle: string; phase: string } | null;
    templates: Array<{
        id: string;
        name: string;
        definition?: SetupDefinition;
    }>;
    action: string;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
    back: string;
};
export interface ScheduleProps {
    reorder?: ScheduleReorder;
    notices?: Array<{
        message: string;
        tone: "success" | "info" | "warning" | "error";
    }>;
    campaignName: string;
    campaignHref: string;
    scheduleHref: string;
    canManage: boolean;
    configured: boolean;
    status: string;
    currentName: string;
    currentPhase: string;
    currentPhaseId: string;
    rows: Cycle[];
    phases: Phase[];
    plan: {
        mode: string;
        steps: Step[];
        phaseNames?: Record<string, string>;
        startsAfter: string;
        nextPosition: number;
    } | null;
    actions: Record<string, string>;
    previousHref: string;
    nextHref: string;
    moreHref: string;
    focusId: string;
    editor: Editor | null;
    onNavigate?: (url: string) => void;
    onReload?: () => void;
}

export function isPhaseEditor(editor: Editor | null) {
    return (
        !!editor &&
        ["phase", "add-phase", "duplicate-phase", "delete-phase"].includes(
            editor.kind,
        )
    );
}

export function isPageEditor(editor: Editor | null): editor is Editor & {
    kind:
        | "plan"
        | "pattern"
        | "setup"
        | "phase"
        | "add-phase"
        | "duplicate-phase"
        | "delete-phase";
} {
    return (
        !!editor &&
        (["setup", "plan", "pattern"].includes(editor.kind) ||
            isPhaseEditor(editor))
    );
}
