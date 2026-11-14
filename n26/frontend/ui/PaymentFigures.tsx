import cotton from "../generated/cotton.json";

/** Values are already formatted by the server, including currency and limits. */
export type PaymentFiguresData = {
    label: string;
    available: string;
    price: string;
    remaining: string;
};

export function PaymentFigures({
    figures,
    className = "",
}: {
    figures: PaymentFiguresData;
    className?: string;
}) {
    const recipe = cotton.paymentFigures;
    return (
        <div className={`${recipe.root} ${className}`.trim()}>
            <dl className={recipe.list}>
                {[
                    { label: "Available", value: figures.available },
                    { label: "Price", value: figures.price },
                ].map(({ label, value }) => (
                    <div key={label} className={recipe.figure}>
                        <dt className={recipe.label}>{label}</dt>
                        <dd className={recipe.value}>
                            <span className={recipe.number}>{value}</span>
                            {figures.label && (
                                <span className={recipe.unit}>
                                    {figures.label}
                                </span>
                            )}
                        </dd>
                    </div>
                ))}
            </dl>
        </div>
    );
}
