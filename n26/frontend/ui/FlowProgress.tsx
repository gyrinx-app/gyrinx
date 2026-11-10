import cotton from "../generated/cotton.json";
import { Icon } from "./index";

export type FlowStep = {
    label: string;
    current?: boolean;
    complete?: boolean;
    skipped?: boolean;
    href?: string;
};

/** The Cotton flow-progress pattern, with navigation owned by its workflow. */
export function FlowProgress({
    steps,
    label = "Progress",
    className = "",
}: {
    steps: FlowStep[];
    label?: string;
    className?: string;
}) {
    const recipe = cotton.flowProgress;
    const short = steps.length <= 4;
    return (
        <nav aria-label={label} className={className}>
            <ol className={short ? recipe.shortList : recipe.longList}>
                {steps.map((step, index) => {
                    const state = step.current
                        ? "current"
                        : step.complete
                          ? "complete"
                          : step.skipped
                            ? "skipped"
                            : "future";
                    const style = recipe.states[state];
                    return (
                        <li
                            key={index}
                            className={
                                short ? recipe.shortItem : recipe.longItem
                            }
                            aria-current={step.current ? "step" : undefined}
                        >
                            <span className={style.circle}>
                                {step.complete ? (
                                    <Icon
                                        name="check"
                                        className="size-4"
                                        label="Completed"
                                    />
                                ) : (
                                    index + 1
                                )}
                            </span>
                            {step.skipped ? (
                                <span className={style.label}>
                                    {step.label}
                                    <span className="sr-only"> (skipped)</span>
                                </span>
                            ) : step.href ? (
                                <a href={step.href} className={style.link}>
                                    {step.label}
                                </a>
                            ) : (
                                <span className={style.label}>
                                    {step.label}
                                </span>
                            )}
                            {short && index < steps.length - 1 && (
                                <span
                                    aria-hidden="true"
                                    className={recipe.separator}
                                />
                            )}
                        </li>
                    );
                })}
            </ol>
        </nav>
    );
}
