import { useEffect, useRef, useState } from "react";
import { QUERY_CHANGE } from "../runtime/useQueryHref";

type Picks = { picks: Record<string, string>; sidePicks: string[] };

function normalise(pick: string) {
    if (pick === "roll") return "general";
    return /^[1-6]$/.test(pick) ? `general-${pick}` : pick;
}

export function useScenarioPicks({
    tableKeys,
    sideJobKeys,
    limit,
    initialSidePicks,
}: {
    tableKeys: string[];
    sideJobKeys: string[];
    limit: number;
    initialSidePicks: string[];
}) {
    function read(): Picks {
        const query = new URLSearchParams(window.location.search);
        const explicit =
            query.has("side_jobs") ||
            sideJobKeys.some(
                (key) => query.has(`${key}_pick`) || query.has(`${key}_set`),
            );
        const count = Math.min(
            limit,
            Math.max(
                1,
                Number.parseInt(query.get("side_jobs") ?? "1", 10) || 1,
            ),
        );
        return {
            picks: Object.fromEntries(
                tableKeys.map((key) => [
                    key,
                    query.get(`${key}_pick`) || "roll",
                ]),
            ),
            sidePicks: explicit
                ? sideJobKeys.slice(0, count).map((key) => {
                      const pick = normalise(query.get(`${key}_pick`) ?? "");
                      const set = query.get(`${key}_set`);
                      return set !== null &&
                          !(pick === set || (set && pick.startsWith(`${set}-`)))
                          ? set
                          : pick;
                  })
                : initialSidePicks,
        };
    }
    const [state, setState] = useState(read);
    const current = useRef(state);
    current.current = state;
    useEffect(() => {
        const restore = () => {
            current.current = read();
            setState(current.current);
        };
        window.addEventListener("popstate", restore);
        return () => window.removeEventListener("popstate", restore);
    });
    function commit(patch: Partial<Picks>) {
        const next = { ...current.current, ...patch };
        current.current = next;
        setState(next);
        const url = new URL(window.location.href);
        for (const key of tableKeys) {
            url.searchParams.delete(`${key}_pick`);
            if (next.picks[key] !== "roll")
                url.searchParams.set(`${key}_pick`, next.picks[key]);
        }
        for (const key of sideJobKeys) {
            url.searchParams.delete(`${key}_pick`);
            url.searchParams.delete(`${key}_set`);
        }
        next.sidePicks.forEach((pick, index) => {
            if (pick) url.searchParams.set(`${sideJobKeys[index]}_pick`, pick);
        });
        url.searchParams.set("side_jobs", String(next.sidePicks.length));
        if (url.href !== window.location.href) {
            window.history.pushState(
                window.history.state,
                "",
                url.pathname + url.search + url.hash,
            );
            window.dispatchEvent(new Event(QUERY_CHANGE));
        }
    }
    return {
        ...state,
        setPicks: (picks: Record<string, string>) => commit({ picks }),
        setSidePicks: (sidePicks: string[]) => commit({ sidePicks }),
    };
}
