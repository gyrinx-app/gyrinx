// Cotton supplies the alert so recovery does not depend on a working React bundle.
export function showIslandError(host, target, retry, kind = "load") {
    const source = document.getElementById(
        host.dataset.reactError || "n26-react-error",
    );
    const content = source?.content.cloneNode(true);
    const message = {
        load: "Gyrinx could not load this section. Check your connection and try again.",
        render: "This section stopped working. Try again, or reload the page if the problem continues.",
        reload: "This section still could not load. Check your connection, then reload the page.",
    }[kind];
    if (!content) {
        const alert = document.createElement("p");
        alert.setAttribute("role", "alert");
        alert.textContent = message;
        target.replaceChildren(alert);
        return;
    }
    content.querySelector("[data-react-error-message]").textContent = message;
    content.querySelector("[data-react-reload]").href = window.location.href;
    const button = content.querySelector("[data-react-retry]");
    if (kind === "reload") {
        // A failed shared dependency can remain cached after retrying the entry.
        button.remove();
    } else {
        button.addEventListener("click", () => {
            if (button.disabled || !host.isConnected) return;
            button.disabled = true;
            button.dataset.busy = "on";
            button.dataset.busyDisabled = "";
            button.setAttribute("aria-busy", "true");
            retry();
        });
    }
    target.replaceChildren(content);
}
