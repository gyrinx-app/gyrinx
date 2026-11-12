import cotton from "../generated/cotton.json";

/** The Cotton colour palette with native radio selection. */
export function ColourPicker({
    name,
    label,
    colours,
    value,
    onChange,
}: {
    name: string;
    label: string;
    colours: string[];
    value: string;
    onChange: (value: string) => void;
}) {
    const recipe = cotton.colourPicker;
    return (
        <fieldset>
            <legend className={recipe.legend}>{label}</legend>
            <div className={recipe.grid}>
                {["", ...colours].map((colour) => (
                    <label
                        key={colour}
                        className={recipe.label}
                        title={colour || "Default"}
                    >
                        <input
                            className={recipe.input}
                            type="radio"
                            name={name}
                            value={colour}
                            checked={value === colour}
                            onChange={() => onChange(colour)}
                        />
                        <span
                            className={colour ? recipe.swatch : recipe.none}
                            style={
                                colour
                                    ? {
                                          backgroundColor: `var(--color-${colour}-500)`,
                                      }
                                    : undefined
                            }
                        />
                        <span className={recipe.text}>
                            {colour
                                ? colour[0].toUpperCase() + colour.slice(1)
                                : "Default"}
                        </span>
                    </label>
                ))}
            </div>
        </fieldset>
    );
}
