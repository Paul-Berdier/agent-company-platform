// Typage du JSX « classique » (fabrique h) avec les types de React 19, qui ne déclarent plus
// d'espace de noms JSX global. Seulement des types : React vient du SDK du tableau de bord à
// l'exécution (src/react.ts), jamais de ce paquet.
import type { JSX as ReactJSX } from "react";

declare global {
  namespace JSX {
    type ElementType = ReactJSX.ElementType;
    interface Element extends ReactJSX.Element {}
    interface ElementClass extends ReactJSX.ElementClass {}
    interface ElementAttributesProperty extends ReactJSX.ElementAttributesProperty {}
    interface ElementChildrenAttribute extends ReactJSX.ElementChildrenAttribute {}
    type LibraryManagedAttributes<C, P> = ReactJSX.LibraryManagedAttributes<C, P>;
    interface IntrinsicAttributes extends ReactJSX.IntrinsicAttributes {}
    interface IntrinsicClassAttributes<T> extends ReactJSX.IntrinsicClassAttributes<T> {}
    interface IntrinsicElements extends ReactJSX.IntrinsicElements {}
  }
}
