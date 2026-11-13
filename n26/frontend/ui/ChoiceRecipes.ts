import cotton from "../generated/cotton.json";

type ReadonlyRecipe<T> = T extends (infer Item)[]
    ? readonly ReadonlyRecipe<Item>[]
    : T extends object
      ? { readonly [Key in keyof T]: ReadonlyRecipe<T[Key]> }
      : T;

/** Static Cotton presentation; workflow behaviour belongs to each island. */
export const choiceRecipes: ReadonlyRecipe<typeof cotton.choice> =
    cotton.choice;
export type ChoiceRecipes = typeof choiceRecipes;
