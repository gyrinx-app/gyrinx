import cotton from "./cotton.json";

// Resolve Gyrinx's generated palette through the active N26 theme. Canvas
// converts its colour syntax to portable sRGB values for stored text styles.
export function themeColours(element) {
    const theme = getComputedStyle(element);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const context = canvas.getContext("2d");
    return cotton.colours.map(({ name, token }) => {
        const colour = theme.getPropertyValue(token).trim();
        if (!colour || !CSS.supports("color", colour))
            throw Error(`Missing N26 colour token: ${token}`);
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = colour;
        context.fillRect(0, 0, 1, 1);
        const value =
            "#" +
            [...context.getImageData(0, 0, 1, 1).data]
                .slice(0, 3)
                .map((channel) => channel.toString(16).padStart(2, "0"))
                .join("");
        return [name, value];
    });
}
