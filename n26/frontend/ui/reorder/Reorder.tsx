import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useId,
    useRef,
    useState,
    type KeyboardEvent,
    type ReactNode,
} from "react";
import {
    DragDropProvider,
    DragOverlay,
    useDraggable,
    useDroppable,
    type DragDropManager,
} from "@dnd-kit/react";
import {
    Accessibility,
    PointerActivationConstraints,
    PointerSensor,
} from "@dnd-kit/dom";
import { pointerIntersection } from "@dnd-kit/collision";
import { Button, Icon } from "../index";

export type ReorderMove = { itemId: string; targetId: string };
export type ReorderSource = {
    id: string;
    label: string;
    /** Stable insertion boundary before this source, including a no-op boundary. */
    origin: string;
    /** Allowed, non-no-op boundaries. The owner retains all domain rules. */
    targets: string[];
};
export type ReorderDestination = { id: string; label: string };

type Session = {
    itemId: string;
    targetId: string | null;
    keyboard: boolean;
    baseline: string;
};
type ReorderContextValue = {
    sources: ReorderSource[];
    targets: ReorderDestination[];
    disabled: boolean;
    session: Session | null;
    instructions: string;
    handles: Map<string, HTMLButtonElement>;
    eligible: (itemId: string, targetId: string) => boolean;
    start: (itemId: string, keyboard: boolean) => void;
    target: (targetId: string | null) => void;
    finish: (cancel: boolean, restoreFocus?: boolean) => void;
    keyDown: (event: KeyboardEvent, itemId: string) => void;
};
const ReorderContext = createContext<ReorderContextValue | null>(null);
function useReorder() {
    const value = useContext(ReorderContext);
    if (!value) throw new Error("Reorder controls require ReorderScope.");
    return value;
}
const sensors = [
    PointerSensor.configure({
        activationConstraints: [
            new PointerActivationConstraints.Distance({ value: 6 }),
        ],
    }),
];

/** Controlled insertion commands: preview never mutates the owner's order or DOM. */
export function ReorderScope({
    sources,
    targets,
    disabled = false,
    onMove,
    children,
}: {
    sources: ReorderSource[];
    targets: ReorderDestination[];
    disabled?: boolean;
    onMove: (move: ReorderMove) => void;
    children: ReactNode;
}) {
    const [session, setSession] = useState<Session | null>(null);
    const sessionRef = useRef<Session | null>(null);
    const pointerManager = useRef<DragDropManager | null>(null);
    const [announcement, announce] = useState("");
    const instructions = useId();
    const handles = useRef(new Map<string, HTMLButtonElement>());
    const baseline = JSON.stringify([sources, targets]);
    const latest = useRef({ sources, targets, disabled, onMove, baseline });
    latest.current = { sources, targets, disabled, onMove, baseline };
    function update(next: Session | null) {
        sessionRef.current = next;
        setSession(next);
    }
    function eligible(itemId: string, targetId: string) {
        const current = latest.current;
        return (
            !current.disabled &&
            current.targets.some((target) => target.id === targetId) &&
            !!current.sources
                .find((source) => source.id === itemId)
                ?.targets.includes(targetId)
        );
    }
    function start(itemId: string, keyboard: boolean) {
        const source = latest.current.sources.find(
            (source) => source.id === itemId,
        );
        if (latest.current.disabled || !source?.targets.length) return;
        update({
            itemId,
            targetId: null,
            keyboard,
            baseline: latest.current.baseline,
        });
        announce(
            `Moving ${source.label}. Choose a position, then drop. Escape cancels.`,
        );
    }
    function target(targetId: string | null) {
        const current = sessionRef.current;
        if (!current) return;
        const next =
            targetId && eligible(current.itemId, targetId) ? targetId : null;
        if (current.targetId === next) return;
        update({ ...current, targetId: next });
        if (next)
            announce(
                latest.current.targets.find((target) => target.id === next)
                    ?.label ?? "",
            );
    }
    function finish(cancel: boolean, restoreFocus = true) {
        const current = sessionRef.current;
        if (!current) return;
        update(null);
        if (restoreFocus)
            requestAnimationFrame(() =>
                handles.current
                    .get(current.itemId)
                    ?.focus({ preventScroll: true }),
            );
        const source = latest.current.sources.find(
            (source) => source.id === current.itemId,
        );
        if (
            cancel ||
            current.baseline !== latest.current.baseline ||
            !current.targetId ||
            !eligible(current.itemId, current.targetId)
        ) {
            announce(`Move cancelled${source ? ` for ${source.label}` : ""}.`);
            return;
        }
        announce(`Move requested for ${source?.label ?? "selection"}.`);
        latest.current.onMove({
            itemId: current.itemId,
            targetId: current.targetId,
        });
    }
    function keyDown(event: KeyboardEvent, itemId: string) {
        const current = sessionRef.current;
        if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            if (current?.keyboard) finish(false);
            else if (!current) start(itemId, true);
            return;
        }
        if (!current?.keyboard || current.itemId !== itemId) return;
        if (event.key === "Escape" || event.key === "Tab") {
            if (event.key === "Escape") event.preventDefault();
            finish(true, event.key !== "Tab");
            return;
        }
        if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key))
            return;
        event.preventDefault();
        const source = latest.current.sources.find(
            (source) => source.id === itemId,
        );
        const all = latest.current.targets;
        const choices = all.filter((choice) => eligible(itemId, choice.id));
        const position = all.findIndex(
            (choice) => choice.id === (current.targetId ?? source?.origin),
        );
        const choice =
            event.key === "Home"
                ? choices[0]
                : event.key === "End"
                  ? choices.at(-1)
                  : event.key === "ArrowDown"
                    ? choices.find((choice) => all.indexOf(choice) > position)
                    : [...choices]
                          .reverse()
                          .find((choice) => all.indexOf(choice) < position);
        if (choice) {
            target(choice.id);
            // Keep the handle focused while revealing an off-screen insertion boundary.
            document
                .getElementById(`${instructions}-${choice.id}`)
                ?.scrollIntoView({ block: "nearest" });
        }
    }
    useEffect(() => {
        if (
            sessionRef.current &&
            (disabled || sessionRef.current.baseline !== baseline)
        ) {
            const pointer = !sessionRef.current.keyboard;
            finish(true);
            if (pointer)
                pointerManager.current?.actions.stop({ canceled: true });
        }
    }, [disabled, baseline]);
    return (
        <ReorderContext.Provider
            value={{
                sources,
                targets,
                disabled,
                session,
                instructions,
                handles: handles.current,
                eligible,
                start,
                target,
                finish,
                keyDown,
            }}
        >
            <DragDropProvider
                sensors={sensors}
                plugins={(defaults) =>
                    defaults.filter((plugin) => plugin !== Accessibility)
                }
                onBeforeDragStart={(event, manager) => {
                    pointerManager.current = manager;
                    const id = String(event.operation.source?.id ?? "");
                    if (
                        !!sessionRef.current ||
                        latest.current.disabled ||
                        !latest.current.sources.find(
                            (source) => source.id === id,
                        )?.targets.length
                    )
                        event.preventDefault();
                }}
                onDragStart={({ operation }) =>
                    start(String(operation.source?.id), false)
                }
                onDragOver={({ operation }) => {
                    if (
                        !sessionRef.current ||
                        sessionRef.current.keyboard ||
                        sessionRef.current.itemId !==
                            String(operation.source?.id)
                    )
                        return;
                    target(
                        operation.target ? String(operation.target.id) : null,
                    );
                }}
                onDragEnd={(event) => {
                    if (
                        !sessionRef.current ||
                        sessionRef.current.keyboard ||
                        sessionRef.current.itemId !==
                            String(event.operation.source?.id)
                    )
                        return;
                    target(
                        event.operation.target
                            ? String(event.operation.target.id)
                            : null,
                    );
                    finish(event.canceled);
                }}
            >
                <p id={instructions} className="sr-only">
                    Press Space or Enter to move. Use Up and Down to choose a
                    position, then Space or Enter to drop. Escape cancels.
                </p>
                <span
                    className="sr-only"
                    role="status"
                    aria-live="polite"
                    aria-atomic="true"
                >
                    {announcement}
                </span>
                {children}
                <DragOverlay dropAnimation={null}>
                    <div className="w-max max-w-72 wrap-anywhere rounded-box border border-box-border bg-surface p-2 text-sm shadow-lg">
                        {
                            sources.find(
                                (source) => source.id === session?.itemId,
                            )?.label
                        }
                    </div>
                </DragOverlay>
            </DragDropProvider>
        </ReorderContext.Provider>
    );
}

