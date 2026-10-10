// Verrou du français (décision D10) : au chargement et à CHAQUE changement de langue, le tableau
// de bord revient au français. Hermes ne fixe aucune langue côté serveur : la sienne vient de
// localStorage["hermes-locale"], anglais par défaut (web/src/i18n/context.tsx:50-64) ; son
// sélecteur de langue reste visible, mais tout autre choix est aussitôt annulé.
import { useEffect, type Noeud } from "../react";
import { sdk, type I18nHermes } from "../sdk";

export const LANGUE = "fr";

/** Remet le français si la langue courante est une autre ; vrai si un changement a été demandé. */
export function forcerFrancais(i18n: unknown): boolean {
  const valeur = i18n as I18nHermes | null | undefined;
  if (!valeur || typeof valeur.setLocale !== "function" || valeur.locale === LANGUE) return false;
  valeur.setLocale(LANGUE);
  return true;
}

export function VerrouFrancais(): Noeud {
  const useI18n = sdk().useI18n;
  // Crochet de contexte de Hermes : appelé à chaque rendu, sans condition (le SDK ne change pas).
  const i18n = typeof useI18n === "function" ? (useI18n() as I18nHermes) : null;
  const langue = i18n?.locale;
  useEffect(() => {
    forcerFrancais(i18n);
  }, [langue]);
  return null;
}
