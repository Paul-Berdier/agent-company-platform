// Mise en forme française des dates, durées et nombres, par Intl en fr-FR (fuseau Europe/Paris).
// Jamais SDK.utils.timeAgo, qui produit de l'anglais (« 5m ago »).

const FUSEAU = "Europe/Paris";

const relatif = new Intl.RelativeTimeFormat("fr-FR", { numeric: "auto" });
const absolu = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short", timeZone: FUSEAU });
const nombres = new Intl.NumberFormat("fr-FR");

/** Horodatage de l'API (secondes ou millisecondes depuis l'époque) en millisecondes ; null si
 *  la valeur n'en est pas un. Hermes renvoie des secondes (SessionInfo.started_at). */
export function versMillisecondes(valeur: unknown): number | null {
  if (typeof valeur !== "number" || !Number.isFinite(valeur) || valeur <= 0) return null;
  return valeur < 1e12 ? valeur * 1000 : valeur;
}

const PALIERS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 30],
  ["month", 12],
  ["year", Number.POSITIVE_INFINITY],
];

/** « il y a 5 minutes », « hier », « dans 2 heures » ; null si l'horodatage est illisible. */
export function dateRelative(valeur: unknown, maintenant: number = Date.now()): string | null {
  const ms = versMillisecondes(valeur);
  if (ms === null) return null;
  let ecart = (ms - maintenant) / 1000;
  for (const [unite, taille] of PALIERS) {
    if (Math.abs(ecart) < taille) return relatif.format(Math.round(ecart), unite);
    ecart /= taille;
  }
  return null;
}

/** « 25 sept. 2026, 14:03 » (fuseau Europe/Paris) ; null si l'horodatage est illisible. */
export function dateAbsolue(valeur: unknown): string | null {
  const ms = versMillisecondes(valeur);
  return ms === null ? null : absolu.format(new Date(ms));
}

export function nombre(valeur: unknown): string | null {
  return typeof valeur === "number" && Number.isFinite(valeur) ? nombres.format(valeur) : null;
}

/** Condensat ou commit abrégé : « sha256:fca358f12efd » → « fca358f12efd » (12 caractères). */
export function court(valeur: unknown, longueur = 12): string | null {
  if (typeof valeur !== "string" || !valeur) return null;
  const sans = valeur.includes(":") ? valeur.slice(valeur.indexOf(":") + 1) : valeur;
  return sans.slice(0, longueur);
}
