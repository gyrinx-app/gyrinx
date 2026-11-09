import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type MouseEvent,
} from "react";
import type { ScheduleProps } from "./types";

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

export function useScheduleNavigation(initial: ScheduleProps) {
    const [data, setData] = useState(initial);
    const [pending, setPending] = useState(false);
    const [busyControl, setBusyControl] = useState<string | null>(null);
    const interaction = useRef<string | null>(null);
    const [error, setError] = useState("");
    const [notices, setNotices] = useState<string[]>([]);
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
                setData(result.schedule);
                setNotices(
                    "notices" in result && Array.isArray(result.notices)
                        ? result.notices.filter(
                              (notice): notice is string =>
                                  typeof notice === "string",
                          )
                        : [],
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
        document.title = `${data.editor?.kind === "plan" ? "Schedule settings" : "Campaign cycles"} — ${data.campaignName} | Gyrinx`;
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
