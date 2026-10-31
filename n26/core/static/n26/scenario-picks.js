// The scenario generator's side job menus: picking a set, or Change set,
// redraws the menu, so the form goes to the server through its hidden
// Update button. Without this script, Generate rolls on the set picked.
document.addEventListener("change", (event) => {
    const menu = event.target;
    if (!(menu instanceof HTMLSelectElement)) return;
    if (!menu.hasAttribute("data-scenario-menu")) return;
    if (!menu.selectedOptions[0]?.hasAttribute("data-switch")) return;
    const update = menu.form?.querySelector("[data-scenario-update]");
    if (update) menu.form.requestSubmit(update);
});
