// Accueil (étape P7, cahier P7 § 8) : une lecture agrégée (GET /v1/accueil, fixture PARTAGÉE avec le test d'image
// hermes/tests/outils/fixtures_accueil/accueil.json), sept blocs dans un ordre fixe, discussions en attente comptées
// par le client, bilan quotidien (tâche cron native du propriétaire), système de P3 en dernier. Aucune donnée
// inventée : un bloc illisible le dit, avec sa raison.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { h } from "../src/react";
import { Accueil } from "../src/interface/Accueil";
import { ROUTE_ACCUEIL, ROUTE_CRON, TACHE_BILAN } from "../src/interface/accueil-api";
import { oublierMeta, ROUTE_META, ROUTE_SESSIONS } from "../src/api";
import { CATALOGUE } from "./catalogue-chaines";
import { META, SESSIONS } from "./fixtures";
import { ApiErrorHermes, attendre, installerSdk, rendre, textesHorsCatalogue, type Reponse } from "./sdk-factice";

const FIXTURE = join(process.cwd(), "..", "..", "hermes", "tests", "outils", "fixtures_accueil", "accueil.json");
const ACCUEIL = JSON.parse(readFileSync(FIXTURE, "utf8")) as Record<string, unknown>;
const TACHE = { id: "b1", name: "Bilan ACP", script: "acp-bilan.py", no_agent: true, enabled: true, state: "scheduled",
                next_run_at: "2026-10-03T08:00:00+02:00", last_run_at: null };

beforeEach(() => oublierMeta());
afterEach(() => vi.unstubAllGlobals());

function carte(racine: HTMLElement, id: string): Element | null | undefined {
  return racine.querySelector(`#${id}`)?.parentElement;
}

function texteDe(element: Element | null | undefined): string {
  return (element?.textContent ?? "").replace(/\s+/g, " ").trim();
}

function reponses(supplement: Record<string, Reponse> = {}): Record<string, Reponse> {
  return { [ROUTE_META]: META, [ROUTE_SESSIONS]: SESSIONS, [ROUTE_ACCUEIL]: ACCUEIL, [ROUTE_CRON]: [], ...supplement };
}

