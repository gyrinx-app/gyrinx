import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type MouseEvent,
} from "react";
import { isPageEditor, type ScheduleProps, type DropIntent } from "./types";
import type { AlertTone } from "../../ui";
import type { PreparedMove } from "./InlineMove";
import { clearMove, moveRecoveryKey, restoreMove } from "./moveRecovery";

function readNotices(value: unknown) {
    if (!Array.isArray(value)) return [];
    return value.flatMap((notice) => {
        const message =
            typeof notice === "string"
                ? notice
                : notice && typeof notice.message === "string"
                  ? notice.message
                  : null;
        if (message === null) return [];
        const tone: AlertTone =
            typeof notice === "string"
                ? "success"
                : ((["success", "warning", "error", "info"] as const).find(
                      (tone) => tone === notice.tone,
                  ) ?? "info");
        return [{ id: crypto.randomUUID(), message, tone }];
    });
}

function scheduleData(value: unknown): value is ScheduleProps {
    if (!value || typeof value !== "object") return false;
    const data = value as Record<string, unknown>;
    return (
        typeof data.configured === "boolean" &&
        typeof data.scheduleHref === "string" &&
        Array.isArray(data.rows) &&
        Array.isArray(data.phases) &&
        !!data.actions &&
        typeof data.actions === "object" &&
        (data.editor === null ||
            (!!data.editor &&
                typeof data.editor === "object" &&
                "values" in data.editor &&
                "recoveryKey" in data.editor))
    );
}

function moveSource(source: string) {
    return Array.from(
        document.querySelectorAll<HTMLElement>("[data-reorder-source]"),
    ).find((node) => node.dataset.reorderSource === source);
}

function moveHandle(source: string) {
    const row = moveSource(source);
    return Array.from(
        row?.querySelectorAll<HTMLButtonElement>(
            "button[aria-label^='Move ']",
        ) ?? [],
    ).find((button) => button.closest("[data-reorder-source]") === row);
}

function revealMovedSource(source: string) {
    const row = moveSource(source);
    const label = row?.getAttribute("aria-labelledby");
    const heading = label ? document.getElementById(label) : null;
    const target = moveHandle(source) ?? heading ?? row;
    (heading ?? row)?.scrollIntoView({ block: "nearest" });
    target?.focus({ preventScroll: true });
}

type ScrollPosition = { left: number; top: number };

function viewport(): ScrollPosition {
    return { left: window.scrollX, top: window.scrollY };
}

function savedScroll(value: unknown): ScrollPosition | undefined {
    if (!value || typeof value !== "object") return;
    const point = value as ScrollPosition;
    if (Number.isFinite(point.left) && Number.isFinite(point.top))
        return { left: point.left, top: point.top };
}

function pageEditor(data: ScheduleProps) {
    return isPageEditor(data.editor);
}

