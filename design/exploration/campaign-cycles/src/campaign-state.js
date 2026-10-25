import { useEffect, useRef, useState } from "react";
import * as M from "./campaign-model.js";

const views = new Set(["dashboard", "schedule", "battles", "activity"]);
export function readRoute(search = location.search) {
    const params = new URLSearchParams(search);
    return {
        tab: views.has(params.get("view")) ? params.get("view") : "dashboard",
        viewer: params.get("viewer") === "player" ? "player" : "arbitrator",
    };
}

export function useCampaignState() {
    const [loaded] = useState(() => {
        try {
            const raw = localStorage.getItem(M.storageKey);
            return {
                state: raw ? M.normalise(JSON.parse(raw)) : M.defaults(),
                blocked: false,
            };
        } catch {
            return { state: M.defaults(), blocked: true };
        }
    });
    const [state, setState] = useState(loaded.state),
        [storageBlocked, setBlocked] = useState(loaded.blocked),
        [persistError, setPersistError] = useState(false);
    const current = useRef(state),
        blocked = useRef(storageBlocked),
        unsaved = useRef(false);
    const transaction = useRef(null);
    transaction.current = async (operation, { reset = false } = {}) => {
        const change = () => {
            let latest = current.current;
            if (!blocked.current && !reset && !unsaved.current) {
                let raw;
                try {
                    raw = localStorage.getItem(M.storageKey);
                } catch {
                    setPersistError(true);
                }
                if (raw) {
                    try {
                        latest = M.normalise(JSON.parse(raw));
                    } catch {
                        blocked.current = true;
                        setBlocked(true);
                        throw new Error(
                            "Saved campaign data changed and could not be read. Reset the demo to replace it.",
                        );
                    }
                }
            }
            const draft = reset ? M.defaults() : structuredClone(latest);
            operation(draft);
            if (reset) {
                blocked.current = false;
                setBlocked(false);
            }
            if (!blocked.current) {
                try {
                    localStorage.setItem(M.storageKey, JSON.stringify(draft));
                    unsaved.current = false;
                    setPersistError(false);
                } catch {
                    unsaved.current = true;
                    setPersistError(true);
                }
            }
            current.current = draft;
            setState(draft);
        };
        // All writes share the lock, including manual edits and automatic catch-up.
        if (navigator.locks)
            return navigator.locks.request(M.storageKey, change);
        return change();
    };
    useEffect(() => {
        // Persist the initial example and migrations through the same write boundary.
        transaction.current(() => {}).catch(() => setPersistError(true));
    }, []);
    useEffect(() => {
        if (
            storageBlocked ||
            !state.autoCycles ||
            state.ended ||
            state.status === "pre_campaign"
        )
            return;
        let checking = false,
            disposed = false;
        async function check() {
            if (
                checking ||
                disposed ||
                Date.parse(current.current.autoCycles?.nextAt) > Date.now()
            )
                return;
            checking = true;
            try {
                await transaction.current((draft) => {
                    if (!disposed) M.runDueCycles(draft);
                });
            } catch {
                if (!disposed) setPersistError(true);
            } finally {
                checking = false;
            }
        }
        const visible = () => {
            if (!document.hidden) check();
        };
        const timer = setTimeout(
            check,
            Math.max(
                0,
                Math.min(
                    2147483647,
                    Date.parse(state.autoCycles.nextAt) - Date.now(),
                ),
            ),
        );
        const interval = setInterval(check, 30000);
        document.addEventListener("visibilitychange", visible);
        check();
        return () => {
            disposed = true;
            clearTimeout(timer);
            clearInterval(interval);
            document.removeEventListener("visibilitychange", visible);
        };
    }, [storageBlocked, state.autoCycles?.nextAt, state.ended, state.status]);
    useEffect(() => {
        if (storageBlocked) return;
        const sync = (event) => {
            if (event.key !== M.storageKey || unsaved.current) return;
            try {
                // Read the latest value: queued events may describe an older write.
                const raw = localStorage.getItem(M.storageKey);
                if (!raw) return;
                const latest = M.normalise(JSON.parse(raw));
                current.current = latest;
                setState(latest);
            } catch {
                setPersistError(true);
            }
        };
        addEventListener("storage", sync);
        return () => removeEventListener("storage", sync);
    }, [storageBlocked]);
    return {
        state,
        update: (operation) => transaction.current(operation),
        storageBlocked,
        persistError,
        reset: () => transaction.current(() => {}, { reset: true }),
    };
}

export function useCampaignNavigation(close) {
    const [route, setRoute] = useState(() => readRoute()),
        closeRef = useRef(close),
        activeUrl = useRef(location.href);
    closeRef.current = close;
    useEffect(() => {
        const pop = () => {
            if (!closeRef.current()) {
                history.pushState({}, "", activeUrl.current);
                return;
            }
            activeUrl.current = location.href;
            setRoute(readRoute());
        };
        addEventListener("popstate", pop);
        return () => removeEventListener("popstate", pop);
    }, []);
    function navigate(tab, viewer = route.viewer) {
        if (!closeRef.current()) return;
        const url = new URL(location.href);
        url.searchParams.set("view", views.has(tab) ? tab : "dashboard");
        url.searchParams.set("viewer", viewer);
        history.pushState({}, "", url);
        activeUrl.current = location.href;
        setRoute(readRoute());
    }
    return { ...route, navigate };
}

export function useCampaignTheme() {
    const [dark, setDark] = useState(() => {
        try {
            return localStorage.getItem("gyrinx-campaign-dark") === "1";
        } catch {
            return false;
        }
    });
    useEffect(() => {
        document.querySelector("#campaign-root").classList.toggle("dark", dark);
        try {
            localStorage.setItem("gyrinx-campaign-dark", dark ? "1" : "0");
        } catch {
            /* Theme still works when storage is unavailable. */
        }
    }, [dark]);
    return [dark, setDark];
}

export function useUnsavedChanges(closeGuard, dirty) {
    useEffect(() => {
        closeGuard.current = () =>
            !dirty ||
            window.confirm(
                "Discard unsaved pattern changes? Your pattern has not been saved.",
            );
        const beforeUnload = (e) => {
            if (dirty) {
                e.preventDefault();
                e.returnValue = "";
            }
        };
        addEventListener("beforeunload", beforeUnload);
        return () => {
            closeGuard.current = null;
            removeEventListener("beforeunload", beforeUnload);
        };
    }, [closeGuard, dirty]);
}
