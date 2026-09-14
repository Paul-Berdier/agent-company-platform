import { describe, expect, it } from "vitest";

import {
  AUTOMATION_TEMPLATES,
  buildBudgetLimits,
  buildScheduleInput,
  formatBudgetLimit,
  scheduleLabel,
} from "../src/automation-ui";

const base = {
  frequency: "daily" as const,
  timezone: "Europe/Paris",
  time: "09:05",
  weekday: "1",
  intervalValue: "60",
  intervalUnit: "minutes" as const,
  cron: "0 9 * * 1-5",
};

describe("assistant d’automatisation", () => {
  it("propose les six modèles initiaux attendus sans prétendre à un connecteur externe", () => {
    expect(AUTOMATION_TEMPLATES.map((template) => template.id)).toEqual([
      "repo-analysis",
      "fix-test",
      "prepare-pr",
      "sourced-report",
      "data-file",
      "watch-update",
    ]);
    expect(AUTOMATION_TEMPLATES.find((template) => template.id === "watch-update")?.acceptanceCriteria.join(" ")).toContain("connecteur non configuré");
  });

  it("convertit les fréquences lisibles en expressions serveur", () => {
    expect(buildScheduleInput(base)).toEqual({ kind: "cron", expression: "5 9 * * *", timezone: "Europe/Paris" });
    expect(buildScheduleInput({ ...base, frequency: "weekly", weekday: "4" })).toEqual({ kind: "cron", expression: "5 9 * * 4", timezone: "Europe/Paris" });
    expect(buildScheduleInput({ ...base, frequency: "interval", intervalValue: "2", intervalUnit: "hours" })).toEqual({ kind: "interval", expression: "7200", timezone: "Europe/Paris" });
    expect(buildScheduleInput({ ...base, frequency: "cron", cron: " 0 8 * * 1-5 " })).toEqual({ kind: "cron", expression: "0 8 * * 1-5", timezone: "Europe/Paris" });
  });

  it("refuse un intervalle invalide et présente les horaires sans exposer cron par défaut", () => {
    expect(() => buildScheduleInput({ ...base, frequency: "interval", intervalValue: "0" })).toThrow("positif");
    expect(scheduleLabel({ kind: "cron", expression: "5 9 * * *", timezone: "Europe/Paris" })).toBe("Chaque jour à 09:05");
    expect(scheduleLabel({ kind: "cron", expression: "5 9 * * 4", timezone: "Europe/Paris" })).toBe("Chaque jeudi à 09:05");
    expect(scheduleLabel({ kind: "interval", expression: "7200", timezone: "Europe/Paris" })).toBe("Toutes les 2 heure(s)");
  });

  it("ne confond jamais une limite inconnue et une limite à zéro", () => {
    expect(formatBudgetLimit(null, "EUR")).toBe("Inconnu / non limité");
    expect(formatBudgetLimit(0, "EUR")).toBe("0 EUR");
    expect(formatBudgetLimit(0.000001, "EUR")).toBe("0,000001 EUR");
    expect(buildBudgetLimits("", "EUR", "", "")).toBeNull();
    expect(buildBudgetLimits("0.000001", "eur", "0", "0")).toEqual({
      max_cost: 0.000001,
      currency: "EUR",
      max_tokens: 0,
      max_tool_calls: 0,
    });
    expect(() => buildBudgetLimits("1", "EU", "", "")).toThrow("trois lettres");
    expect(() => buildBudgetLimits("", "EUR", "0.5", "")).toThrow("entiers");
  });
});