describe("Accueil agrégé (GET /v1/accueil)", () => {
  it("rend les sept blocs dans l'ordre, en français, à partir de la fixture partagée", async () => {
    installerSdk(reponses());
    window.__HERMES_BASE_PATH__ = "/hermes";
    const r = await rendre(<Accueil />);
    await attendre();
    const ordre = [...r.racine.querySelectorAll(".acp-grille--accueil > section > h2")].map((t) => t.id);
    expect(ordre).toEqual([
      "acp-accueil-a-traiter", "acp-accueil-projets", "acp-accueil-executant", "acp-accueil-quotas",
      "acp-projets-notifications", "acp-accueil-bilan", "acp-accueil-sessions", "acp-accueil-hermes",
      "acp-accueil-garde", "acp-accueil-persona", "acp-accueil-catalogue", "acp-accueil-raccourcis",
    ]);
    const aTraiter = texteDe(carte(r.racine, "acp-accueil-a-traiter"));
    expect(aTraiter).toContain("Exploration du dépôt « jetable »");
    expect(aTraiter).toContain("Discussions en attenteInconnues");  // SDK sans buildWsUrl : jamais zéro
    const lien = [...r.racine.querySelectorAll("#acp-accueil-a-traiter ~ * a, #acp-accueil-a-traiter ~ a")]
      .map((a) => a.getAttribute("href"));
    expect(lien).toContain("/hermes/projets?vue=questions&q=q_bf237cb06b85");
    const projets = texteDe(carte(r.racine, "acp-accueil-projets"));
    expect(projets).toContain("Outil jetable");
    expect(projets).toContain("0 sur 2");
    const executant = texteDe(carte(r.racine, "acp-accueil-executant"));
    for (const attendu of ["En ligne", "Exécutant Railway", "linux", "Exploration du dépôt « jetable »",
                           "Voies fermées", "isolement de l'exécutant (régime B)"]) {
      expect(executant).toContain(attendu);
    }
    const quotas = texteDe(carte(r.racine, "acp-accueil-quotas"));
    expect(quotas).toContain("41 %");
    // Relecture finale de P7 (constat produit-8) : la source dite pour l'hôte (exécutant Railway), jamais « sur ce PC »,
    // jamais un code seul.
    expect(quotas).toContain("Dernier événement de limite des cartes Claude de l'exécutant Railway");
    expect(quotas).toContain("Compteurs de votre compte ChatGPT, lus par Codex (app-server)");
    expect(quotas).not.toContain("sur ce PC");
    expect(quotas).not.toContain("codex_app_server");
    expect(quotas).toContain("Même enveloppe que Codex");
    expect(texteDe(carte(r.racine, "acp-projets-notifications"))).toContain("ntfy");
    // La carte « Poste » figée de P3 (« Non configuré ») n'existe plus : c'était une donnée fausse.
    expect(r.racine.querySelector("#acp-accueil-poste")).toBeNull();
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("quotas : une source sans libellé du greffon vaut « Inconnu », jamais le code (produit-8)", async () => {
    const quotas = JSON.parse(JSON.stringify(ACCUEIL.quotas)) as Record<string, Record<string, unknown>>;
    delete quotas["poste-codex"].source_libelle;
    installerSdk(reponses({ [ROUTE_ACCUEIL]: { ...ACCUEIL, quotas } }));
    const r = await rendre(<Accueil />);
    await attendre();
    const texte = texteDe(carte(r.racine, "acp-accueil-quotas"));
    expect(texte).not.toContain("codex_app_server");
    expect(texte).toContain("SourceInconnu");
    r.demonter();
  });

  it("un bloc illisible vaut « Bloc illisible » et sa raison, jamais une valeur par défaut", async () => {
    const illisible = { ...ACCUEIL, executant: null, quotas: null,
                        illisibles: { executant: "Bloc illisible (OperationalError) : rechargez la page." } };
    installerSdk(reponses({ [ROUTE_ACCUEIL]: illisible }));
    const r = await rendre(<Accueil />);
    await attendre();
    expect(texteDe(carte(r.racine, "acp-accueil-executant"))).toContain(
      "Bloc illisible : Bloc illisible (OperationalError) : rechargez la page.");
    expect(texteDe(carte(r.racine, "acp-accueil-quotas"))).toContain("Bloc illisible : Inconnu");
    r.demonter();
  });

  // Relecture finale de P7 (constat produit-4) : des discussions non lues comptaient pour zéro dans le total, et la
  // carte disait « Rien n'attend votre décision. » à côté de « Discussions en attente : Inconnues ».
  it("discussions inconnues : total qualifié, jamais « Rien n'attend »", async () => {
    const vide = { ...ACCUEIL, a_traiter: { total: 0, questions: 0, decisions: 0, revues: 0, arretees: 0, premieres: [],
                                           tableaux_illisibles: [] } };
    installerSdk(reponses({ [ROUTE_ACCUEIL]: vide }));  // SDK sans buildWsUrl : discussions inconnues
    const r = await rendre(<Accueil />);
    await attendre();
    const aTraiter = texteDe(carte(r.racine, "acp-accueil-a-traiter"));
    expect(aTraiter).not.toContain("Rien n'attend votre décision.");
    expect(aTraiter).toContain("0 (discussions en attente : état inconnu, non comptées)");
    r.demonter();
  });

  // Constat produit-12 : « Page actualisée en temps réel » couvrait aussi des cartes lues une seule fois.
  it("dit ce qui n'est lu qu'à l'ouverture (sessions récentes, système)", async () => {
    installerSdk(reponses());
    const r = await rendre(<Accueil />);
    await attendre();
    expect(r.texte()).toContain("Sessions récentes et cartes Système : lues à l'ouverture de la page.");
    r.demonter();
  });

  it("route /v1/accueil absente : l'accueil le dit ; le système (meta) reste lu", async () => {
    installerSdk({ [ROUTE_META]: META, [ROUTE_SESSIONS]: SESSIONS, [ROUTE_CRON]: [] });
    const r = await rendre(<Accueil />);
    await attendre();
    expect(r.texte()).toContain("L'accueil est indisponible : le greffon acp-poste ne répond pas sur /v1/accueil.");
    expect(r.racine.querySelector("#acp-accueil-a-traiter")).toBeNull();
    expect(r.racine.querySelector("#acp-accueil-hermes")).not.toBeNull();
    r.demonter();
  });
});

describe("bilan quotidien (tâche cron native du propriétaire)", () => {
  it("non créé : le bouton appelle POST /api/cron/jobs avec la session, sans agent, à 8 h", async () => {
    const table = reponses({ [`POST ${ROUTE_CRON}`]: TACHE });
    const installation = installerSdk(table);
    const r = await rendre(<Accueil />);
    await attendre();
    const bilan = carte(r.racine, "acp-accueil-bilan");
    expect(texteDe(bilan)).toContain("Non créé");
    const bouton = [...(bilan?.querySelectorAll("button") ?? [])].find((b) => b.textContent === "Créer le bilan quotidien (8 h)");
    table[ROUTE_CRON] = [TACHE];
    await act(async () => {
      bouton?.click();
    });
    await attendre(6);
    expect(installation.requetes.filter((q) => q.methode === "POST").map((q) => [q.url, q.corps])).toEqual([
      [ROUTE_CRON, { name: "Bilan ACP", schedule: "0 8 * * *", prompt: "", no_agent: true, script: "acp-bilan.py",
                     deliver: "local" }],
    ]);
    expect(TACHE_BILAN.no_agent).toBe(true);
    expect(texteDe(carte(r.racine, "acp-accueil-bilan"))).toContain("Actif");
    expect(texteDe(carte(r.racine, "acp-accueil-bilan"))).toContain("Prochaine exécution");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("une tâche avec agent n'est pas le bilan ; une tâche en pause le dit ; canal absent : il ne partira pas", async () => {
    const sansCanal = { ...ACCUEIL, notifications: { canal: "aucune", configure: false, connu: true, message: null } };
    installerSdk(reponses({
      [ROUTE_ACCUEIL]: sansCanal,
      [ROUTE_CRON]: [{ ...TACHE, id: "x", no_agent: false }, { ...TACHE, enabled: false, state: "paused" }],
    }));
    const r = await rendre(<Accueil />);
    await attendre();
    const bilan = texteDe(carte(r.racine, "acp-accueil-bilan"));
    expect(bilan).toContain("En pause");
    expect(bilan).not.toContain("Prochaine exécution");
    expect(bilan).not.toContain("Plusieurs tâches");
    expect(bilan).toContain("Le bilan ne partira pas : notifications non configurées.");
    r.demonter();
  });

  // Relecture finale de P7 (constats produit-2, scenario-5) : Hermes date last_run_at à CHAQUE exécution, même en échec
  // (last_status « error ») ; la carte disait « Dernier envoi » d'après last_run_at seul, donc un faux succès.
  it("dernière exécution en échec : dite, détail replié ; jamais « envoi »", async () => {
    installerSdk(reponses({
      [ROUTE_CRON]: [{ ...TACHE, last_run_at: "2026-10-08T08:00:03+02:00", last_status: "error",
                       last_error: "bilan non enfilé (OperationalError)", failure_streak: 1 }],
    }));
    const r = await rendre(<Accueil />);
    await attendre();
    const bilan = carte(r.racine, "acp-accueil-bilan");
    const texte = texteDe(bilan);
    expect(texte).not.toContain("envoi");
    expect(texte).toContain("Dernière exécution");
    expect(texteDe(bilan?.querySelector(".acp-alerte-texte"))).toBe(
      "Dernière exécution en échec : le bilan de ce jour n'est pas garanti. Détail ci-dessous et sur la page Cron.");
    expect(texteDe(bilan?.querySelector("details"))).toContain("bilan non enfilé (OperationalError)");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("tâche en erreur chez Hermes (prochaine exécution incalculable) : « En erreur », jamais « Actif »", async () => {
    installerSdk(reponses({
      [ROUTE_CRON]: [{ ...TACHE, state: "error", next_run_at: null, last_run_at: "2026-10-08T08:00:03+02:00",
                       last_status: "ok", last_error: "Failed to compute next run for recurring schedule" }],
    }));
    const r = await rendre(<Accueil />);
    await attendre();
    const bilan = texteDe(carte(r.racine, "acp-accueil-bilan"));
    expect(bilan).toContain("En erreur");
    expect(bilan).not.toContain("Actif");
    expect(bilan).toContain("Failed to compute next run for recurring schedule");
    r.demonter();
  });

  it("issue de la dernière exécution non publiée : jamais dite « en échec » (aucune donnée inventée)", async () => {
    installerSdk(reponses({ [ROUTE_CRON]: [{ ...TACHE, last_run_at: "2026-10-08T08:00:03+02:00" }] }));
    const r = await rendre(<Accueil />);
    await attendre();
    const bilan = carte(r.racine, "acp-accueil-bilan");
    expect(texteDe(bilan)).toContain("Dernière exécution");
    expect(texteDe(bilan)).not.toContain("en échec");
    r.demonter();
  });

  it("dernière exécution réussie : aucune alerte", async () => {
    installerSdk(reponses({
      [ROUTE_CRON]: [{ ...TACHE, last_run_at: "2026-10-08T08:00:03+02:00", last_status: "ok", last_error: null }],
    }));
    const r = await rendre(<Accueil />);
    await attendre();
    const bilan = carte(r.racine, "acp-accueil-bilan");
    expect(texteDe(bilan)).toContain("Actif");
    expect(texteDe(bilan)).toContain("Prochaine exécution");
    expect(bilan?.querySelector(".acp-alerte-texte")).toBeNull();
    r.demonter();
  });

  // Constat produit-14 : un refus de la route NATIVE (anglais) n'est pas un message du greffon.
  it("création refusée par la route native : message français, détail anglais replié", async () => {
    installerSdk(reponses({
      [`POST ${ROUTE_CRON}`]: new ApiErrorHermes("script does not exist: /opt/data/scripts/acp-bilan.py", 400,
                                                 '{"detail":"script does not exist: /opt/data/scripts/acp-bilan.py"}'),
    }));
    const r = await rendre(<Accueil />);
    await attendre();
    const bilan = carte(r.racine, "acp-accueil-bilan");
    const bouton = [...(bilan?.querySelectorAll("button") ?? [])].find((b) => b.textContent === "Créer le bilan quotidien (8 h)");
    await act(async () => {
      bouton?.click();
    });
    await attendre(6);
    const erreur = carte(r.racine, "acp-accueil-bilan")?.querySelector('[role="alert"]');
    expect(texteDe(erreur?.querySelector("p"))).toBe(
      "Le bilan n'a pas été créé : Hermes a refusé la tâche (détail technique ci-dessous).");
    expect(texteDe(erreur?.querySelector("details"))).toContain("script does not exist");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("liste cron illisible : état du bilan inconnu, aucun bouton", async () => {
    installerSdk(reponses({ [ROUTE_CRON]: new ApiErrorHermes("Internal error", 500, '{"detail":"boom"}') }));
    const r = await rendre(<Accueil />);
    await attendre();
    const bilan = carte(r.racine, "acp-accueil-bilan");
    expect(texteDe(bilan)).toContain("État du bilan inconnu : la liste des tâches cron de Hermes ne répond pas.");
    expect(bilan?.querySelector("button")).toBeNull();
    r.demonter();
  });
});

describe("système (cartes de P3, en dernier)", () => {
  it.each([
    ["divergent", "Modifiée par le propriétaire"],
    ["depose", "Déposée à ce démarrage"],
    ["non_ordinaire", "Fichier non ordinaire"],
    ["autre-chose", "Inconnu"],
  ])("persona %s", async (etat, libelle) => {
    installerSdk(reponses({ [ROUTE_META]: { ...META, demarrage: { soul: { etat } } } }));
    const r = await rendre(<Accueil />);
    expect(carte(r.racine, "acp-accueil-persona")?.textContent).toContain(libelle);
    r.demonter();
  });

  it("montre le résumé du catalogue quand /v1/meta le fournit ; « Inconnu » pour chaque valeur absente", async () => {
    installerSdk(reponses({
      [ROUTE_META]: { ...META, catalogue: { skills_actives: 17, skills_attendues: 17, context7: "connecte" } } }));
    const r = await rendre(<Accueil />);
    const bloc = carte(r.racine, "acp-accueil-catalogue");
    expect(bloc?.textContent).toContain("17");
    expect(bloc?.textContent).toContain("Connecté");
    r.demonter();
    oublierMeta();
    installerSdk(reponses({ [ROUTE_META]: { contrat: "acp-poste/1", garde_execution: {
      presente_dans_le_gestionnaire: false, alerte: "Garde d'exécution absente du processus du tableau de bord." } },
                             [ROUTE_SESSIONS]: { sessions: [] } }));
    const r2 = await rendre(<Accueil />);
    const hermes = carte(r2.racine, "acp-accueil-hermes");
    expect(hermes?.querySelectorAll(".acp-inconnu").length).toBe(4);
    expect(carte(r2.racine, "acp-accueil-garde")?.textContent).toContain("Garde d'exécution absente");
    expect(r2.texte()).toContain("Aucune session pour l'instant.");
    expect(textesHorsCatalogue(r2.racine, CATALOGUE)).toEqual([]);
    r2.demonter();
  });

  it("dit que l'état est indisponible quand /v1/meta ne répond pas ; erreur réseau des sessions en français", async () => {
    installerSdk({ [ROUTE_SESSIONS]: new ApiErrorHermes("Hermes dashboard cannot reach the Hermes service.", 0,
                                                       "TypeError: Failed to fetch"), [ROUTE_ACCUEIL]: ACCUEIL,
                   [ROUTE_CRON]: [] });
    const r = await rendre(<Accueil />);
    await attendre();
    expect(r.texte()).toContain("L'état de la plateforme est indisponible");
    expect(r.racine.querySelector("#acp-accueil-hermes")).toBeNull();
    expect(carte(r.racine, "acp-accueil-sessions")?.textContent).toContain("Le tableau de bord ne répond pas.");
    r.demonter();
  });
});
