import { describe, expect, it } from "vitest";

import { activitySourceFor } from "../src/phaser/activity-source";

describe("activitySourceFor", () => {
  it.each(["working", "thinking", "reviewing", "blocked"])(
    "marque le statut backend %s comme réel",
    (status) => expect(activitySourceFor(status, false)).toBe("real"),
  );

  it("marque une activité ancrée comme réelle", () => {
    expect(activitySourceFor("idle", true)).toBe("real");
  });

  it.each(["idle", "offline", "completed", "error"])(
    "garde le statut non opérationnel %s décoratif sans station",
    (status) => expect(activitySourceFor(status, false)).toBe("decorative"),
  );
});