/** Render-prop keeps table rows and phase sections in their owner's valid markup. */
export function ReorderItem({
    id,
    children,
}: {
    id: string;
    children: (props: {
        ref: (element: Element | null) => void;
        handle: ReactNode;
        active: boolean;
    }) => ReactNode;
}) {
    const context = useReorder();
    const source = context.sources.find((source) => source.id === id);
    const disabled = context.disabled || !source?.targets.length;
    const { ref, handleRef } = useDraggable({ id, disabled });
    const active = context.session?.itemId === id;
    const setHandle = useCallback(
        (element: HTMLButtonElement | null) => {
            handleRef(element);
            if (element) context.handles.set(id, element);
            else context.handles.delete(id);
        },
        [handleRef, id, context.handles],
    );
    return children({
        ref,
        active,
        handle:
            source && source.targets.length ? (
                <Button
                    ref={setHandle}
                    size="xs"
                    variant="ghost"
                    className="inline-flex shrink-0 cursor-grab items-center justify-center touch-none size-4! p-0! active:cursor-grabbing"
                    disabled={context.disabled}
                    aria-label={`Move ${source.label}`}
                    aria-describedby={context.instructions}
                    aria-pressed={active}
                    title={`Move ${source.label}`}
                    onKeyDown={(event) => context.keyDown(event, id)}
                    onBlur={() => {
                        if (active && context.session?.keyboard)
                            context.finish(true, false);
                    }}
                >
                    <Icon name="grip-vertical" className="size-3!" />
                </Button>
            ) : null,
    });
}

/** Zero-height insertion boundary; only the active drop line is painted. */
export function ReorderDropLine({
    id,
    align = "center",
}: {
    id: string;
    /** Keep table-edge hit areas inside their scroll container. */
    align?: "start" | "center" | "end";
}) {
    const context = useReorder();
    const allowed =
        !!context.session && context.eligible(context.session.itemId, id);
    const { ref } = useDroppable({
        id,
        disabled: !allowed,
        collisionDetector: pointerIntersection,
    });
    const active = allowed && context.session?.targetId === id;
    return (
        <div className="relative h-0" aria-hidden="true">
            <div
                ref={ref}
                id={`${context.instructions}-${id}`}
                data-reorder-target={id}
                data-reorder-active={active || undefined}
                className={`absolute inset-x-0 z-10 flex h-6 ${align === "start" ? "top-0 items-start" : align === "end" ? "-top-6 items-end" : "-top-3 items-center"} ${allowed ? "" : "pointer-events-none"}`}
            >
                {active && (
                    <span
                        data-reorder-indicator
                        className="w-full border-t-2 border-accent"
                    />
                )}
            </div>
        </div>
    );
}
