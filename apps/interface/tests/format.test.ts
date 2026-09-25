import { describe, expect, it } from "vitest";
import { court, dateAbsolue, dateRelative, nombre, versMillisecondes } from "../src/format";

const MAINTENANT = Date.UTC(2026, 8, 25, 12, 0, 0);

describe("format fr-FR", () => {
  it("dates relatives en français, secondes ou millisecondes", () => {
    expect(dateRelative(MAINTENANT / 1000 - 5 * 60, MAINTENANT)).toBe("il y a 5 minutes");
    expect(dateRelative(MAINTENANT - 3 * 3600 * 1000, MAINTENANT)).toBe("il y a 3 heures");
    expect(dateRelative(MAINTENANT / 1000 - 86400, MAINTENANT)).toBe("hier");
    expect(dateRelative(MAINTENANT / 1000, MAINTENANT)).toBe("maintenant");
    expect(dateRelative(MAINTENANT / 1000 + 7200, MAINTENANT)).toBe("dans 2 heures");
  });

  it("date absolue au fuseau Europe/Paris", () => {
    expect(dateAbsolue(MAINTENANT / 1000)).toBe("25 sept. 2026, 14:00");
  });

  it("une valeur illisible n'est jamais convertie en date", () => {
    for (const v of [null, undefined, 0, -1, "1727000000", Number.NaN]) {
      expect(versMillisecondes(v)).toBeNull();
      expect(dateRelative(v, MAINTENANT)).toBeNull();
      expect(dateAbsolue(v)).toBeNull();
    }
  });

  it("nombres et condensats", () => {
    expect(nombre(1234567)).toBe("1 234 567");
    expect(nombre("12")).toBeNull();
    expect(court("sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7")).toBe("fca358f12efd");
    expect(court("120b15c1234567", 7)).toBe("120b15c");
    expect(court("")).toBeNull();
    expect(court(null)).toBeNull();
  });
});
