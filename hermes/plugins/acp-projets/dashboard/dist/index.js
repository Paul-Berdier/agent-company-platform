/* acp-projets 0.11.0 (ACP) — bundle généré par apps/interface/esbuild.mjs depuis apps/interface/src ; ne pas modifier à la main. Aucun code tiers embarqué : React vient du SDK du tableau de bord de Hermes. */

"use strict";
(() => {
  var __defProp = Object.defineProperty;
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

  // src/chaines.ts
  var T = {
    commun: {
      inconnu: "Inconnu",
      oui: "Oui",
      non: "Non",
      separateur: "\xB7",
      chargement: "Chargement\u2026",
      detailTechnique: "D\xE9tail technique",
      nonConfigure: "Non configur\xE9"
    },
    marque: {
      sigle: "ACP",
      lienAccueil: "ACP, retour \xE0 l'accueil"
    },
    etats: {
      conforme: "Conforme",
      nonConforme: "Non conforme",
      inconnu: "Inconnu",
      nonConfigure: "Non configur\xE9",
      horsLigne: "Hors ligne",
      connecte: "Connect\xE9",
      active: "Active",
      activee: "Activ\xE9e",
      desactivee: "D\xE9sactiv\xE9e",
      absente: "Absente",
      candidate: "Candidate pour le poste, non planifi\xE9e",
      prevueP8: "Pr\xE9vu au poste (P8)",
      horsV1: "Hors v1",
      ambigue: "Nom ambigu",
      livree: "Livr\xE9e",
      aJour: "\xC0 jour",
      deposee: "D\xE9pos\xE9e \xE0 ce d\xE9marrage",
      divergente: "Modifi\xE9e par le propri\xE9taire",
      nonOrdinaire: "Fichier non ordinaire",
      presente: "Pr\xE9sente"
    },
    accueil: {
      titre: "Accueil",
      intro: "\xC9tat de votre agent Hermes et de la plateforme ACP, relev\xE9 \xE0 l'ouverture de la page.",
      hermes: "Hermes",
      version: "Version en service",
      versionTestee: "Version test\xE9e par ACP",
      conformite: "Conformit\xE9",
      image: "Image de base",
      commit: "Commit d\xE9ploy\xE9",
      garde: "Garde d'ex\xE9cution",
      gardeEtat: "Processus du tableau de bord",
      gardeActive: "Active",
      gardeAbsente: "Absente",
      outilsAdmis: "Outils admis pour l'agent",
      persona: "Persona",
      personaEtat: "SOUL.md",
      catalogue: "Catalogue",
      skillsAcp: "Skills ACP actives",
      skillsAttendues: "attendues",
      context7: "context7",
      ouvrirCatalogue: "Ouvrir le catalogue",
      sessions: "Sessions r\xE9centes",
      aucuneSession: "Aucune session pour l'instant.",
      sansTitre: "Sans titre",
      messages: "messages",
      toutesSessions: "Toutes les sessions",
      poste: "Poste Windows",
      posteNote: "Le poste du propri\xE9taire n'est pas encore branch\xE9\xA0: il le sera \xE0 l'\xE9tape P5.",
      raccourcis: "Raccourcis",
      lienProjets: "Projets",
      discussion: "Discussion",
      lienSessions: "Sessions",
      kanban: "Kanban",
      lienCatalogue: "Catalogue",
      piedAcp: "ACP",
      piedPropulse: "propuls\xE9 par Hermes Agent",
      piedLicence: "(licence MIT)",
      metaIndisponible: "L'\xE9tat de la plateforme est indisponible\xA0: la route /v1/meta du greffon acp-poste ne r\xE9pond pas."
    },
    catalogue: {
      titre: "Catalogue",
      intro: "Skills et serveurs MCP retenus par ACP, en lecture seule\xA0: rien ne s'installe depuis cette page.",
      filtres: "Filtres",
      profil: "Profil",
      source: "Source",
      cible: "Cible",
      tous: "Tous",
      toutes: "Toutes",
      profilBase: "Base",
      profilWeb: "Site web",
      profilRecherche: "Recherche",
      profilDonnees: "Donn\xE9es",
      cibleHermes: "Hermes (Railway)",
      ciblePoste: "Poste Windows",
      skills: "Skills",
      mcp: "Serveurs MCP",
      nom: "Nom",
      description: "Description",
      etat: "\xC9tat",
      licence: "Licence",
      outils: "Outils expos\xE9s",
      aucuneEntree: "Aucune entr\xE9e pour ces filtres.",
      ecarts: "\xC9carts",
      aucunEcart: "Aucun \xE9cart relev\xE9.",
      horsCatalogue: "Install\xE9es hors catalogue",
      collisions: "Collisions de noms",
      desactivationsNonAppliquees: "D\xE9sactivations non appliqu\xE9es",
      indisponible: "Catalogue ACP indisponible\xA0: le greffon acp-poste ne sert pas la route /v1/catalogue.",
      alertes: "Alertes du catalogue",
      vuParHermes: "Vu par le tableau de bord de Hermes",
      vuParHermesNote: "Liste renvoy\xE9e par /api/skills, telle que le tableau de bord la calcule.",
      skillsInstallees: "Skills install\xE9es",
      skillsActivees: "Activ\xE9es",
      skillsDesactivees: "D\xE9sactiv\xE9es",
      listeSkills: "Liste des skills"
    },
    alertes: {
      titre: "Alertes ACP"
    },
    projets: {
      titre: "Projets",
      intro: "Les projets que vous confiez \xE0 Hermes\xA0: il les planifie, les fait avancer carte par carte et vous pose ici ses questions.",
      navigation: "Pages des projets",
      vueListe: "Projets",
      vueQuestions: "Questions",
      vueNouveau: "Nouveau projet",
      actualisation: "Page actualis\xE9e toutes les 15 secondes tant qu'elle est visible.",
      actualisationImpossible: "Derni\xE8re actualisation impossible\xA0: les donn\xE9es affich\xE9es sont celles de la lecture pr\xE9c\xE9dente.",
      indisponible: "Les projets sont indisponibles\xA0: le greffon acp-poste ne r\xE9pond pas sur /v1/projets.",
      questionsIndisponibles: "Les questions sont indisponibles\xA0: le greffon acp-poste ne r\xE9pond pas sur /v1/questions.",
      posteIndisponible: "L'inventaire du poste est indisponible\xA0: le greffon acp-poste ne r\xE9pond pas sur /v1/poste.",
      envoi: "Envoi\u2026",
      vosProjets: "Vos projets",
      nouveauProjet: "Nouveau projet",
      aucunProjet: "Aucun projet pour l'instant. Lancez-en un avec \xAB\xA0Nouveau projet\xA0\xBB, ou demandez-le \xE0 Hermes dans la discussion.",
      cartesFaites: "Cartes faites",
      sur: "sur",
      enAttenteDuPoste: "Cartes en attente du poste",
      bloquees: "Cartes bloqu\xE9es",
      enTriage: "Cartes en triage",
      questionsEnAttente: "Questions en attente",
      derniereNote: "Derni\xE8re note",
      aucuneNote: "Aucune carte finie pour l'instant.",
      poste: "Poste",
      depuis: "depuis",
      depuisLe: "Depuis",
      creeLe: "Cr\xE9\xE9",
      termineLe: "Termin\xE9",
      etat: "\xC9tat",
      posteTitre: "Poste Windows",
      machine: "Machine",
      derniereVue: "Vu pour la derni\xE8re fois",
      cartesEnAttente: "Cartes du poste en attente",
      notificationsTitre: "Notifications",
      canal: "Canal",
      canalAucun: "Aucun",
      canalTelegram: "Telegram",
      canalNtfy: "ntfy",
      etatNotifications: "\xC9tat",
      notificationsActives: "Configur\xE9es",
      notificationsInactives: "Non configur\xE9es",
      notificationsNonConfigurees: "Notifications non configur\xE9es (variables ACP_NOTIFICATIONS\u2026 du service Hermes sur Railway).",
      envoyerTest: "Envoyer une notification de test",
      pauseTitre: "Pause g\xE9n\xE9rale",
      pauseExplication: "Arr\xEAte tout le travail de Hermes\xA0: aucune nouvelle carte ne part et les cartes en cours finissent. Aucune notification pendant la pause.",
      pauseGenerale: "Pause g\xE9n\xE9rale",
      pauseQuestion: "Mettre Hermes en pause g\xE9n\xE9rale\xA0?",
      pauseConfirmer: "Confirmer la pause g\xE9n\xE9rale",
      annuler: "Annuler",
      pauseEnCours: "Hermes est en pause g\xE9n\xE9rale",
      pauseEffet: "Aucune nouvelle carte ne part tant que vous ne reprenez pas.",
      raison: "Raison",
      reprendreHermes: "Reprendre",
      nouveauTitre: "Nouveau projet",
      nouveauIntro: "D\xE9crivez le r\xE9sultat attendu\xA0: Hermes le d\xE9coupe en \xE9tapes v\xE9rifiables et le fait avancer seul. Il ne pousse, ne fusionne et ne publie jamais sans votre accord.",
      champTitre: "Titre",
      champObjectif: "Objectif",
      aideObjectif: "Ce qui doit exister \xE0 la fin, les contraintes et ce qui compte pour vous.",
      champProfil: "Type de projet",
      champReponses: "Qui r\xE9pond aux questions",
      reponsesHermes: "Hermes d'abord",
      reponsesHermesAide: "Hermes r\xE9pond s'il le peut \xE0 partir de l'objectif et des d\xE9cisions du projet\xA0; sinon, il vous transmet la question.",
      reponsesProprietaire: "Moi",
      reponsesProprietaireAide: "Chaque question vous est transmise directement.",
      champDepot: "D\xE9p\xF4t",
      sansDepot: "Sans d\xE9p\xF4t",
      aucunDepotConnu: "Aucun d\xE9p\xF4t connu\xA0: le poste n'a encore publi\xE9 aucun inventaire (\xE9tape P5).",
      releveFactice: "Relev\xE9 factice\xA0: ces mod\xE8les viennent d'un relev\xE9 de test, pas de votre poste.",
      exploration: "Exploration du d\xE9p\xF4t",
      explorationAide: "Le poste lit le d\xE9p\xF4t, sans rien y modifier, avant la planification.",
      champVoie: "Ex\xE9cutant",
      champModele: "Mod\xE8le",
      modeleParDefaut: "Mod\xE8le par d\xE9faut du relev\xE9",
      champEffort: "Effort",
      effortParDefaut: "Par d\xE9faut",
      releveDu: "Relev\xE9 du",
      relevePerime: "Relev\xE9 p\xE9rim\xE9\xA0: le poste doit publier un nouvel inventaire.",
      lancer: "Lancer le projet",
      retour: "Retour aux projets",
      objectif: "Objectif",
      tour: "Tour",
      cartesCreees: "Cartes cr\xE9\xE9es",
      correctionsParEtape: "Corrections par \xE9tape au plus",
      profil: "Type de projet",
      depot: "D\xE9p\xF4t",
      reponses: "Qui r\xE9pond",
      origine: "Lanc\xE9 depuis",
      origineTableau: "la page Projets",
      origineDiscussion: "la discussion",
      mettreEnPause: "Mettre en pause",
      reprendre: "Reprendre",
      cartes: "Cartes",
      aucuneCarte: "Aucune carte pour l'instant.",
      statut: "Statut",
      voie: "Ex\xE9cutant",
      modeleDemande: "Mod\xE8le demand\xE9",
      effort: "Effort",
      palier: "Palier",
      modeleServi: "Mod\xE8le servi",
      mention: "Mention",
      carte: "Carte",
      resume: "R\xE9sum\xE9",
      toursTitre: "Tours et d\xE9cisions",
      decisions: "D\xE9cisions",
      voirQuestions: "Voir les questions",
      journal: "Journal",
      journalVide: "Journal vide.",
      journalOuvrir: "Entr\xE9es du journal",
      questionsTitre: "Questions ouvertes",
      aucuneQuestion: "Aucune question en attente.",
      projet: "Projet",
      motifEscalade: "Motif",
      poseeLe: "Pos\xE9e",
      votreReponse: "Votre r\xE9ponse",
      repondre: "R\xE9pondre",
      reponseEnvoyee: "R\xE9ponse envoy\xE9e\xA0: la carte reprend.",
      triageTitre: "Cartes en triage",
      aucunTriage: "Aucune carte en triage.",
      consigne: "Consigne (facultative)",
      reprendreCarte: "Reprendre",
      carteReprise: "Carte reprise\xA0: elle repart dans le graphe du projet.",
      bloqueesTitre: "Cartes bloqu\xE9es ou abandonn\xE9es",
      bloqueesNote: "Lecture seule\xA0: relancer une carte depuis cette page arrivera \xE0 l'\xE9tape P7\xA0; en attendant, le kanban de Hermes le permet.",
      aucuneBloquee: "Aucune carte bloqu\xE9e.",
      abandonnee: "Abandonn\xE9e apr\xE8s plusieurs \xE9checs",
      assigne: "Assign\xE9e \xE0",
      tableauxIllisibles: "Tableaux illisibles",
      etats: {
        creation: "Cr\xE9ation en cours",
        actif: "Actif",
        enPause: "En pause",
        termine: "Termin\xE9",
        abandonne: "Abandonn\xE9",
        exploration: "Exploration du d\xE9p\xF4t",
        planification: "Planification",
        synthese: "Synth\xE8se",
        enCours: "En cours",
        enAttenteDuPoste: "En attente du poste",
        plafondAtteint: "Plafond atteint\xA0: votre d\xE9cision est attendue"
      },
      statuts: {
        triage: "En triage",
        todo: "En attente",
        scheduled: "Suspendue",
        ready: "Pr\xEAte",
        running: "En cours",
        blocked: "Bloqu\xE9e",
        review: "En relecture",
        done: "Faite",
        archived: "Archiv\xE9e",
        aCreer: "\xC0 cr\xE9er"
      },
      roles: {
        exploration: "Exploration du d\xE9p\xF4t",
        planification: "Planification",
        implementation: "Impl\xE9mentation",
        relecture: "Relecture crois\xE9e",
        correction: "Corrections",
        hermes: "\xC9tapes de Hermes",
        synthese: "Synth\xE8se",
        repondre: "R\xE9ponses aux questions",
        triage: "Triage"
      },
      voies: {
        hermes: "Hermes",
        posteCodex: "Poste (Codex)",
        posteClaude: "Poste (Claude)"
      },
      etatsPoste: {
        nonConfigure: "Non configur\xE9",
        enLigne: "En ligne",
        horsLigne: "Hors ligne"
      },
      etatsQuestion: {
        ouverte: "Hermes cherche la r\xE9ponse",
        escaladee: "Votre r\xE9ponse est attendue"
      }
    },
    refus: {
      sdk: "Interface ACP d\xE9sactiv\xE9e\xA0: SDK du tableau de bord incompatible.",
      attendu: "Attendu\xA0:",
      trouve: "Trouv\xE9\xA0:"
    },
    erreurs: {
      requete: "La requ\xEAte a \xE9chou\xE9.",
      code: "Code HTTP",
      reseau: "Le tableau de bord ne r\xE9pond pas.",
      inattendue: "Erreur inattendue."
    }
  };

  // src/sdk.ts
  var MAJEURE_ATTENDUE = 1;
  var SDK_ATTENDU = `${MAJEURE_ATTENDUE}.x`;
  function verifierSdk(sdk2) {
    if (!sdk2 || typeof sdk2 !== "object") return { ok: false, trouve: "absent" };
    const brut = sdk2.sdkVersion;
    if (typeof brut !== "string" || !/^\d+\.\d+\.\d+$/.test(brut)) {
      return { ok: false, trouve: typeof brut === "string" ? brut.slice(0, 40) : "absent" };
    }
    if (Number(brut.split(".")[0]) !== MAJEURE_ATTENDUE) return { ok: false, trouve: brut };
    const s = sdk2;
    if (!s.React || typeof s.React.createElement !== "function" || typeof s.fetchJSON !== "function") {
      return { ok: false, trouve: `${brut} incomplet` };
    }
    return { ok: true, version: brut };
  }
  function sdk() {
    const valeur = window.__HERMES_PLUGIN_SDK__;
    if (!valeur) throw new Error("SDK du tableau de bord absent");
    return valeur;
  }
  function cheminDeBase() {
    const brut = window.__HERMES_BASE_PATH__ ?? "";
    return typeof brut === "string" ? brut.replace(/\/+$/, "") : "";
  }

  // src/api.ts
  var ROUTE_CATALOGUE = "/api/plugins/acp-poste/v1/catalogue";
  var ErreurApi = class extends Error {
    constructor(genre, statut, detail) {
      super(`${genre}${statut === null ? "" : ` ${statut}`}`);
      __publicField(this, "genre");
      __publicField(this, "statut");
      __publicField(this, "detail");
      this.name = "ErreurApi";
      this.genre = genre;
      this.statut = statut;
      this.detail = detail.slice(0, 2e3);
    }
  };
  function envelopper(erreur) {
    if (erreur instanceof ErreurApi) return erreur;
    const message = erreur instanceof Error ? erreur.message : String(erreur);
    const champs = erreur && typeof erreur === "object" ? erreur : {};
    if (typeof champs.status === "number" && Number.isInteger(champs.status)) {
      const corps = typeof champs.body === "string" && champs.body ? champs.body : message;
      return champs.status === 0 ? new ErreurApi("reseau", null, corps) : new ErreurApi("requete", champs.status, corps);
    }
    const trouve = /^(\d{3}):\s?([\s\S]*)$/.exec(message);
    if (trouve) return new ErreurApi("requete", Number(trouve[1]), trouve[2] ?? "");
    if (erreur instanceof TypeError || /fetch|network|réseau|unreachable/i.test(message)) {
      return new ErreurApi("reseau", null, message);
    }
    return new ErreurApi("inattendue", null, message);
  }
  async function lireJSON(url) {
    const fetchJSON = sdk().fetchJSON;
    if (typeof fetchJSON !== "function") throw new ErreurApi("inattendue", null, "fetchJSON absent du SDK");
    try {
      return await fetchJSON(url);
    } catch (erreur) {
      throw envelopper(erreur);
    }
  }
  var lireCatalogue = () => lireJSON(ROUTE_CATALOGUE);

  // src/react.ts
  function react() {
    const r = sdk().React;
    if (!r) throw new Error("React absent du SDK du tableau de bord");
    return r;
  }
  function h(type, props, ...enfants) {
    const createElement = react().createElement;
    return createElement(type, props, ...enfants);
  }
  function useState(initial) {
    return react().useState(initial);
  }
  function useEffect(effet, dependances) {
    react().useEffect(effet, dependances);
  }
  function useRef(initial) {
    return react().useRef(initial);
  }

  // src/commun.tsx
  function Donnee(props) {
    const { valeur, mono } = props;
    if (valeur === null || valeur === void 0 || valeur === "") {
      return /* @__PURE__ */ h("span", { className: "acp-inconnu" }, T.commun.inconnu);
    }
    return /* @__PURE__ */ h("span", { "data-acp-donnee": "", className: mono ? "acp-donnee acp-mono" : "acp-donnee" }, String(valeur));
  }
  function Carte(props) {
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": props.id }, /* @__PURE__ */ h("h2", { className: "acp-carte__titre", id: props.id }, props.titre), props.children);
  }
  function Ligne(props) {
    return /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, props.libelle), /* @__PURE__ */ h("dd", null, props.children));
  }
  function BlocErreur(props) {
    const erreur = props.erreur instanceof ErreurApi ? props.erreur : envelopper(props.erreur);
    const message = props.message ?? (erreur.genre === "reseau" ? T.erreurs.reseau : erreur.genre === "requete" ? T.erreurs.requete : T.erreurs.inattendue);
    return /* @__PURE__ */ h("div", { className: "acp-erreur", role: "alert" }, /* @__PURE__ */ h("p", null, message), erreur.statut !== null ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.erreurs.code), " ", /* @__PURE__ */ h(Donnee, { valeur: erreur.statut, mono: true })) : null, erreur.detail ? /* @__PURE__ */ h("details", { className: "acp-details" }, /* @__PURE__ */ h("summary", null, T.commun.detailTechnique), /* @__PURE__ */ h(Donnee, { valeur: erreur.detail, mono: true })) : null);
  }
  function useChargement(charger) {
    const [etat, fixer] = useState({ etat: "chargement" });
    useEffect(() => {
      let actif = true;
      charger().then(
        (valeur) => {
          if (actif) fixer({ etat: "ok", valeur });
        },
        (erreur) => {
          if (actif) fixer({ etat: "erreur", erreur: envelopper(erreur) });
        }
      );
      return () => {
        actif = false;
      };
    }, []);
    return etat;
  }
  function EnChargement() {
    return /* @__PURE__ */ h("p", { className: "acp-discret", "aria-live": "polite", "aria-busy": "true" }, T.commun.chargement);
  }

  // src/refus.tsx
  function creerRefus(trouve) {
    return function RefusSdk() {
      return /* @__PURE__ */ h("div", { "data-acp-racine": "refus", className: "acp-banniere acp-banniere--refus", role: "alert" }, /* @__PURE__ */ h("p", null, T.refus.sdk), /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.refus.attendu), " ", /* @__PURE__ */ h(Donnee, { valeur: SDK_ATTENDU, mono: true }), " ", /* @__PURE__ */ h("span", null, T.commun.separateur), " ", /* @__PURE__ */ h("span", null, T.refus.trouve), " ", /* @__PURE__ */ h(Donnee, { valeur: trouve, mono: true })));
    };
  }

  // src/installer.ts
  function installer(enregistrement) {
    const registre = window.__HERMES_PLUGINS__;
    if (!registre || typeof registre.register !== "function") return null;
    const verdict = verifierSdk(window.__HERMES_PLUGIN_SDK__);
    if (!verdict.ok) {
      console.warn(`[acp] ${enregistrement.nom} d\xE9sactiv\xE9 : SDK du tableau de bord incompatible (trouv\xE9 ${verdict.trouve}).`);
      if (window.__HERMES_PLUGIN_SDK__?.React) {
        const refus = creerRefus(verdict.trouve);
        registre.register(enregistrement.nom, refus);
        if (typeof registre.registerSlot === "function") registre.registerSlot(enregistrement.nom, "header-banner", refus);
      }
      return verdict;
    }
    registre.register(enregistrement.nom, enregistrement.page);
    for (const [emplacement, composant] of enregistrement.emplacements ?? []) {
      registre.registerSlot(enregistrement.nom, emplacement, composant);
    }
    return verdict;
  }

  // src/projets/api.ts
  var RACINE_POSTE = "/api/plugins/acp-poste/v1";
  var ROUTE_PROJETS = `${RACINE_POSTE}/projets`;
  var ROUTE_QUESTIONS = `${RACINE_POSTE}/questions`;
  var ROUTE_POSTE = `${RACINE_POSTE}/poste`;
  var ROUTE_PAUSE = `${RACINE_POSTE}/pause`;
  var ROUTE_NOTIFICATION_TEST = `${RACINE_POSTE}/notifications/test`;
  var segment = (valeur) => encodeURIComponent(valeur);
  var routeProjet = (id) => `${ROUTE_PROJETS}/${segment(id)}`;
  var routePauseProjet = (id) => `${routeProjet(id)}/pause`;
  var routeRepriseProjet = (id) => `${routeProjet(id)}/reprise`;
  var routeReponse = (question) => `${ROUTE_QUESTIONS}/${segment(question)}/reponse`;
  var routeReprendreTriage = (tableau, carte) => `${RACINE_POSTE}/triage/${segment(tableau)}/${segment(carte)}/reprendre`;
  async function ecrireJSON(url, corps, entetes = {}) {
    const fetchJSON = sdk().fetchJSON;
    if (typeof fetchJSON !== "function") throw new ErreurApi("inattendue", null, "fetchJSON absent du SDK");
    try {
      return await fetchJSON(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...entetes },
        body: JSON.stringify(corps ?? {})
      });
    } catch (erreur) {
      throw envelopper(erreur);
    }
  }
  function messageDuRefus(erreur) {
    const texte = erreur.detail.trim();
    if (!texte.startsWith("{")) return null;
    try {
      const corps = JSON.parse(texte);
      const detail = corps?.detail;
      if (typeof detail === "string" && detail.trim()) return detail.trim();
      if (detail && typeof detail === "object") {
        const message = detail.message;
        if (typeof message === "string" && message.trim()) return message.trim();
      }
    } catch {
      return null;
    }
    return null;
  }
  function nouvelleCle() {
    const c = globalThis.crypto;
    if (c && typeof c.randomUUID === "function") return c.randomUUID();
    const octets = new Uint8Array(16);
    if (c && typeof c.getRandomValues === "function") c.getRandomValues(octets);
    else for (let i = 0; i < octets.length; i += 1) octets[i] = Math.floor(Math.random() * 256);
    return [...octets].map((o) => o.toString(16).padStart(2, "0")).join("");
  }
  var lireProjets = () => lireJSON(ROUTE_PROJETS);
  var lireProjet = (id) => lireJSON(routeProjet(id));
  var lireQuestions = () => lireJSON(ROUTE_QUESTIONS);
  var lirePoste = () => lireJSON(ROUTE_POSTE);
  var lancerProjet = (demande, cle) => ecrireJSON(ROUTE_PROJETS, demande, { "Idempotency-Key": cle });
  var pauseProjet = (id) => ecrireJSON(routePauseProjet(id), {});
  var repriseProjet = (id) => ecrireJSON(routeRepriseProjet(id), {});
  var repondreQuestion = (question, reponse) => ecrireJSON(routeReponse(question), { reponse });
  var reprendreTriage = (tableau, carte, consigne) => ecrireJSON(routeReprendreTriage(tableau, carte), consigne ? { consigne } : {});
  var pauseGenerale = (generale) => ecrireJSON(ROUTE_PAUSE, { generale });
  var notificationDeTest = () => ecrireJSON(ROUTE_NOTIFICATION_TEST, {});

  // src/types.ts
  function chaine(valeur) {
    return typeof valeur === "string" && valeur.trim() ? valeur : null;
  }
  function listeDeChaines(valeur) {
    return Array.isArray(valeur) ? valeur.filter((v) => typeof v === "string" && v.trim() !== "") : [];
  }

  // src/format.ts
  var FUSEAU = "Europe/Paris";
  var relatif = new Intl.RelativeTimeFormat("fr-FR", { numeric: "auto" });
  var absolu = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short", timeZone: FUSEAU });
  var nombres = new Intl.NumberFormat("fr-FR");
  function versMillisecondes(valeur) {
    if (typeof valeur !== "number" || !Number.isFinite(valeur) || valeur <= 0) return null;
    return valeur < 1e12 ? valeur * 1e3 : valeur;
  }
  var PALIERS = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 30],
    ["month", 12],
    ["year", Number.POSITIVE_INFINITY]
  ];
  function dateRelative(valeur, maintenant = Date.now()) {
    const ms = versMillisecondes(valeur);
    if (ms === null) return null;
    let ecart = (ms - maintenant) / 1e3;
    for (const [unite, taille] of PALIERS) {
      if (Math.abs(ecart) < taille) return relatif.format(Math.round(ecart), unite);
      ecart /= taille;
    }
    return null;
  }
  function dateAbsolue(valeur) {
    const ms = versMillisecondes(valeur);
    return ms === null ? null : absolu.format(new Date(ms));
  }
  function isoVersMillisecondes(valeur) {
    if (typeof valeur !== "string" || !/^\d{4}-\d{2}-\d{2}T/.test(valeur)) return null;
    const ms = Date.parse(valeur);
    return Number.isFinite(ms) ? ms : null;
  }
  function nombre(valeur) {
    return typeof valeur === "number" && Number.isFinite(valeur) ? nombres.format(valeur) : null;
  }

  // src/projets/libelles.ts
  var L = (texte, famille) => ({ texte, famille });
  function libelleEtatProjet(etat, derive) {
    const e = T.projets.etats;
    switch (etat) {
      case "creation":
        return L(e.creation, "neutre");
      case "en_pause":
        return L(e.enPause, "neutre");
      case "termine":
        return L(e.termine, "succes");
      case "abandonne":
        return L(e.abandonne, "echec");
      case "actif":
        switch (derive) {
          case "exploration":
            return L(e.exploration, "actif");
          case "planification":
            return L(e.planification, "actif");
          case "synthese":
            return L(e.synthese, "actif");
          case "en_cours":
            return L(e.enCours, "actif");
          case "en_attente_du_poste":
            return L(e.enAttenteDuPoste, "degrade");
          case "plafond_atteint":
            return L(e.plafondAtteint, "degrade");
          default:
            return L(e.actif, "actif");
        }
      default:
        return null;
    }
  }
  function libelleStatut(statut) {
    const s = T.projets.statuts;
    switch (statut) {
      case "triage":
        return L(s.triage, "degrade");
      case "todo":
        return L(s.todo, "neutre");
      case "scheduled":
        return L(s.scheduled, "neutre");
      case "ready":
        return L(s.ready, "neutre");
      case "running":
        return L(s.running, "actif");
      case "blocked":
        return L(s.blocked, "echec");
      case "review":
        return L(s.review, "actif");
      case "done":
        return L(s.done, "succes");
      case "archived":
        return L(s.archived, "neutre");
      case "a_creer":
        return L(s.aCreer, "neutre");
      default:
        return null;
    }
  }
  function libelleEtatPoste(etat) {
    const p = T.projets.etatsPoste;
    switch (etat) {
      case "non_configure":
        return L(p.nonConfigure, "neutre");
      case "en_ligne":
        return L(p.enLigne, "succes");
      case "hors_ligne":
        return L(p.horsLigne, "degrade");
      default:
        return null;
    }
  }
  function libelleEtatQuestion(etat) {
    const q = T.projets.etatsQuestion;
    if (etat === "ouverte") return L(q.ouverte, "actif");
    if (etat === "escaladee") return L(q.escaladee, "degrade");
    return null;
  }
  var ORDRE_DES_ROLES = [
    "exploration",
    "planification",
    "implementation",
    "relecture",
    "correction",
    "hermes",
    "synthese",
    "repondre",
    "triage"
  ];
  function libelleRole(role) {
    const r = T.projets.roles;
    const table = {
      exploration: r.exploration,
      planification: r.planification,
      implementation: r.implementation,
      relecture: r.relecture,
      correction: r.correction,
      hermes: r.hermes,
      synthese: r.synthese,
      repondre: r.repondre,
      triage: r.triage
    };
    return typeof role === "string" ? table[role] ?? null : null;
  }
  function libelleVoie(voie) {
    const v = T.projets.voies;
    if (voie === "hermes") return v.hermes;
    if (voie === "poste-codex") return v.posteCodex;
    if (voie === "poste-claude") return v.posteClaude;
    return null;
  }
  function libelleProfil(profil) {
    const c = T.catalogue;
    const table = {
      base: c.profilBase,
      web: c.profilWeb,
      recherche: c.profilRecherche,
      donnees: c.profilDonnees
    };
    return typeof profil === "string" ? table[profil] ?? null : null;
  }
  function libelleReponses(reponses) {
    if (reponses === "hermes_d_abord") return T.projets.reponsesHermes;
    if (reponses === "proprietaire") return T.projets.reponsesProprietaire;
    return null;
  }
  function libelleCanal(canal) {
    if (canal === "aucune") return T.projets.canalAucun;
    if (canal === "telegram") return T.projets.canalTelegram;
    if (canal === "ntfy") return T.projets.canalNtfy;
    return null;
  }
  function libelleOrigine(origine) {
    if (origine === "tableau_de_bord") return T.projets.origineTableau;
    if (origine === "discussion") return T.projets.origineDiscussion;
    return null;
  }

  // src/projets/vue.ts
  var CHEMIN_PAGE = "/projets";
  var IDENTIFIANT = /^[A-Za-z0-9_-]{1,80}$/;
  function vueDepuisAdresse(recherche) {
    const parametres = new URLSearchParams(recherche);
    const projet = parametres.get("projet");
    if (projet && IDENTIFIANT.test(projet)) return { genre: "detail", id: projet };
    const vue = parametres.get("vue");
    if (vue === "questions") return { genre: "questions" };
    if (vue === "nouveau") return { genre: "nouveau" };
    return { genre: "liste" };
  }
  function rechercheDeVue(vue, recherche = "") {
    const parametres = new URLSearchParams(recherche);
    parametres.delete("projet");
    parametres.delete("vue");
    if (vue.genre === "detail") parametres.set("projet", vue.id);
    else if (vue.genre !== "liste") parametres.set("vue", vue.genre);
    const texte = parametres.toString();
    return texte ? `?${texte}` : "";
  }
  function remplacerAdresse(vue) {
    try {
      const { pathname, search } = window.location;
      window.history.replaceState(window.history.state, "", `${pathname}${rechercheDeVue(vue, search)}`);
    } catch {
    }
  }
  function memeVue(a, b) {
    return a.genre === b.genre && (a.genre !== "detail" || b.genre === "detail" && a.id === b.id);
  }

  // src/projets/briques.tsx
  function LienVue(props) {
    const adresse = `${cheminDeBase()}${CHEMIN_PAGE}${rechercheDeVue(props.vue)}`;
    const surClic = (evenement) => {
      if (evenement.defaultPrevented || evenement.button !== 0) return;
      if (evenement.metaKey || evenement.ctrlKey || evenement.shiftKey || evenement.altKey) return;
      evenement.preventDefault();
      props.naviguer(props.vue);
    };
    return /* @__PURE__ */ h(
      "a",
      {
        className: props.className ?? "acp-lien",
        href: adresse,
        "aria-current": props.courant ? "page" : void 0,
        onClick: surClic
      },
      props.children
    );
  }
  function Etiquette(props) {
    if (props.libelle) {
      return /* @__PURE__ */ h("span", { className: `acp-pastille acp-pastille--${props.libelle.famille}` }, props.libelle.texte);
    }
    return /* @__PURE__ */ h(Donnee, { valeur: typeof props.brut === "string" ? props.brut : null, mono: true });
  }
  function BlocRefus(props) {
    const message = messageDuRefus(props.erreur);
    if (!message) return /* @__PURE__ */ h(BlocErreur, { erreur: props.erreur });
    return /* @__PURE__ */ h("div", { className: "acp-erreur", role: "alert" }, /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: message })), props.erreur.statut !== null ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.erreurs.code), " ", /* @__PURE__ */ h(Donnee, { valeur: props.erreur.statut, mono: true })) : null);
  }
  function RetourEnvoi(props) {
    const { etat } = props;
    if (etat.etat === "envoi") {
      return /* @__PURE__ */ h("p", { className: "acp-discret", role: "status" }, T.projets.envoi);
    }
    if (etat.etat === "erreur") return /* @__PURE__ */ h(BlocRefus, { erreur: etat.erreur });
    if (etat.etat === "ok" && props.reussite) {
      return /* @__PURE__ */ h("p", { className: "acp-succes", role: "status" }, props.reussite);
    }
    return null;
  }
  function Horodatage(props) {
    const ms = versMillisecondes(props.valeur) ?? isoVersMillisecondes(props.valeur);
    if (ms === null) return /* @__PURE__ */ h(Donnee, { valeur: null });
    return /* @__PURE__ */ h("time", { dateTime: new Date(ms).toISOString() }, /* @__PURE__ */ h(Donnee, { valeur: props.relative ? dateRelative(ms) : dateAbsolue(ms) }));
  }
  function EtatDuPoste(props) {
    const poste = props.poste;
    const libelle = libelleEtatPoste(poste?.etat);
    return /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle, brut: poste?.etat }), poste?.etat === "hors_ligne" ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.depuis), " ", /* @__PURE__ */ h(Horodatage, { valeur: poste.hors_ligne_depuis })) : null);
  }
  function Bouton(props) {
    const classes = ["acp-bouton"];
    if (props.principal) classes.push("acp-bouton--principal");
    if (props.danger) classes.push("acp-bouton--danger");
    return /* @__PURE__ */ h(
      "button",
      {
        type: props.type ?? "button",
        className: classes.join(" "),
        onClick: props.surClic,
        disabled: props.desactive,
        "aria-describedby": props.decritPar
      },
      props.libelle
    );
  }

  // src/projets/envoi.ts
  function useEnvoi() {
    const [etat, fixer] = useState({ etat: "repos" });
    const enCours = useRef(false);
    const envoyer = async (travail) => {
      if (enCours.current) return null;
      enCours.current = true;
      fixer({ etat: "envoi" });
      try {
        const resultat = await travail();
        fixer({ etat: "ok", resultat });
        return resultat;
      } catch (erreur) {
        fixer({ etat: "erreur", erreur: envelopper(erreur) });
        return null;
      } finally {
        enCours.current = false;
      }
    };
    return { etat, envoyer, oublier: () => fixer({ etat: "repos" }) };
  }

  // src/projets/BandeauPause.tsx
  function BandeauPause(props) {
    const envoi = useEnvoi();
    const reprendre = async () => {
      if (await envoi.envoyer(() => pauseGenerale(false)) !== null) props.apres();
    };
    return /* @__PURE__ */ h("section", { className: "acp-banniere acp-banniere--pause", "aria-labelledby": "acp-pause-titre", "data-acp-pause": "" }, /* @__PURE__ */ h("h2", { className: "acp-banniere__titre", id: "acp-pause-titre" }, T.projets.pauseEnCours), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.pauseEffet), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, T.projets.raison), /* @__PURE__ */ h("dd", null, /* @__PURE__ */ h(Donnee, { valeur: chaine(props.pause.reason) }))), /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, T.projets.depuisLe), /* @__PURE__ */ h("dd", null, /* @__PURE__ */ h(Horodatage, { valeur: props.pause.engaged_at })))), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.projets.reprendreHermes, principal: true, surClic: reprendre, desactive: envoi.etat.etat === "envoi" })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }));
  }
  function CommandePause(props) {
    const [confirmation, fixerConfirmation] = useState(false);
    const envoi = useEnvoi();
    const confirmer = async () => {
      if (await envoi.envoyer(() => pauseGenerale(true)) !== null) {
        fixerConfirmation(false);
        props.apres();
      }
    };
    return /* @__PURE__ */ h(Carte, { titre: T.projets.pauseTitre, id: "acp-projets-pause" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.pauseExplication), confirmation ? /* @__PURE__ */ h("div", { className: "acp-confirmation", role: "group", "aria-labelledby": "acp-pause-question" }, /* @__PURE__ */ h("p", { id: "acp-pause-question" }, T.projets.pauseQuestion), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.projets.pauseConfirmer, danger: true, surClic: confirmer, desactive: envoi.etat.etat === "envoi" }), /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.projets.annuler,
        surClic: () => {
          fixerConfirmation(false);
          envoi.oublier();
        }
      }
    ))) : /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.projets.pauseGenerale, danger: true, surClic: () => fixerConfirmation(true) })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }));
  }

  // src/projets/Notifications.tsx
  function Notifications(props) {
    const etat = props.etat ?? null;
    const envoi = useEnvoi();
    const configure = etat?.configure === true;
    const canal = etat?.connu ? etat.canal : null;
    const libelle = libelleCanal(canal);
    const message = envoi.etat.etat === "ok" ? chaine(envoi.etat.resultat?.message) : null;
    return /* @__PURE__ */ h(Carte, { titre: T.projets.notificationsTitre, id: "acp-projets-notifications" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.canal }, libelle ? /* @__PURE__ */ h("span", null, libelle) : /* @__PURE__ */ h(Donnee, { valeur: chaine(canal), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.etatNotifications }, /* @__PURE__ */ h(
      Etiquette,
      {
        libelle: etat?.connu !== true ? null : configure ? { texte: T.projets.notificationsActives, famille: "succes" } : { texte: T.projets.notificationsInactives, famille: "neutre" }
      }
    ))), configure ? null : /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-notifications-note" }, T.projets.notificationsNonConfigurees), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.projets.envoyerTest,
        desactive: !configure || envoi.etat.etat === "envoi",
        decritPar: configure ? void 0 : "acp-notifications-note",
        surClic: () => void envoi.envoyer(notificationDeTest)
      }
    )), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }), message ? /* @__PURE__ */ h("p", { className: "acp-succes", role: "status" }, /* @__PURE__ */ h(Donnee, { valeur: message })) : null);
  }

  // src/projets/ListeProjets.tsx
  var entier = (v) => typeof v === "number" && Number.isInteger(v) && v >= 0 ? v : null;
  function Avancement(props) {
    const faites = entier(props.faites);
    const total = entier(props.total);
    const part = faites !== null && total !== null && total > 0 ? Math.min(100, Math.round(100 * faites / total)) : 0;
    return /* @__PURE__ */ h("span", { className: "acp-avancement" }, /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: nombre(faites) }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.sur), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(total) })), /* @__PURE__ */ h("span", { className: "acp-barre", "aria-hidden": "true" }, /* @__PURE__ */ h("span", { className: "acp-barre__plein", style: { width: `${part}%` } })));
  }
  function DerniereNote(props) {
    const note = chaine(props.projet.derniere_note);
    if (note) return /* @__PURE__ */ h(Donnee, { valeur: note });
    if (entier(props.projet.compteurs?.faites) === 0) return /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.aucuneNote);
    return /* @__PURE__ */ h(Donnee, { valeur: null });
  }
  function CarteDeProjet(props) {
    const { projet } = props;
    const id = chaine(projet.id);
    const compteurs = projet.compteurs ?? {};
    const questions = entier(projet.questions_ouvertes);
    return /* @__PURE__ */ h("li", { className: "acp-entree acp-projet" }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, id ? /* @__PURE__ */ h(LienVue, { vue: { genre: "detail", id }, naviguer: props.naviguer, className: "acp-lien acp-lien--titre" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(projet.titre) })) : /* @__PURE__ */ h(Donnee, { valeur: chaine(projet.titre) })), /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatProjet(projet.etat, projet.etat_derive), brut: projet.etat }), questions !== null && questions > 0 ? /* @__PURE__ */ h("span", { className: "acp-pastille acp-pastille--degrade" }, /* @__PURE__ */ h("span", null, T.projets.questionsEnAttente), " ", /* @__PURE__ */ h(Donnee, { valeur: questions })) : null), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.cartesFaites }, /* @__PURE__ */ h(Avancement, { faites: compteurs.faites, total: compteurs.total })), entier(compteurs.en_attente_du_poste) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.enAttenteDuPoste }, /* @__PURE__ */ h(Donnee, { valeur: nombre(compteurs.en_attente_du_poste) })) : null, entier(compteurs.bloquees) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.bloquees }, /* @__PURE__ */ h(Donnee, { valeur: nombre(compteurs.bloquees) })) : null, entier(compteurs.triage) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.enTriage }, /* @__PURE__ */ h(Donnee, { valeur: nombre(compteurs.triage) })) : null, /* @__PURE__ */ h(Ligne, { libelle: T.projets.poste }, /* @__PURE__ */ h(EtatDuPoste, { poste: props.poste })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.derniereNote }, /* @__PURE__ */ h(DerniereNote, { projet })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.creeLe }, /* @__PURE__ */ h(Horodatage, { valeur: projet.cree_le, relative: true }))));
  }
  function CartePoste(props) {
    const poste = props.poste;
    return /* @__PURE__ */ h(Carte, { titre: T.projets.posteTitre, id: "acp-projets-poste" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.etat }, /* @__PURE__ */ h(EtatDuPoste, { poste })), chaine(poste?.machine) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.machine }, /* @__PURE__ */ h(Donnee, { valeur: chaine(poste?.machine), mono: true })) : null, poste?.derniere_vue ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.derniereVue }, /* @__PURE__ */ h(Horodatage, { valeur: poste.derniere_vue })) : null, /* @__PURE__ */ h(Ligne, { libelle: T.projets.cartesEnAttente }, /* @__PURE__ */ h(Donnee, { valeur: nombre(poste?.cartes_en_attente) }))), chaine(poste?.message) ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(poste?.message) })) : null);
  }
  function ListeProjets(props) {
    const { donnees } = props;
    const projets = Array.isArray(donnees.projets) ? donnees.projets : [];
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h(Carte, { titre: T.projets.vosProjets, id: "acp-projets-liste" }, /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(LienVue, { vue: { genre: "nouveau" }, naviguer: props.naviguer, className: "acp-bouton acp-bouton--principal" }, T.projets.nouveauProjet)), projets.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucunProjet) : /* @__PURE__ */ h("ul", { className: "acp-entrees" }, projets.map((p, rang) => /* @__PURE__ */ h(CarteDeProjet, { key: chaine(p.id) ?? String(rang), projet: p, poste: donnees.poste, naviguer: props.naviguer })))), /* @__PURE__ */ h("div", { className: "acp-grille" }, /* @__PURE__ */ h(CartePoste, { poste: donnees.poste }), /* @__PURE__ */ h(Notifications, { etat: donnees.notifications }), donnees.pause_generale ? null : /* @__PURE__ */ h(CommandePause, { apres: props.apres })));
  }

  // src/projets/sondage.ts
  var INTERVALLE_SONDAGE_MS = 15e3;
  function visible() {
    return typeof document === "undefined" || document.visibilityState !== "hidden";
  }
  function useSondage(charger, cle, intervalle = INTERVALLE_SONDAGE_MS) {
    const [etat, fixer] = useState({ valeur: null, erreur: null, luLe: null });
    const lecteur = useRef(charger);
    lecteur.current = charger;
    useEffect(() => {
      let actif = true;
      let numero = 0;
      let minuterie = null;
      const arreter = () => {
        if (minuterie !== null) clearTimeout(minuterie);
        minuterie = null;
      };
      const planifier = () => {
        arreter();
        if (actif && visible()) minuterie = setTimeout(lire, intervalle);
      };
      function lire() {
        arreter();
        const ce = numero += 1;
        lecteur.current().then(
          (valeur) => {
            if (actif && ce === numero) fixer({ valeur, erreur: null, luLe: Date.now() });
          },
          (erreur) => {
            if (actif && ce === numero) fixer((avant) => ({ ...avant, erreur: envelopper(erreur) }));
          }
        ).finally(() => {
          if (ce === numero) planifier();
        });
      }
      const surVisibilite = () => {
        if (visible()) lire();
        else arreter();
      };
      lire();
      document.addEventListener("visibilitychange", surVisibilite);
      return () => {
        actif = false;
        arreter();
        document.removeEventListener("visibilitychange", surVisibilite);
      };
    }, [cle, intervalle]);
    return etat;
  }

  // src/projets/DetailProjet.tsx
  function Libre(props) {
    return props.texte ? /* @__PURE__ */ h("span", null, props.texte) : /* @__PURE__ */ h(Donnee, { valeur: chaine(props.brut), mono: props.mono });
  }
  function EnTete(props) {
    const { projet } = props;
    const id = chaine(projet.id);
    const envoi = useEnvoi();
    const geste = async (travail) => {
      if (await envoi.envoyer(travail) !== null) props.apres();
    };
    const plafonds = projet.plafonds ?? {};
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": "acp-projet-titre" }, /* @__PURE__ */ h("h2", { className: "acp-carte__titre acp-carte__titre--grand", id: "acp-projet-titre" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(projet.titre) })), /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatProjet(projet.etat, projet.etat_derive), brut: projet.etat })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.objectif }, /* @__PURE__ */ h(Donnee, { valeur: chaine(projet.objectif) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.cartesFaites }, /* @__PURE__ */ h(Avancement, { faites: projet.compteurs?.faites, total: projet.compteurs?.total })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.tour }, /* @__PURE__ */ h(Donnee, { valeur: nombre(projet.tour) }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.sur), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(plafonds.tours) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.cartesCreees }, /* @__PURE__ */ h(Donnee, { valeur: nombre(projet.cartes_creees) }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.sur), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(plafonds.cartes) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.correctionsParEtape }, /* @__PURE__ */ h(Donnee, { valeur: nombre(plafonds.corrections) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.profil }, /* @__PURE__ */ h(Libre, { texte: libelleProfil(projet.profil), brut: projet.profil, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.depot }, projet.depot === null ? /* @__PURE__ */ h("span", null, T.projets.sansDepot) : /* @__PURE__ */ h(Donnee, { valeur: chaine(projet.depot), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.reponses }, /* @__PURE__ */ h(Libre, { texte: libelleReponses(projet.reponses), brut: projet.reponses, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.poste }, /* @__PURE__ */ h(EtatDuPoste, { poste: props.liste?.poste })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.origine }, /* @__PURE__ */ h(Libre, { texte: libelleOrigine(projet.origine), brut: projet.origine, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.creeLe }, /* @__PURE__ */ h(Horodatage, { valeur: projet.cree_le })), projet.termine_le ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.termineLe }, /* @__PURE__ */ h(Horodatage, { valeur: projet.termine_le })) : null), id && (projet.etat === "actif" || projet.etat === "en_pause") ? /* @__PURE__ */ h("div", { className: "acp-actions" }, projet.etat === "actif" ? /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.projets.mettreEnPause,
        desactive: envoi.etat.etat === "envoi",
        surClic: () => void geste(() => pauseProjet(id))
      }
    ) : /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.projets.reprendre,
        principal: true,
        desactive: envoi.etat.etat === "envoi",
        surClic: () => void geste(() => repriseProjet(id))
      }
    )) : null, /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }));
  }
  function CarteDuGraphe(props) {
    const { carte } = props;
    const resume = chaine(carte.resume);
    return /* @__PURE__ */ h("li", { className: "acp-entree" }, /* @__PURE__ */ h("h4", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.titre) })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.statut }, /* @__PURE__ */ h(Etiquette, { libelle: libelleStatut(carte.statut), brut: carte.statut })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.voie }, /* @__PURE__ */ h(Libre, { texte: libelleVoie(carte.voie), brut: carte.voie, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.tour }, /* @__PURE__ */ h(Donnee, { valeur: nombre(carte.tour) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.modeleDemande }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.modele), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.effort }, chaine(carte.effort) ? /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.effort), mono: true }) : /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.effortParDefaut)), /* @__PURE__ */ h(Ligne, { libelle: T.projets.palier }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.palier), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.modeleServi }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.modele_servi) })), chaine(carte.mention) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.mention }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.mention) })) : null, chaine(carte.carte) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.carte }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.carte), mono: true })) : null), resume ? /* @__PURE__ */ h("details", { className: "acp-details" }, /* @__PURE__ */ h("summary", null, T.projets.resume), /* @__PURE__ */ h("p", { className: "acp-texte-long" }, /* @__PURE__ */ h(Donnee, { valeur: resume }))) : null);
  }
  function Cartes(props) {
    const groupes = /* @__PURE__ */ new Map();
    for (const carte of props.cartes) {
      const role = chaine(carte.role) ?? "";
      groupes.set(role, [...groupes.get(role) ?? [], carte]);
    }
    const connus = [...ORDRE_DES_ROLES];
    const roles = [...connus.filter((r) => groupes.has(r)), ...[...groupes.keys()].filter((r) => !connus.includes(r))];
    return /* @__PURE__ */ h(Carte, { titre: T.projets.cartes, id: "acp-projet-cartes" }, props.cartes.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucuneCarte) : null, roles.map((role) => /* @__PURE__ */ h("div", { key: role || "?", className: "acp-groupe" }, /* @__PURE__ */ h("h3", { className: "acp-sous-titre" }, /* @__PURE__ */ h(Libre, { texte: libelleRole(role), brut: role, mono: true })), /* @__PURE__ */ h("ul", { className: "acp-entrees" }, (groupes.get(role) ?? []).map((c, rang) => /* @__PURE__ */ h(CarteDuGraphe, { key: chaine(c.carte) ?? `${role}-${rang}`, carte: c }))))));
  }
  function Tours(props) {
    const tours = Array.isArray(props.projet.tours) ? props.projet.tours : [];
    if (tours.length === 0) return null;
    return /* @__PURE__ */ h(Carte, { titre: T.projets.toursTitre, id: "acp-projet-tours" }, tours.map((t, rang) => {
      const decisions = listeDeChaines(t.decisions);
      return /* @__PURE__ */ h("div", { key: String(t.tour ?? rang), className: "acp-groupe" }, /* @__PURE__ */ h("h3", { className: "acp-sous-titre" }, /* @__PURE__ */ h("span", null, T.projets.tour), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(t.tour) })), /* @__PURE__ */ h("p", { className: "acp-texte-long" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(t.resume) })), decisions.length > 0 ? /* @__PURE__ */ h("div", null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.decisions), /* @__PURE__ */ h("ul", { className: "acp-noms" }, decisions.map((d, i) => /* @__PURE__ */ h("li", { key: String(i) }, /* @__PURE__ */ h(Donnee, { valeur: d }))))) : null);
    }));
  }
  function QuestionsDuProjet(props) {
    const questions = Array.isArray(props.projet.questions_ouvertes) ? props.projet.questions_ouvertes : [];
    if (questions.length === 0) return null;
    return /* @__PURE__ */ h(Carte, { titre: T.projets.questionsEnAttente, id: "acp-projet-questions" }, /* @__PURE__ */ h("ul", { className: "acp-noms" }, questions.map((q, rang) => /* @__PURE__ */ h("li", { key: chaine(q.id) ?? String(rang), className: "acp-question-courte" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatQuestion(q.etat), brut: q.etat }), /* @__PURE__ */ h("p", { className: "acp-texte-long" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(q.texte) }))))), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(LienVue, { vue: { genre: "questions" }, naviguer: props.naviguer }, T.projets.voirQuestions)));
  }
  function Journal(props) {
    const journal = Array.isArray(props.projet.journal) ? props.projet.journal : [];
    return /* @__PURE__ */ h(Carte, { titre: T.projets.journal, id: "acp-projet-journal" }, journal.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.journalVide) : /* @__PURE__ */ h("details", { className: "acp-details" }, /* @__PURE__ */ h("summary", null, /* @__PURE__ */ h("span", null, T.projets.journalOuvrir), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(journal.length) })), /* @__PURE__ */ h("ul", { className: "acp-journal" }, journal.map((j, rang) => /* @__PURE__ */ h("li", { key: String(rang) }, /* @__PURE__ */ h(Horodatage, { valeur: j.quand }), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine(j.action), mono: true }), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine(j.acteur), mono: true }), chaine(j.cible) ? /* @__PURE__ */ h("span", null, " ", /* @__PURE__ */ h(Donnee, { valeur: chaine(j.cible), mono: true })) : null, chaine(j.detail) ? /* @__PURE__ */ h("span", { className: "acp-journal__detail" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(j.detail), mono: true })) : null)))));
  }
  function DetailProjet(props) {
    const sondage = useSondage(() => lireProjet(props.id), props.jeton);
    const projet = sondage.valeur?.projet ?? null;
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(LienVue, { vue: { genre: "liste" }, naviguer: props.naviguer }, T.projets.retour)), projet === null && sondage.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : null, sondage.erreur !== null ? /* @__PURE__ */ h(BlocRefus, { erreur: sondage.erreur }) : null, projet !== null ? /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h(EnTete, { projet, liste: props.liste, apres: props.apres }), /* @__PURE__ */ h(QuestionsDuProjet, { projet, naviguer: props.naviguer }), /* @__PURE__ */ h(Cartes, { cartes: Array.isArray(projet.cartes) ? projet.cartes : [] }), /* @__PURE__ */ h(Tours, { projet }), /* @__PURE__ */ h(Journal, { projet })) : null);
  }

  // src/projets/NouveauProjet.tsx
  var valeurDe = (e) => e.target.value;
  var PROFILS_CONNUS = ["base", "web", "recherche", "donnees"];
  function voiesRelevees(catalogue) {
    const voies = catalogue?.voies && typeof catalogue.voies === "object" ? catalogue.voies : {};
    const ordre = listeDeChaines(catalogue?.politique?.voies_par_classe?.exploration);
    const candidates = ordre.length > 0 ? ordre : Object.keys(voies);
    return candidates.filter((v) => voies[v] && voies[v].etat !== "inconnu" && voies[v].releve_le);
  }
  function depotsConnus(catalogue) {
    const voies = catalogue?.voies && typeof catalogue.voies === "object" ? catalogue.voies : {};
    const relevees = Object.values(voies).filter((v) => v && v.etat !== "inconnu" && v.releve_le);
    if (catalogue?.etat !== "connu" || relevees.length === 0) return null;
    const alias = /* @__PURE__ */ new Set();
    for (const v of relevees) for (const d of listeDeChaines(v.depots)) alias.add(d);
    return [...alias].sort();
  }
  function effortsAdmis(voie, modele, interdits) {
    const modeles = Array.isArray(voie?.modeles) ? voie.modeles : [];
    const choisi = modele ? modeles.find((m) => m.id === modele) : modeles.find((m) => m.isDefault) ?? modeles[0];
    return listeDeChaines(choisi?.supportedReasoningEfforts).filter((e) => !interdits.includes(e));
  }
  function Formulaire(props) {
    const cataloguePoste = props.poste?.catalogue ?? null;
    const depots = depotsConnus(cataloguePoste);
    const voies = voiesRelevees(cataloguePoste);
    const interdits = listeDeChaines(cataloguePoste?.politique?.efforts_interdits);
    const profils = (() => {
      const lus = props.catalogue?.profils && typeof props.catalogue.profils === "object" ? Object.keys(props.catalogue.profils) : [];
      return lus.length > 0 ? lus : PROFILS_CONNUS;
    })();
    const [titre, fixerTitre] = useState("");
    const [objectif, fixerObjectif] = useState("");
    const [profil, fixerProfil] = useState(profils.includes("base") ? "base" : profils[0] ?? "base");
    const [reponses, fixerReponses] = useState("hermes_d_abord");
    const [depot, fixerDepot] = useState("");
    const [voie, fixerVoie] = useState(voies[0] ?? "");
    const [modele, fixerModele] = useState("");
    const [effort, fixerEffort] = useState("");
    const [cle, fixerCle] = useState(nouvelleCle);
    const envoi = useEnvoi();
    const releveVoie = voie ? cataloguePoste?.voies?.[voie] : void 0;
    const modeles = Array.isArray(releveVoie?.modeles) ? releveVoie.modeles.filter((m) => chaine(m.id)) : [];
    const efforts = effortsAdmis(releveVoie, modele, interdits);
    const avecExploration = depot !== "" && voies.length > 0;
    const complet = titre.trim() !== "" && objectif.trim() !== "";
    const lancer = async (evenement) => {
      evenement.preventDefault();
      if (!complet) return;
      const demande = {
        titre: titre.trim(),
        objectif: objectif.trim(),
        profil,
        depot: depot || null,
        reponses
      };
      if (avecExploration && voie) {
        demande.exploration = { voie, ...modele ? { modele } : {}, ...effort ? { effort } : {} };
      }
      const resultat = await envoi.envoyer(() => lancerProjet(demande, cle));
      const id = chaine(resultat?.projet?.id);
      if (resultat !== null) {
        fixerCle(nouvelleCle());
        props.apres();
        if (id) props.naviguer({ genre: "detail", id });
      }
    };
    return /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: (e) => void lancer(e), "aria-labelledby": "acp-nouveau-titre" }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-titre-champ" }, T.projets.champTitre), /* @__PURE__ */ h(
      "input",
      {
        id: "acp-projet-titre-champ",
        type: "text",
        "data-acp-donnee": "",
        maxLength: 120,
        required: true,
        value: titre,
        onChange: (e) => fixerTitre(valeurDe(e))
      }
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-objectif" }, T.projets.champObjectif), /* @__PURE__ */ h(
      "textarea",
      {
        id: "acp-projet-objectif",
        "data-acp-donnee": "",
        rows: 5,
        maxLength: 4e3,
        required: true,
        "aria-describedby": "acp-projet-objectif-aide",
        value: objectif,
        onChange: (e) => fixerObjectif(valeurDe(e))
      }
    ), /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-projet-objectif-aide" }, T.projets.aideObjectif)), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-profil" }, T.projets.champProfil), /* @__PURE__ */ h("select", { id: "acp-projet-profil", value: profil, onChange: (e) => fixerProfil(valeurDe(e)) }, profils.map(
      (p) => libelleProfil(p) ? /* @__PURE__ */ h("option", { key: p, value: p }, libelleProfil(p)) : /* @__PURE__ */ h("option", { key: p, value: p, "data-acp-donnee": "" }, p)
    ))), /* @__PURE__ */ h("fieldset", { className: "acp-groupe-choix" }, /* @__PURE__ */ h("legend", null, T.projets.champReponses), /* @__PURE__ */ h("label", { className: "acp-choix-radio" }, /* @__PURE__ */ h(
      "input",
      {
        type: "radio",
        name: "acp-projet-reponses",
        value: "hermes_d_abord",
        checked: reponses === "hermes_d_abord",
        onChange: () => fixerReponses("hermes_d_abord")
      }
    ), /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-choix-radio__titre" }, T.projets.reponsesHermes), /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.reponsesHermesAide))), /* @__PURE__ */ h("label", { className: "acp-choix-radio" }, /* @__PURE__ */ h(
      "input",
      {
        type: "radio",
        name: "acp-projet-reponses",
        value: "proprietaire",
        checked: reponses === "proprietaire",
        onChange: () => fixerReponses("proprietaire")
      }
    ), /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-choix-radio__titre" }, T.projets.reponsesProprietaire), /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.reponsesProprietaireAide)))), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-depot" }, T.projets.champDepot), /* @__PURE__ */ h(
      "select",
      {
        id: "acp-projet-depot",
        value: depot,
        disabled: depots === null,
        "aria-describedby": depots === null ? "acp-projet-depot-aide" : void 0,
        onChange: (e) => fixerDepot(valeurDe(e))
      },
      /* @__PURE__ */ h("option", { value: "" }, T.projets.sansDepot),
      (depots ?? []).map((d) => /* @__PURE__ */ h("option", { key: d, value: d, "data-acp-donnee": "" }, d))
    ), depots === null ? /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-projet-depot-aide" }, T.projets.aucunDepotConnu) : null), cataloguePoste?.releve_factice === true ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "note" }, T.projets.releveFactice) : null, avecExploration ? /* @__PURE__ */ h("fieldset", { className: "acp-groupe-choix" }, /* @__PURE__ */ h("legend", null, T.projets.exploration), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.explorationAide), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-voie" }, T.projets.champVoie), /* @__PURE__ */ h(
      "select",
      {
        id: "acp-projet-voie",
        value: voie,
        onChange: (e) => {
          fixerVoie(valeurDe(e));
          fixerModele("");
          fixerEffort("");
        }
      },
      voies.map(
        (v) => libelleVoie(v) ? /* @__PURE__ */ h("option", { key: v, value: v }, libelleVoie(v)) : /* @__PURE__ */ h("option", { key: v, value: v, "data-acp-donnee": "" }, v)
      )
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-modele" }, T.projets.champModele), /* @__PURE__ */ h(
      "select",
      {
        id: "acp-projet-modele",
        value: modele,
        onChange: (e) => {
          fixerModele(valeurDe(e));
          fixerEffort("");
        }
      },
      /* @__PURE__ */ h("option", { value: "" }, T.projets.modeleParDefaut),
      modeles.map((m) => /* @__PURE__ */ h("option", { key: String(m.id), value: String(m.id), "data-acp-donnee": "" }, String(m.id)))
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-effort" }, T.projets.champEffort), /* @__PURE__ */ h("select", { id: "acp-projet-effort", value: effort, onChange: (e) => fixerEffort(valeurDe(e)) }, /* @__PURE__ */ h("option", { value: "" }, T.projets.effortParDefaut), efforts.map((x) => /* @__PURE__ */ h("option", { key: x, value: x, "data-acp-donnee": "" }, x)))), /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.projets.releveDu), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine(releveVoie?.releve_le_lisible) })), releveVoie?.perime === true ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.projets.relevePerime) : null) : null, /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        type: "submit",
        principal: true,
        libelle: envoi.etat.etat === "envoi" ? T.projets.envoi : T.projets.lancer,
        desactive: !complet || envoi.etat.etat === "envoi"
      }
    )), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }));
  }
  function NouveauProjet(props) {
    const catalogue = useChargement(lireCatalogue);
    const poste = useChargement(lirePoste);
    const pret = catalogue.etat !== "chargement" && poste.etat !== "chargement";
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": "acp-nouveau-titre" }, /* @__PURE__ */ h("h2", { className: "acp-carte__titre", id: "acp-nouveau-titre" }, T.projets.nouveauTitre), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.nouveauIntro), !pret ? /* @__PURE__ */ h(EnChargement, null) : null, poste.etat === "erreur" ? /* @__PURE__ */ h(BlocErreur, { erreur: poste.erreur, message: T.projets.posteIndisponible }) : null, catalogue.etat === "erreur" ? /* @__PURE__ */ h(BlocErreur, { erreur: catalogue.erreur, message: T.catalogue.indisponible }) : null, pret ? /* @__PURE__ */ h(
      Formulaire,
      {
        catalogue: catalogue.etat === "ok" ? catalogue.valeur : null,
        poste: poste.etat === "ok" ? poste.valeur : null,
        naviguer: props.naviguer,
        apres: props.apres
      }
    ) : null);
  }

  // src/projets/Questions.tsx
  function LienProjet(props) {
    const id = chaine(props.id);
    const titre = /* @__PURE__ */ h(Donnee, { valeur: chaine(props.titre) });
    return id ? /* @__PURE__ */ h(LienVue, { vue: { genre: "detail", id }, naviguer: props.naviguer }, titre) : titre;
  }
  function Question(props) {
    const { question } = props;
    const id = chaine(question.id);
    const [reponse, fixerReponse] = useState("");
    const envoi = useEnvoi();
    const champ = `acp-reponse-${id ?? "inconnue"}`;
    const repondre = async (evenement) => {
      evenement.preventDefault();
      if (!id || !reponse.trim()) return;
      if (await envoi.envoyer(() => repondreQuestion(id, reponse.trim())) !== null) {
        fixerReponse("");
        props.apres();
      }
    };
    return /* @__PURE__ */ h("li", { className: "acp-entree acp-question" }, /* @__PURE__ */ h("p", { className: "acp-question__texte" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(question.texte) })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.projet }, /* @__PURE__ */ h(LienProjet, { id: question.projet, titre: question.projet_titre, naviguer: props.naviguer })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.etat }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatQuestion(question.etat), brut: question.etat })), chaine(question.motif_escalade) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.motifEscalade }, /* @__PURE__ */ h(Donnee, { valeur: chaine(question.motif_escalade) })) : null, /* @__PURE__ */ h(Ligne, { libelle: T.projets.carte }, /* @__PURE__ */ h(Donnee, { valeur: chaine(question.carte), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.poseeLe }, /* @__PURE__ */ h(Horodatage, { valeur: question.cree_le, relative: true }))), id ? /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: (e) => void repondre(e) }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: champ }, T.projets.votreReponse), /* @__PURE__ */ h(
      "textarea",
      {
        id: champ,
        "data-acp-donnee": "",
        rows: 3,
        maxLength: 4e3,
        value: reponse,
        onChange: (e) => fixerReponse(e.target.value)
      }
    )), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        type: "submit",
        principal: true,
        libelle: T.projets.repondre,
        desactive: !reponse.trim() || envoi.etat.etat === "envoi"
      }
    )), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat, reussite: T.projets.reponseEnvoyee })) : null);
  }
  function Triage(props) {
    const { carte } = props;
    const tableau = chaine(carte.tableau);
    const identifiant = chaine(carte.carte);
    const [consigne, fixerConsigne] = useState("");
    const envoi = useEnvoi();
    const champ = `acp-consigne-${identifiant ?? "inconnue"}`;
    const reprendre = async (evenement) => {
      evenement.preventDefault();
      if (!tableau || !identifiant) return;
      if (await envoi.envoyer(() => reprendreTriage(tableau, identifiant, consigne.trim() || null)) !== null) {
        fixerConsigne("");
        props.apres();
      }
    };
    return /* @__PURE__ */ h("li", { className: "acp-entree" }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.titre) })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.projet }, /* @__PURE__ */ h(LienProjet, { id: carte.projet, titre: carte.projet_titre, naviguer: props.naviguer })), chaine(carte.raison) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.raison }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.raison) })) : null), tableau && identifiant ? /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: (e) => void reprendre(e) }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: champ }, T.projets.consigne), /* @__PURE__ */ h(
      "textarea",
      {
        id: champ,
        "data-acp-donnee": "",
        rows: 3,
        maxLength: 8e3,
        value: consigne,
        onChange: (e) => fixerConsigne(e.target.value)
      }
    )), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { type: "submit", libelle: T.projets.reprendreCarte, desactive: envoi.etat.etat === "envoi" })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat, reussite: T.projets.carteReprise })) : null);
  }
  function Bloquee(props) {
    const { carte } = props;
    return /* @__PURE__ */ h("li", { className: "acp-entree" }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.titre) })), /* @__PURE__ */ h("p", { className: "acp-etat" }, carte.abandonnee === true ? /* @__PURE__ */ h(Etiquette, { libelle: { texte: T.projets.abandonnee, famille: "echec" } }) : /* @__PURE__ */ h(Etiquette, { libelle: { texte: T.projets.statuts.blocked, famille: "echec" } })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.projet }, /* @__PURE__ */ h(LienProjet, { id: carte.projet, titre: carte.projet_titre, naviguer: props.naviguer })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.assigne }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.assigne), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.raison }, /* @__PURE__ */ h(Donnee, { valeur: chaine(carte.raison) }))));
  }
  function Questions(props) {
    const sondage = useSondage(lireQuestions, props.jeton);
    const donnees = sondage.valeur;
    if (donnees === null) {
      return sondage.erreur ? /* @__PURE__ */ h(BlocErreur, { erreur: sondage.erreur, message: T.projets.questionsIndisponibles }) : /* @__PURE__ */ h(EnChargement, null);
    }
    const questions = Array.isArray(donnees.questions) ? donnees.questions : [];
    const triage = Array.isArray(donnees.triage) ? donnees.triage : [];
    const bloquees = Array.isArray(donnees.bloquees) ? donnees.bloquees : [];
    const illisibles = listeDeChaines(donnees.tableaux_illisibles);
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, sondage.erreur ? /* @__PURE__ */ h(BlocRefus, { erreur: sondage.erreur }) : null, /* @__PURE__ */ h(Carte, { titre: T.projets.questionsTitre, id: "acp-questions-ouvertes" }, questions.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucuneQuestion) : /* @__PURE__ */ h("ul", { className: "acp-entrees acp-entrees--une" }, questions.map((q, rang) => /* @__PURE__ */ h(Question, { key: chaine(q.id) ?? String(rang), question: q, naviguer: props.naviguer, apres: props.apres })))), /* @__PURE__ */ h(Carte, { titre: T.projets.triageTitre, id: "acp-questions-triage" }, triage.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucunTriage) : /* @__PURE__ */ h("ul", { className: "acp-entrees acp-entrees--une" }, triage.map((c, rang) => /* @__PURE__ */ h(Triage, { key: chaine(c.carte) ?? String(rang), carte: c, naviguer: props.naviguer, apres: props.apres })))), /* @__PURE__ */ h(Carte, { titre: T.projets.bloqueesTitre, id: "acp-questions-bloquees" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.bloqueesNote), bloquees.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucuneBloquee) : /* @__PURE__ */ h("ul", { className: "acp-entrees" }, bloquees.map((c, rang) => /* @__PURE__ */ h(Bloquee, { key: chaine(c.carte) ?? String(rang), carte: c, naviguer: props.naviguer })))), illisibles.length > 0 ? /* @__PURE__ */ h(Carte, { titre: T.projets.tableauxIllisibles, id: "acp-questions-illisibles" }, /* @__PURE__ */ h("ul", { className: "acp-noms" }, illisibles.map((t) => /* @__PURE__ */ h("li", { key: t }, /* @__PURE__ */ h(Donnee, { valeur: t, mono: true }))))) : null);
  }

  // src/projets/Projets.tsx
  function Navigation(props) {
    const onglets = [
      { vue: { genre: "liste" }, libelle: T.projets.vueListe },
      { vue: { genre: "questions" }, libelle: T.projets.vueQuestions, compte: props.questions },
      { vue: { genre: "nouveau" }, libelle: T.projets.vueNouveau }
    ];
    return /* @__PURE__ */ h("nav", { className: "acp-onglets", "aria-label": T.projets.navigation }, onglets.map((o) => /* @__PURE__ */ h(
      LienVue,
      {
        key: o.vue.genre,
        vue: o.vue,
        naviguer: props.naviguer,
        className: "acp-onglet",
        courant: memeVue(o.vue, props.vue) || o.vue.genre === "liste" && props.vue.genre === "detail"
      },
      /* @__PURE__ */ h("span", null, o.libelle),
      typeof o.compte === "number" && o.compte > 0 ? /* @__PURE__ */ h("span", { className: "acp-compteur" }, /* @__PURE__ */ h(Donnee, { valeur: o.compte })) : null
    )));
  }
  function Projets() {
    const [vue, fixerVue] = useState(() => vueDepuisAdresse(window.location.search));
    const [jeton, fixerJeton] = useState(0);
    const rafraichir = () => fixerJeton((j) => j + 1);
    const liste = useSondage(lireProjets, jeton);
    const racine = useRef(null);
    const naviguer = (suivante) => {
      fixerVue(suivante);
      remplacerAdresse(suivante);
      rafraichir();
      try {
        racine.current?.scrollIntoView?.({ block: "start" });
      } catch {
      }
    };
    const donnees = liste.valeur;
    const questions = typeof donnees?.questions_ouvertes === "number" ? donnees.questions_ouvertes : null;
    const pause = donnees?.pause_generale && typeof donnees.pause_generale === "object" ? donnees.pause_generale : null;
    return /* @__PURE__ */ h("div", { className: "acp-page", "data-acp-racine": "projets", ref: racine }, /* @__PURE__ */ h("div", { className: "acp-entete" }, /* @__PURE__ */ h("h1", { className: "acp-titre" }, T.projets.titre), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.intro)), /* @__PURE__ */ h(Navigation, { vue, naviguer, questions }), pause ? /* @__PURE__ */ h(BandeauPause, { pause, apres: rafraichir }) : null, donnees === null && liste.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : null, donnees === null && liste.erreur !== null ? /* @__PURE__ */ h(BlocErreur, { erreur: liste.erreur, message: T.projets.indisponible }) : null, donnees !== null && liste.erreur !== null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.projets.actualisationImpossible) : null, vue.genre === "liste" && donnees !== null ? /* @__PURE__ */ h(ListeProjets, { donnees, naviguer, apres: rafraichir }) : null, vue.genre === "nouveau" ? /* @__PURE__ */ h(NouveauProjet, { naviguer, apres: rafraichir }) : null, vue.genre === "detail" ? /* @__PURE__ */ h(DetailProjet, { key: vue.id, id: vue.id, jeton, liste: donnees, naviguer, apres: rafraichir }) : null, vue.genre === "questions" ? /* @__PURE__ */ h(Questions, { jeton, naviguer, apres: rafraichir }) : null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.actualisation));
  }

  // src/projets/index.ts
  installer({ nom: "acp-projets", page: Projets });
})();
