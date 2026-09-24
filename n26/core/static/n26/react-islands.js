// Django owns each host. React owns only the host's children.
const islands = new Map();

export function mountWithin(scope, loadModule = (url) => import(url)) {
    const hosts = [...scope.querySelectorAll("[data-react-module]")];
    if (scope.matches?.("[data-react-module]")) hosts.unshift(scope);
    for (const host of hosts) {
        if (islands.has(host)) continue;
        const pending = { dispose: null };
        islands.set(host, pending);
        loadModule(host.dataset.reactModule)
            .then((module) => {
                if (!host.isConnected || islands.get(host) !== pending) return;
                const data = document.getElementById(host.dataset.reactProps);
                pending.dispose = module.mount(
                    host,
                    JSON.parse(data.textContent),
                );
            })
            .catch((error) => {
                if (!host.isConnected || islands.get(host) !== pending) return;
                if (host.hasAttribute("data-react-fallback")) {
                    console.error("React island failed to load", error);
                    return;
                }
                host.replaceChildren();
                const message = document.createElement("p");
                message.setAttribute("role", "alert");
                message.textContent = "This section could not load. ";
                const retry = document.createElement("a");
                retry.href = window.location.href;
                retry.className = "underline";
                retry.textContent = "Reload the page";
                message.append(retry, ".");
                host.append(message);
                console.error("React island failed to load", error);
            });
    }
}

document.addEventListener("htmx:load", (event) =>
    mountWithin(event.detail.elt),
);
document.addEventListener("htmx:beforeCleanupElement", (event) => {
    for (const [host, mounted] of islands) {
        if (event.detail.elt === host || event.detail.elt.contains(host)) {
            islands.delete(host);
            mounted.dispose?.();
        }
    }
});
mountWithin(document);
