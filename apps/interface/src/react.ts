// Fabrique JSX et crochets pris sur le React DU TABLEAU DE BORD (SDK.React) : les greffons
// n'embarquent aucun React. Les composants sont rendus par l'arbre React de Hermes, les crochets
// doivent donc venir de la même instance.
import type * as ReactTypes from "react";
import { sdk } from "./sdk";

function react(): typeof ReactTypes {
  const r = sdk().React;
  if (!r) throw new Error("React absent du SDK du tableau de bord");
  return r;
}

export function h(type: unknown, props: unknown, ...enfants: unknown[]): ReactTypes.ReactElement {
  const createElement = react().createElement as (...a: unknown[]) => ReactTypes.ReactElement;
  return createElement(type, props, ...enfants);
}

/** Fragment : un composant qui rend ses enfants (même effet qu'un fragment de React). */
export function Fragment(props: { children?: ReactTypes.ReactNode }): ReactTypes.ReactNode {
  return props.children ?? null;
}

export function useState<S>(initial: S | (() => S)): [S, (valeur: S | ((avant: S) => S)) => void] {
  return react().useState<S>(initial);
}

export function useEffect(effet: () => void | (() => void), dependances?: readonly unknown[]): void {
  react().useEffect(effet, dependances);
}

export function useMemo<T>(calcul: () => T, dependances: readonly unknown[]): T {
  return react().useMemo(calcul, dependances);
}

export function useRef<T>(initial: T): { current: T } {
  return react().useRef<T>(initial);
}

export type Noeud = ReactTypes.ReactNode;
export type Composant<P = Record<string, never>> = (props: P) => ReactTypes.ReactNode;
