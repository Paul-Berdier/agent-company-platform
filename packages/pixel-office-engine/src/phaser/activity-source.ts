export type ActivitySource = "real" | "decorative";

const REAL_STATUSES = new Set(["working", "thinking", "reviewing", "blocked"]);

/**
 * Une activité est réelle lorsqu'elle est ancrée à une station ou provient
 * d'un statut opérationnel reçu du backend. L'errance idle reste décorative.
 */
export function activitySourceFor(status: string, anchored: boolean): ActivitySource {
  return anchored || REAL_STATUSES.has(status) ? "real" : "decorative";
}
