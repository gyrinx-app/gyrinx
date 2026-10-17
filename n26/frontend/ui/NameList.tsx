import cotton from "../generated/cotton.json";

export type CountedName = { name: string; count: number; text: string };

export function NameList({
    names,
    label,
}: {
    names: CountedName[];
    label: string;
}) {
    const recipe = cotton.nameList;
    return (
        <ul role="list" aria-label={label} className={recipe.root}>
            {names.map((name, index) => (
                <li key={index} className={recipe.item}>
                    <span aria-hidden="true" className={recipe.separator}>
                        ·
                    </span>
                    <span className={recipe.text}>{name.text}</span>
                </li>
            ))}
        </ul>
    );
}
