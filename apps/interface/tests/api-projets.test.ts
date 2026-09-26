import { describe, expect, it } from "vitest";
import { ErreurApi } from "../src/api";
import {
  codeDuRefus,
  ecrireJSON,
  lancerProjet,
  messageDuRefus,
  nouvelleCle,
  pauseGenerale,
  reprendreTriage,
  routeReponse,
  routeReprendreTriage,
  ROUTE_PAUSE,
  ROUTE_PROJETS,
} from "../src/projets/api";
import { rechercheDeVue, vueDepuisAdresse } from "../src/projets/vue";
import { REFUS_AUCUN_INVENTAIRE } from "./fixtures-projets";
import { ApiErrorHermes, installerSdk } from "./sdk-factice";

describe("écritures de la page Projets", () => {
  it("POST en JSON par le fetchJSON du SDK, jamais par un fetch direct", async () => {
    const installation = installerSdk({ [`POST ${ROUTE_PAUSE}`]: { pause_generale: null } });
    await pauseGenerale(false);
    expect(installation.requetes).toEqual([
      { url: ROUTE_PAUSE, methode: "POST", corps: { generale: false }, entetes: { "Content-Type": "application/json" } },
    ]);
  });

  it("le lancement porte sa clé d'idempotence dans l'en-tête Idempotency-Key", async () => {
    const installation = installerSdk({ [`POST ${ROUTE_PROJETS}`]: { projet: { id: "p_1" }, deja_lance: false } });
    const demande = { titre: "T", objectif: "O", profil: "base", depot: null, reponses: "hermes_d_abord" as const };
    await lancerProjet(demande, "cle-1");
    const [requete] = installation.requetes;
    expect(requete?.entetes).toEqual({ "Content-Type": "application/json", "Idempotency-Key": "cle-1" });
    expect(requete?.corps).toEqual(demande);
  });

  it("les segments de chemin sont encodés ; une consigne vide n'est pas envoyée", async () => {
    expect(routeReponse("q/../x")).toBe("/api/plugins/acp-poste/v1/questions/q%2F..%2Fx/reponse");
    expect(routeReprendreTriage("acp-a b", "t_1")).toBe("/api/plugins/acp-poste/v1/triage/acp-a%20b/t_1/reprendre");
    const route = routeReprendreTriage("acp-t", "t_1");
    const installation = installerSdk({ [`POST ${route}`]: { reprise: true } });
    await reprendreTriage("acp-t", "t_1", null);
    await reprendreTriage("acp-t", "t_1", "Garder Python 3.12.");
    expect(installation.requetes.map((r) => r.corps)).toEqual([{}, { consigne: "Garder Python 3.12." }]);
  });

  it("une erreur de l'API devient une ErreurApi dont le refus français se lit tel quel", async () => {
    installerSdk({
      [`POST ${ROUTE_PROJETS}`]: new ApiErrorHermes("Refusé par ACP : …", 400, REFUS_AUCUN_INVENTAIRE, ROUTE_PROJETS),
    });
    const erreur = await ecrireJSON(ROUTE_PROJETS, {}).catch((e: unknown) => e);
    expect(erreur).toBeInstanceOf(ErreurApi);
    expect(messageDuRefus(erreur as ErreurApi)).toBe(
      "Refusé par ACP : aucun dépôt autorisé n'est connu : le poste n'a encore publié aucun inventaire (étape P5). " +
        "Lancez le projet sans dépôt, ou connectez le poste.",
    );
    expect(codeDuRefus(erreur as ErreurApi)).toBe("aucun_inventaire");
  });

  it("messageDuRefus : détail texte, détail structuré, ou rien (réseau, page HTML)", () => {
    expect(messageDuRefus(new ErreurApi("requete", 404, '{"detail":"Not Found"}'))).toBe("Not Found");
    expect(messageDuRefus(new ErreurApi("requete", 409, '{"detail":{"code":"x","message":"Refusé."}}'))).toBe("Refusé.");
    expect(messageDuRefus(new ErreurApi("reseau", null, "TypeError: Failed to fetch"))).toBeNull();
    expect(messageDuRefus(new ErreurApi("requete", 502, "<html>Bad gateway</html>"))).toBeNull();
    expect(messageDuRefus(new ErreurApi("requete", 500, "{pas du json"))).toBeNull();
    expect(codeDuRefus(new ErreurApi("requete", 404, '{"detail":"Not Found"}'))).toBeNull();
  });

  it("chaque clé d'idempotence est neuve", () => {
    const cles = new Set(Array.from({ length: 50 }, () => nouvelleCle()));
    expect(cles.size).toBe(50);
    for (const cle of cles) expect(cle).toMatch(/^[0-9a-f-]{32,36}$/);
  });
});

describe("routeur interne par l'adresse", () => {
  it("lit ?projet=, ?vue=questions et ?vue=nouveau ; refuse un identifiant douteux", () => {
    expect(vueDepuisAdresse("?projet=p_367e23fd51b7&profile=default")).toEqual({ genre: "detail", id: "p_367e23fd51b7" });
    expect(vueDepuisAdresse("?vue=questions")).toEqual({ genre: "questions" });
    expect(vueDepuisAdresse("?vue=nouveau")).toEqual({ genre: "nouveau" });
    expect(vueDepuisAdresse("")).toEqual({ genre: "liste" });
    expect(vueDepuisAdresse("?projet=../../etc")).toEqual({ genre: "liste" });
  });

  it("garde les autres paramètres (Hermes ajoute ?profile=)", () => {
    expect(rechercheDeVue({ genre: "detail", id: "p_1" }, "?profile=default&vue=nouveau")).toBe(
      "?profile=default&projet=p_1",
    );
    expect(rechercheDeVue({ genre: "liste" }, "?profile=default&projet=p_1")).toBe("?profile=default");
    expect(rechercheDeVue({ genre: "questions" })).toBe("?vue=questions");
  });
});
