import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type MouseEvent,
} from "react";
import type { ScheduleProps } from "./types";
import type { AlertTone } from "../../ui";

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

function pageEditor(data: ScheduleProps) {
    return data.editor?.kind === "setup" || data.editor?.kind === "plan";
}

export function useScheduleNavigation(initial: ScheduleProps) {
    const [data, setData] = useState(initial);
    const [pending, setPending] = useState(false);
    const [pageNavigation, setPageNavigation] = useState(0);
    const page = useRef(pageEditor(initial));
    const [busyControl, setBusyControl] = useState<string | null>(null);
    const interaction = useRef<string | null>(null);
    const [error, setError] = useState("");
    const [notices, setNotices] = useState(() => readNotices(initial.notices));
    const controller = useRef<AbortController | null>(null);
    const guarded = useRef(false);
    const scope = useRef(crypto.randomUUID());
    const index = useRef(0);
    const current = useRef(window.location.href);
    const retryTarget = useRef(window.location.href);

    const inSchedule = useCallback(
        (url: URL) =>
            url.origin === window.location.origin &&
            url.pathname.startsWith(initial.scheduleHref),
        [initial.scheduleHref],
    );
    const load = useCallback(
        async (href: string, history: "push" | "none" = "push") => {
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
                    window.history.replaceState(
                        { ...window.history.state, htmx: false },
                        "",
                        window.location.href,
                    );
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
            };
            if (localStep) {
                controller.current?.abort();
                controller.current = null;
                setPending(false);
                setBusyControl(null);
                interaction.current = null;
                setError("");
                remember();
                if (history === "push")
                    setPageNavigation((navigation) => navigation + 1);
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
                const movesPage =
                    history === "push" &&
                    url.href !== previous.href &&
                    (pageEditor(result.schedule) ||
                        (page.current && result.schedule.editor === null));
                remember();
                page.current = pageEditor(result.schedule);
                setData(result.schedule);
                if (movesPage)
                    setPageNavigation((navigation) => navigation + 1);
                setNotices(
                    readNotices("notices" in result ? result.notices : []),
                );
            } catch {
                if (controller.current === request && !request.signal.aborted)
                    setError(
                        "The schedule could not be loaded. Check your connection and access, then try again.",
                    );
            } finally {
                if (controller.current === request) {
                    setPending(false);
                    setBusyControl(null);
                }
            }
        },
        [inSchedule, initial.onNavigate],
    );

    useEffect(() => {
        if (!pageNavigation) return;
        // Wait for the destination and its focus effects before moving the viewport.
        const frame = window.requestAnimationFrame(() =>
            window.scrollTo({ left: 0, top: 0, behavior: "instant" }),
        );
        return () => window.cancelAnimationFrame(frame);
    }, [pageNavigation]);

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
            const previous = new URL(current.current);
            const next = new URL(window.location.href);
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
                return;
            }
            void load(next.href, "none");
        }
        window.addEventListener("popstate", restore);
        return () => {
            window.removeEventListener("popstate", restore);
            controller.current?.abort();
        };
    }, [load]);

    useEffect(() => {
        document.title = `${data.editor?.kind === "plan" || data.editor?.kind === "setup" ? data.editor.heading : "Phases & cycles"} — ${data.campaignName} | Gyrinx`;
        const target =
            window.location.hash.slice(1) ||
            (data.focusId ? `cycle-${data.focusId}` : "");
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
        if (!guarded.current) void load(url.href);
    }
    const setGuard = useCallback((value: boolean) => {
        guarded.current = value;
    }, []);
    return {
        data,
        pending,
        busyControl,
        error,
        notices,
        onClick,
        setGuard,
        navigate: useCallback(
            (url: string) => {
                void load(url);
            },
            [load],
        ),
        reload: useCallback(() => {
            void load(window.location.href, "none");
        }, [load]),
        retry: useCallback(() => {
            void load(retryTarget.current);
        }, [load]),
    };
}
