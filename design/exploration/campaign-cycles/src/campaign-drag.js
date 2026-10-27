import { useRef, useState } from "react";
import { cycleDropPosition, moveCycle } from "./campaign-model.js";

export function useCampaignDrag(state, change, enabled) {
    const id = useRef(null),
        [dragging, setDragging] = useState(null),
        [hover, setHover] = useState(null);
    function clear() {
        id.current = null;
        setDragging(null);
        setHover(null);
    }
    function targetFromEvent(event, phaseId) {
        const row = event.target.closest?.("[data-cycle-id]");
        let beforeId = null;
        if (row && id.current !== state.currentCycle) {
            if (row.dataset.cycleId === id.current) {
                const at = state.cycles.findIndex((c) => c.id === id.current);
                beforeId =
                    state.cycles.slice(at + 1).find((c) => c.phase === phaseId)
                        ?.id || null;
            } else {
                const rows = state.cycles.filter(
                        (c) => c.phase === phaseId && c.id !== id.current,
                    ),
                    at = rows.findIndex((c) => c.id === row.dataset.cycleId),
                    box = row.getBoundingClientRect();
                beforeId =
                    event.clientY < box.top + box.height / 2
                        ? row.dataset.cycleId
                        : rows[at + 1]?.id || null;
            }
        }
        return {
            phase: phaseId,
            beforeId,
            ...cycleDropPosition(state, id.current, phaseId, beforeId),
        };
    }
    function phaseProps(phaseId) {
        const available =
            dragging && cycleDropPosition(state, dragging, phaseId).valid;
        return {
            className: `cp-schedule-phase ${dragging ? (available ? "cp-drop-available" : "cp-drop-blocked") : ""} ${hover?.phase === phaseId && hover.valid ? "cp-drop-active" : ""}`,
            "data-drop-target": dragging ? "phase" : undefined,
            onDragOver: (event) => {
                if (!enabled || !id.current) return;
                const target = targetFromEvent(event, phaseId);
                event.preventDefault();
                event.dataTransfer.dropEffect = target.valid ? "move" : "none";
                setHover((old) =>
                    old?.phase === target.phase &&
                    old?.beforeId === target.beforeId &&
                    old?.valid === target.valid
                        ? old
                        : target,
                );
            },
            onDragLeave: (event) => {
                if (!event.currentTarget.contains(event.relatedTarget))
                    setHover((old) => (old?.phase === phaseId ? null : old));
            },
            onDrop: (event) => {
                event.preventDefault();
                const target = targetFromEvent(event, phaseId);
                if (enabled && target.valid) {
                    const cycleId = id.current;
                    change(
                        (s) => moveCycle(s, cycleId, phaseId, target.beforeId),
                        "Cycle moved.",
                    );
                }
                clear();
            },
        };
    }
    function cycleProps(cycle) {
        const movable =
            enabled && !state.ended && !state.closedCycles.includes(cycle.id);
        return {
            draggable: movable,
            onDragStart: (event) => {
                id.current = cycle.id;
                setDragging(cycle.id);
                setHover(null);
                event.dataTransfer.setData("text/plain", cycle.id);
                event.dataTransfer.effectAllowed = "move";
            },
            onDragEnd: clear,
        };
    }
    return { dragging, hover, phaseProps, cycleProps };
}