export function useScheduleNavigation(initial: ScheduleProps) {
    const [data, setData] = useState(initial);
    const [pending, setPending] = useState(false);
    const [move, setMove] = useState<PreparedMove | null>(null);
    const [commandPending, setCommandPending] = useState(false);
    const [recoveringMove, setRecoveringMove] = useState(false);
    const moveControl = useRef<string | null>(null);
    const markerKey = moveRecoveryKey(initial.scheduleHref);
    const [scrollTarget, setScrollTarget] = useState<ScrollPosition | null>(
        null,
    );
    const page = useRef(pageEditor(initial));
    const [busyControl, setBusyControl] = useState<string | null>(null);
    const interaction = useRef<string | null>(null);
    const [error, setError] = useState("");
    const [notices, setNotices] = useState(() => readNotices(initial.notices));
    const controller = useRef<AbortController | null>(null);
    const guarded = useRef(false);
    const scope = useRef(crypto.randomUUID());
    const index = useRef(0);
    const renderedIndex = useRef(0);
    const current = useRef(window.location.href);
    const retryTarget = useRef(window.location.href);
    const retryHistory = useRef<"push" | "none">("push");
    const retryScroll = useRef<ScrollPosition | undefined>(undefined);
    const retryDrop = useRef<DropIntent | undefined>(undefined);
    const focusSource = useRef<string | null>(null);
    const scrollPositions = useRef(new Map<number, ScrollPosition>());

    const inSchedule = useCallback(
        (url: URL) =>
            url.origin === window.location.origin &&
            url.pathname.startsWith(initial.scheduleHref),
        [initial.scheduleHref],
    );
    const load = useCallback(
        async (
            href: string,
            history: "push" | "none" = "push",
            restoreScroll?: ScrollPosition,
            drop?: DropIntent,
        ) => {
            retryDrop.current = drop;
            const url = new URL(href, window.location.href);
            if (!inSchedule(url)) {
                (
                    initial.onNavigate ??
                    ((target) => window.location.assign(target))
                )(href);
                return;
            }
            const previous = new URL(current.current);
            const withoutStep = (value: URL) => {
                const query = new URLSearchParams(value.search);
                query.delete("step");
                return query.toString();
            };
            const localStep =
                url.pathname.endsWith("/edit/setup/") &&
                url.pathname === previous.pathname &&
                url.searchParams.get("step") !==
                    previous.searchParams.get("step") &&
                withoutStep(url) === withoutStep(previous);
            const remember = () => {
                if (history === "push" && url.href !== window.location.href) {
                    if (renderedIndex.current === index.current) {
                        const scroll = viewport();
                        scrollPositions.current.set(index.current, scroll);
                        window.history.replaceState(
                            {
                                ...window.history.state,
                                htmx: false,
                                n26Schedule: {
                                    scope: scope.current,
                                    index: index.current,
                                    scroll,
                                },
                            },
                            "",
                            window.location.href,
                        );
                    }
                    window.history.pushState(
                        {
                            ...window.history.state,
                            htmx: false,
                            n26Schedule: {
                                scope: scope.current,
                                index: ++index.current,
                            },
                        },
                        "",
                        url.pathname + url.search + url.hash,
                    );
                }
                current.current = url.href;
                renderedIndex.current = index.current;
            };
            if (localStep) {
                controller.current?.abort();
                controller.current = null;
                setPending(false);
                setBusyControl(null);
                interaction.current = null;
                setError("");
                remember();
                if (restoreScroll) setScrollTarget({ ...restoreScroll });
                else if (history === "push")
                    setScrollTarget({ left: 0, top: 0 });
                const step = Number(url.searchParams.get("step") ?? "1");
                setData((data) =>
                    data.editor?.kind === "setup"
                        ? {
                              ...data,
                              editor: {
                                  ...data.editor,
                                  context: {
                                      ...data.editor.context,
                                      setupStage: [1, 2, 3].includes(step)
                                          ? step
                                          : 1,
                                  },
                              },
                          }
                        : data,
                );
                return;
            }
            controller.current?.abort();
            const request = new AbortController();
            controller.current = request;
            retryTarget.current = url.href;
            retryHistory.current = history;
            retryScroll.current = restoreScroll;
            setPending(true);
            setBusyControl(interaction.current);
            interaction.current = null;
            setError("");
            try {
                const response = await fetch(url.pathname + url.search, {
                    credentials: "same-origin",
                    redirect: "error",
                    signal: request.signal,
                    headers: { Accept: "application/json" },
                });
                if (
                    !response.ok ||
                    !response.headers
                        .get("Content-Type")
                        ?.includes("application/json")
                )
                    throw new Error();
                const result: unknown = await response.json();
                if (
                    !result ||
                    typeof result !== "object" ||
                    !("schedule" in result) ||
                    !scheduleData(result.schedule)
                )
                    throw new Error();
                if (controller.current !== request) return;
                if (drop) {
                    const editor = result.schedule.editor;
                    if (
                        editor?.kind !==
                        (drop.sourceId.startsWith("phase:")
                            ? "move-phase"
                            : "move-cycle")
                    )
                        throw new Error();
                    if (
                        drop.recoveryKey &&
                        drop.recoveryKey !== editor.recoveryKey
                    ) {
                        clearMove(markerKey);
                        guarded.current = false;
                        setRecoveringMove(false);
                        retryDrop.current = undefined;
                        return;
                    }
                    retryDrop.current = undefined;
                    setMove({
                        editor,
                        intent: drop,
                        href: url.pathname + url.search,
                    });
                    setRecoveringMove(false);
                    return;
                }
                const movesPage =
                    history === "push" &&
                    url.href !== previous.href &&
                    (pageEditor(result.schedule) ||
                        (page.current && result.schedule.editor === null));
                remember();
                page.current = pageEditor(result.schedule);
                const prepared = result.schedule;
                retryDrop.current = undefined;
                setData(prepared);
                if (restoreScroll) setScrollTarget({ ...restoreScroll });
                else if (movesPage) setScrollTarget({ left: 0, top: 0 });
                setNotices(
                    readNotices("notices" in result ? result.notices : []),
                );
            } catch {
                if (controller.current === request && !request.signal.aborted)
                    setError(
                        drop?.recoveryKey
                            ? "The earlier move is still unconfirmed. Retry loading the schedule before making another change."
                            : "The schedule could not be loaded. Check your connection and access, then try again.",
                    );
            } finally {
                if (controller.current === request) {
                    setPending(false);
                    setBusyControl(null);
                }
            }
        },
        [inSchedule, initial.onNavigate, markerKey],
    );

    useEffect(() => {
        if (!initial.canManage || initial.editor) return;
        const retained = restoreMove(markerKey);
        if (retained) {
            try {
                if (!inSchedule(new URL(retained.href, window.location.href))) {
                    clearMove(markerKey);
                    return;
                }
            } catch {
                clearMove(markerKey);
                return;
            }
            guarded.current = true;
            setRecoveringMove(true);
            focusSource.current = retained.sourceId;
            moveControl.current =
                moveHandle(retained.sourceId)?.dataset.busyId ?? null;
            void load(retained.href, "none", undefined, retained);
        }
    }, [load, markerKey, inSchedule, initial.canManage, initial.editor]);

    useEffect(() => {
        if (!recoveringMove) return;
        const warn = (event: BeforeUnloadEvent) => {
            event.preventDefault();
            event.returnValue = true;
        };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [recoveringMove]);

    useEffect(() => {
        if (!scrollTarget) return;
        // Native history restoration can clamp against the previous, shorter page.
        const frame = window.requestAnimationFrame(() =>
            window.scrollTo({ ...scrollTarget, behavior: "instant" }),
        );
        return () => window.cancelAnimationFrame(frame);
    }, [scrollTarget]);

    useEffect(() => {
        window.history.replaceState(
            {
                ...window.history.state,
                htmx: false,
                n26Schedule: { scope: scope.current, index: index.current },
            },
            "",
            window.location.href,
        );
        function restore(event: PopStateEvent) {
            const target = event.state?.n26Schedule;
            if (guarded.current) {
                const distance =
                    target?.scope === scope.current
                        ? index.current - target.index
                        : 0;
                if (distance) window.history.go(distance);
                else
                    window.history.replaceState(
                        window.history.state,
                        "",
                        current.current,
                    );
                return;
            }
            retryDrop.current = undefined;
            setMove(null);
            clearMove(markerKey);
            focusSource.current = null;
            const previous = new URL(current.current);
            const next = new URL(window.location.href);
            const ownEntry = target?.scope === scope.current;
            const restoringEntry = ownEntry && target.index !== index.current;
            if (renderedIndex.current === index.current)
                scrollPositions.current.set(index.current, viewport());
            const restoreScroll = restoringEntry
                ? (scrollPositions.current.get(target.index) ??
                  savedScroll(target.scroll))
                : undefined;
            index.current =
                target?.scope === scope.current ? target.index : index.current;
            controller.current?.abort();
            controller.current = null;
            setPending(false);
            setBusyControl(null);
            interaction.current = null;
            setError("");
            retryTarget.current = next.href;
            if (
                previous.pathname === next.pathname &&
                previous.search === next.search
            ) {
                current.current = next.href;
                renderedIndex.current = index.current;
                if (restoreScroll) setScrollTarget({ ...restoreScroll });
                return;
            }
            void load(next.href, "none", restoreScroll);
        }
        window.addEventListener("popstate", restore);
        return () => {
            window.removeEventListener("popstate", restore);
            controller.current?.abort();
        };
    }, [load]);

    useEffect(() => {
        document.title = `${isPageEditor(data.editor) ? data.editor.heading : "Phases & cycles"} — ${data.campaignName} | Gyrinx`;
        const target =
            window.location.hash.slice(1) ||
            (data.focusId ? `cycle-${data.focusId}` : "");
        if (!data.editor && focusSource.current) {
            const source = focusSource.current;
            focusSource.current = null;
            const frame = window.requestAnimationFrame(() => {
                revealMovedSource(source);
            });
            return () => window.cancelAnimationFrame(frame);
        }
        if (!data.editor && target) {
            try {
                document
                    .getElementById(decodeURIComponent(target))
                    ?.scrollIntoView?.({ block: "nearest" });
            } catch {
                /* A malformed fragment cannot select a cycle. */
            }
        }
    }, [data]);

    function onClick(event: MouseEvent<HTMLElement>) {
        if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        )
            return;
        interaction.current =
            (event.target as Element).closest<HTMLElement>("[data-busy-id]")
                ?.dataset.busyId ?? null;
        const link = (event.target as Element).closest("a[href]");
        if (
            !(link instanceof HTMLAnchorElement) ||
            link.target ||
            link.hasAttribute("download") ||
            link.getAttribute("href")?.startsWith("#")
        )
            return;
        const url = new URL(link.href);
        if (!inSchedule(url)) return;
        event.preventDefault();
        if (!guarded.current) {
            setMove(null);
            clearMove(markerKey);
            focusSource.current = null;
            void load(url.href);
        }
    }
    const setGuard = useCallback((value: boolean) => {
        guarded.current = value;
    }, []);
    return {
        data,
        pending: pending || commandPending,
        busyControl:
            busyControl ?? (commandPending ? moveControl.current : null),
        move,
        recoveringMove,
        markerKey,
        setCommandPending,
        completeMove: (url: string) => {
            setMove(null);
            guarded.current = false;
            void load(url);
        },
        dismissMove: (refresh: boolean) => {
            const source = move?.intent.sourceId;
            setMove(null);
            if (source && !refresh)
                requestAnimationFrame(() =>
                    moveHandle(source)?.focus({ preventScroll: true }),
                );
            guarded.current = false;
            if (refresh) void load(window.location.href, "none");
        },
        error,
        notices,
        onClick,
        setGuard,
        prepareMove: (itemId: string, targetId: string) => {
            if (
                pending ||
                commandPending ||
                move ||
                data.editor ||
                guarded.current ||
                !data.canManage
            )
                return;
            const source = data.reorder?.sources.find(
                (item) => item.id === itemId,
            );
            const target = data.reorder?.targets.find(
                (item) => item.id === targetId,
            );
            if (!source || !target || !source.targets.includes(targetId))
                return;
            focusSource.current = source.id;
            interaction.current = moveHandle(source.id)?.dataset.busyId ?? null;
            moveControl.current = interaction.current;
            void load(source.moveHref, "none", undefined, {
                sourceId: source.id,
                revision: data.reorder!.revision,
                destination:
                    target.kind === "phase"
                        ? { after_occurrence_id: target.afterId ?? "" }
                        : {
                              occurrence_id: target.occurrenceId!,
                              after_cycle_id: target.afterId ?? "",
                          },
            });
        },
        navigate: useCallback(
            (url: string) => {
                void load(url);
            },
            [load],
        ),
        reload: useCallback(() => {
            focusSource.current = null;
            void load(window.location.href, "none");
        }, [load]),
        retry: useCallback(() => {
            void load(
                retryTarget.current,
                retryHistory.current,
                retryScroll.current,
                retryDrop.current,
            );
        }, [load]),
    };
}
