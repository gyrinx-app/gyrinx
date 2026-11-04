import { useEffect, useState } from "react";

export const QUERY_CHANGE = "n26:query-change";

export function useQueryHref(href: string, keys: string[] = []) {
    const [search, setSearch] = useState(window.location.search);
    const signature = keys.join("\0");
    useEffect(() => {
        if (!signature) return;
        const update = () => setSearch(window.location.search);
        window.addEventListener("popstate", update);
        window.addEventListener(QUERY_CHANGE, update);
        return () => {
            window.removeEventListener("popstate", update);
            window.removeEventListener(QUERY_CHANGE, update);
        };
    }, [signature]);
    if (!keys.length) return href;
    const url = new URL(href, window.location.href);
    if (url.origin !== window.location.origin) return href;
    const current = new URLSearchParams(search);
    for (const key of keys) {
        url.searchParams.delete(key);
        for (const value of current.getAll(key))
            url.searchParams.append(key, value);
    }
    return url.pathname + url.search + url.hash;
}
