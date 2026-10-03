import { useEffect, useState } from "react";
import { ActionBar, Button } from "../../ui";

export type ToolbarProps = {
    countOne: string;
    countMany: string;
    plusOne: string;
    plusMany: string;
    minusOne: string;
    minusMany: string;
};
function selection() {
    const form = document.getElementById("post-battle-form");
    const boxes = [
        ...(form?.querySelectorAll<HTMLInputElement>(
            "input[data-xp-participant]",
        ) || []),
    ];
    const chosen = boxes.filter((box) => box.checked);
    const xp = chosen
        .filter((box) => !("xpBlocked" in box.dataset))
        .map((box) => {
            const input = document.getElementById(
                box.dataset.xpParticipant!,
            ) as HTMLInputElement | null;
            const number = Number(input?.value || 0);
            return Number.isInteger(number) ? number : 1;
        });
    return {
        total: boxes.length,
        selected: chosen.length,
        minusDisabled: xp.every((value) => value <= 0),
        plusDisabled: !xp.length,
    };
}
export function PostBattleToolbar(props: ToolbarProps) {
    const [state, setState] = useState(selection);
    useEffect(() => {
        const form = document.getElementById("post-battle-form");
        const update = () => setState(selection());
        form?.addEventListener("input", update);
        form?.addEventListener("post-battle:fields-corrected", update);
        form?.addEventListener("htmx:afterSwap", update);
        return () => {
            form?.removeEventListener("input", update);
            form?.removeEventListener("post-battle:fields-corrected", update);
            form?.removeEventListener("htmx:afterSwap", update);
        };
    }, []);
    const label = (one: string, many: string) =>
        (state.selected === 1 ? one : many).replace(
            "{n}",
            String(state.selected),
        );
    const act = (intent: string) =>
        document.getElementById("post-battle-form")?.dispatchEvent(
            new CustomEvent("post-battle:bulk-action", {
                detail: { intent },
            }),
        );
    return (
        <ActionBar
            className="border border-box-border bg-ink-100 p-3 dark:bg-ink-900"
            data-xp-toolbar
        >
            <p
                className="mr-auto w-full text-sm font-semibold sm:w-auto"
                role="status"
                aria-live="polite"
            >
                {label(props.countOne, props.countMany)}
            </p>
            <Button
                disabled={!state.total || state.selected === state.total}
                onClick={() => act("attend-all")}
            >
                Mark all attended
            </Button>
            <Button
                disabled={state.minusDisabled}
                aria-label={label(props.minusOne, props.minusMany)}
                onClick={() => act("xp-step:-1")}
            >
                −1 XP
            </Button>
            <Button
                disabled={state.plusDisabled}
                aria-label={label(props.plusOne, props.plusMany)}
                onClick={() => act("xp-step:+1")}
            >
                +1 XP
            </Button>
        </ActionBar>
    );
}
