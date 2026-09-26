/* acp-interface 0.11.0 (ACP) — bundle généré par apps/interface/esbuild.mjs depuis apps/interface/src ; ne pas modifier à la main. Aucun code tiers embarqué : React vient du SDK du tableau de bord de Hermes. */

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
      notificationsNonConfigurees: "Notifications non configur\xE9es\xA0: leur activation passe par une PR qui d\xE9clare les variables ACP_NOTIFICATIONS\u2026 dans l'IaC Railway (docs/refonte/railway.md, \xA7 9).",
      notificationsEtatInconnu: "\xC9tat du canal inconnu\xA0: la passerelle ne l'a pas encore publi\xE9.",
      envoyerTest: "Envoyer une notification de test",
      pauseTitre: "Pause g\xE9n\xE9rale",
      pauseExplication: "Arr\xEAte le travail autonome de Hermes\xA0: aucune nouvelle carte ne part, les cartes en cours finissent et aucune nouvelle notification d'avancement n'est \xE9mise (celles d\xE9j\xE0 en file et la notification de test partent encore). La discussion avec Hermes reste ouverte\xA0; lancer un projet y est refus\xE9.",
      pauseGenerale: "Pause g\xE9n\xE9rale",
      pauseQuestion: "Mettre Hermes en pause g\xE9n\xE9rale\xA0?",
      pauseConfirmer: "Confirmer la pause g\xE9n\xE9rale",
      annuler: "Annuler",
      pauseEnCours: "Hermes est en pause g\xE9n\xE9rale",
      pauseEffet: "Aucune nouvelle carte ne part tant que vous ne reprenez pas.",
      pauseCrochets: "Pause engag\xE9e par la veille des crochets shell\xA0: retirez la cl\xE9 hooks du config.yaml (et tout shell-hooks-allowlist.json) du volume de Hermes\xA0; la reprise est refus\xE9e tant qu'ils existent.",
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
      reponsesSansObjet: "Sans objet sans d\xE9p\xF4t\xA0: aucune question ne na\xEEt d'un projet sans d\xE9p\xF4t\xA0; s'il manque une information, Hermes bloque une carte avec sa raison (page Questions, cartes bloqu\xE9es).",
      champDepot: "D\xE9p\xF4t",
      sansDepot: "Sans d\xE9p\xF4t",
      aucunDepotConnu: "Aucun d\xE9p\xF4t connu\xA0: le poste n'a encore publi\xE9 aucun inventaire (\xE9tape P5).",
      depotsInconnus: "D\xE9p\xF4ts inconnus\xA0: l'inventaire du poste est illisible (voir l'erreur ci-dessus).",
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
      extrait: "Extrait\xA0:",
      caracteresSur: "caract\xE8res sur",
      lireEnEntier: "Lire le r\xE9sum\xE9 en entier",
      texteBorne: "Texte born\xE9 \xE0 100 000 caract\xE8res par le greffon.",
      resultatTitre: "R\xE9sultat du projet",
      resultatIntro: "Synth\xE8se du dernier tour fait, en entier.",
      palierStandard: "Standard",
      detailTechnique: "D\xE9tail technique",
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
      reponseDifferee: "R\xE9ponse enregistr\xE9e\xA0: la carte reprendra \xE0 la reprise du projet.",
      reponseSansReprise: "R\xE9ponse enregistr\xE9e\xA0; la carte n'a pas \xE9t\xE9 relanc\xE9e (voir le kanban de Hermes).",
      contexte: "Contexte",
      carteDeLaQuestion: "Carte",
      triageTitre: "Cartes en triage",
      aucunTriage: "Aucune carte en triage.",
      consigne: "Consigne (facultative)",
      reprendreCarte: "Reprendre",
      carteReprise: "Carte reprise\xA0: elle repart dans le graphe du projet.",
      carteNonReprise: "La carte n'a pas \xE9t\xE9 reprise (voir le kanban de Hermes).",
      prolonger: "Prolonger",
      relancer: "Relancer la planification",
      conclure: "Conclure le projet",
      prolongerAideTours: "\xAB\xA0Prolonger\xA0\xBB accorde un tour de plus\xA0: Hermes planifie la suite avec votre consigne.",
      prolongerAideCartes: "\xAB\xA0Prolonger\xA0\xBB rel\xE8ve le plafond de cartes\xA0: Hermes planifie la suite avec votre consigne.",
      relancerAide: "\xAB\xA0Relancer la planification\xA0\xBB fait replanifier Hermes avec votre consigne.",
      conclureAide: "\xAB\xA0Conclure le projet\xA0\xBB l'arr\xEAte ici\xA0: \xAB\xA0Termin\xE9\xA0\xBB s'il a au moins un tour, sinon \xAB\xA0Abandonn\xE9\xA0\xBB.",
      prolongerP6: "Prolonger le plafond de corrections arrivera \xE0 l'\xE9tape P6.",
      prolongationFaite: "Plafond relev\xE9\xA0: Hermes planifie la suite avec votre consigne.",
      relanceFaite: "Planification relanc\xE9e\xA0: Hermes planifie avec votre consigne.",
      conclusionFaite: "Projet conclu.",
      noteTronquee: "Extrait\xA0; le d\xE9tail du projet donne les r\xE9sum\xE9s en entier.",
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
        plafondAtteint: "Plafond atteint\xA0: votre d\xE9cision est attendue",
        aDecider: "Votre d\xE9cision est attendue"
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
      },
      actionsJournal: {
        lancement: "Lancement",
        planification: "Tour planifi\xE9",
        planification_annulee: "Planification annul\xE9e",
        pause: "Mise en pause",
        reprise: "Reprise",
        pause_carte: "Carte suspendue par la pause",
        reprise_carte: "Carte reprise",
        question: "Question du poste",
        question_escaladee: "Question transmise au propri\xE9taire",
        question_repondue: "Question r\xE9pondue",
        triage_repris: "D\xE9cision appliqu\xE9e",
        prolongation: "Plafond prolong\xE9",
        relance_planification: "Planification relanc\xE9e",
        conclusion: "Projet conclu",
        plafond: "Plafond atteint",
        sans_plan: "Planification finie sans plan",
        termine: "Projet termin\xE9",
        reparation: "Cr\xE9ation r\xE9par\xE9e",
        surcharge: "Surcharge de routage",
        correction: "Correction ins\xE9r\xE9e"
      },
      acteursJournal: {
        vous: "Vous",
        acp: "ACP",
        poste: "Poste",
        discussion: "Hermes (discussion)",
        carte: "Carte"
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
  var ROUTE_META = "/api/plugins/acp-poste/v1/meta";
  var ROUTE_SESSIONS = "/api/sessions?limit=5&offset=0&order=recent";
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
  var enCours = null;
  function lireMeta(maintenant = Date.now()) {
    if (enCours && maintenant - enCours.quand < 15e3) return enCours.promesse;
    const promesse = lireJSON(ROUTE_META);
    enCours = { quand: maintenant, promesse };
    promesse.catch(() => {
      if (enCours?.promesse === promesse) enCours = null;
    });
    return promesse;
  }
  var lireSessions = () => lireJSON(ROUTE_SESSIONS);

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

  // src/commun.tsx
  var FAMILLES = {
    conforme: "succes",
    connecte: "succes",
    active: "succes",
    activee: "succes",
    aJour: "succes",
    deposee: "succes",
    livree: "succes",
    presente: "succes",
    nonConforme: "degrade",
    divergente: "degrade",
    ambigue: "degrade",
    absente: "echec",
    nonOrdinaire: "echec",
    inconnu: "neutre",
    nonConfigure: "neutre",
    horsLigne: "neutre",
    candidate: "neutre",
    prevueP8: "neutre",
    horsV1: "neutre",
    desactivee: "neutre"
  };
  function Donnee(props) {
    const { valeur, mono } = props;
    if (valeur === null || valeur === void 0 || valeur === "") {
      return /* @__PURE__ */ h("span", { className: "acp-inconnu" }, T.commun.inconnu);
    }
    return /* @__PURE__ */ h("span", { "data-acp-donnee": "", className: mono ? "acp-donnee acp-mono" : "acp-donnee" }, String(valeur));
  }
  function Pastille(props) {
    return /* @__PURE__ */ h("span", { className: `acp-pastille acp-pastille--${FAMILLES[props.etat]}` }, T.etats[props.etat]);
  }
  function Carte(props) {
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": props.id }, /* @__PURE__ */ h("h2", { className: "acp-carte__titre", id: props.id }, props.titre), props.children);
  }
  function Ligne(props) {
    return /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, props.libelle), /* @__PURE__ */ h("dd", null, props.children));
  }
  function Lien(props) {
    return /* @__PURE__ */ h("a", { className: "acp-lien", href: `${cheminDeBase()}${props.vers}`, "aria-label": props.ariaLabel }, props.children);
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
  function nombre(valeur) {
    return typeof valeur === "number" && Number.isFinite(valeur) ? nombres.format(valeur) : null;
  }
  function court(valeur, longueur = 12) {
    if (typeof valeur !== "string" || !valeur) return null;
    const sans = valeur.includes(":") ? valeur.slice(valeur.indexOf(":") + 1) : valeur;
    return sans.slice(0, longueur);
  }

  // src/types.ts
  function chaine(valeur) {
    return typeof valeur === "string" && valeur.trim() ? valeur : null;
  }
  function listeDeChaines(valeur) {
    return Array.isArray(valeur) ? valeur.filter((v) => typeof v === "string" && v.trim() !== "") : [];
  }

  // src/interface/Accueil.tsx
  function etatPersona(meta) {
    switch (meta?.demarrage?.soul?.etat) {
      case "a_jour":
        return "aJour";
      case "depose":
        return "deposee";
      case "divergent":
        return "divergente";
      case "non_ordinaire":
        return "nonOrdinaire";
      default:
        return "inconnu";
    }
  }
  function etatConformite(conforme) {
    return conforme === true ? "conforme" : conforme === false ? "nonConforme" : "inconnu";
  }
  function etatContext7(valeur) {
    return valeur === "connecte" ? "connecte" : valeur === "hors_ligne" ? "horsLigne" : "inconnu";
  }
  function CarteHermes(props) {
    const { hermes, image, deploiement } = props.meta;
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.hermes, id: "acp-accueil-hermes" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.version }, /* @__PURE__ */ h(Donnee, { valeur: chaine(hermes?.version), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.versionTestee }, /* @__PURE__ */ h(Donnee, { valeur: chaine(hermes?.version_testee), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.conformite }, /* @__PURE__ */ h(Pastille, { etat: etatConformite(hermes?.conforme) })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.image }, /* @__PURE__ */ h(Donnee, { valeur: court(image?.condensat_index), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.commit }, /* @__PURE__ */ h(Donnee, { valeur: court(deploiement?.commit), mono: true }))));
  }
  function CarteGarde(props) {
    const garde = props.meta.garde_execution;
    const presente = garde?.presente_dans_le_gestionnaire;
    const admis = Array.isArray(garde?.outils_admis) ? garde.outils_admis.length : null;
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.garde, id: "acp-accueil-garde" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.gardeEtat }, presente === true ? /* @__PURE__ */ h(Pastille, { etat: "active" }) : presente === false ? /* @__PURE__ */ h(Pastille, { etat: "absente" }) : /* @__PURE__ */ h(Pastille, { etat: "inconnu" })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.outilsAdmis }, /* @__PURE__ */ h(Donnee, { valeur: nombre(admis) }))), chaine(garde?.alerte) ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(garde?.alerte) })) : null);
  }
  function CartePersona(props) {
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.persona, id: "acp-accueil-persona" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.personaEtat }, /* @__PURE__ */ h(Pastille, { etat: etatPersona(props.meta) }))));
  }
  function CarteCatalogue(props) {
    const resume = props.meta.catalogue ?? null;
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.catalogue, id: "acp-accueil-catalogue" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.skillsAcp }, /* @__PURE__ */ h(Donnee, { valeur: nombre(resume?.skills_actives) }), /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.commun.separateur, " "), /* @__PURE__ */ h(Donnee, { valeur: nombre(resume?.skills_attendues) }), /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.accueil.skillsAttendues)), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.context7 }, /* @__PURE__ */ h(Pastille, { etat: etatContext7(resume?.context7) }))), /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/catalogue" }, T.accueil.ouvrirCatalogue)));
  }
  function Horodatage(props) {
    const ms = versMillisecondes(props.valeur);
    if (ms === null) return /* @__PURE__ */ h(Donnee, { valeur: null });
    return /* @__PURE__ */ h("time", { dateTime: new Date(ms).toISOString() }, /* @__PURE__ */ h(Donnee, { valeur: dateRelative(ms) }));
  }
  function CarteSessions() {
    const chargement = useChargement(lireSessions);
    let contenu;
    if (chargement.etat === "chargement") {
      contenu = /* @__PURE__ */ h(EnChargement, null);
    } else if (chargement.etat === "erreur") {
      contenu = /* @__PURE__ */ h(BlocErreur, { erreur: chargement.erreur });
    } else {
      const sessions = Array.isArray(chargement.valeur.sessions) ? chargement.valeur.sessions.slice(0, 5) : [];
      contenu = sessions.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.aucuneSession) : /* @__PURE__ */ h("ul", { className: "acp-sessions" }, sessions.map((session, rang) => /* @__PURE__ */ h("li", { key: session.id ?? String(rang), className: "acp-session" }, /* @__PURE__ */ h("span", { className: "acp-session__titre" }, chaine(session.title) ? /* @__PURE__ */ h(Donnee, { valeur: chaine(session.title) }) : /* @__PURE__ */ h("span", null, T.accueil.sansTitre)), /* @__PURE__ */ h("span", { className: "acp-session__meta" }, /* @__PURE__ */ h(Horodatage, { valeur: session.last_active }), /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.commun.separateur, " "), /* @__PURE__ */ h(Donnee, { valeur: nombre(session.message_count) }), /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.accueil.messages)))));
    }
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.sessions, id: "acp-accueil-sessions" }, contenu, /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/sessions" }, T.accueil.toutesSessions)));
  }
  function CartePoste() {
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.poste, id: "acp-accueil-poste" }, /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Pastille, { etat: "nonConfigure" })), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.posteNote));
  }
  function CarteRaccourcis() {
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.raccourcis, id: "acp-accueil-raccourcis" }, /* @__PURE__ */ h("ul", { className: "acp-raccourcis" }, /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/projets" }, T.accueil.lienProjets)), /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/chat" }, T.accueil.discussion)), /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/sessions" }, T.accueil.lienSessions)), /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/kanban" }, T.accueil.kanban)), /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/catalogue" }, T.accueil.lienCatalogue))));
  }
  function Pied(props) {
    return /* @__PURE__ */ h("div", { className: "acp-pied" }, /* @__PURE__ */ h("span", null, T.accueil.piedAcp), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine(props.meta?.greffon?.version), mono: true }), " ", /* @__PURE__ */ h("span", null, T.commun.separateur), " ", /* @__PURE__ */ h("span", null, T.accueil.piedPropulse), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine(props.meta?.hermes?.version), mono: true }), " ", /* @__PURE__ */ h("span", null, T.accueil.piedLicence));
  }
  function Accueil() {
    const meta = useChargement(() => lireMeta());
    return /* @__PURE__ */ h("div", { className: "acp-page", "data-acp-racine": "accueil" }, /* @__PURE__ */ h("div", { className: "acp-entete" }, /* @__PURE__ */ h("h1", { className: "acp-titre" }, T.accueil.titre), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.intro)), meta.etat === "chargement" ? /* @__PURE__ */ h(EnChargement, null) : null, meta.etat === "erreur" ? /* @__PURE__ */ h(BlocErreur, { erreur: meta.erreur, message: T.accueil.metaIndisponible }) : null, /* @__PURE__ */ h("div", { className: "acp-grille" }, meta.etat === "ok" ? /* @__PURE__ */ h(CarteHermes, { meta: meta.valeur }) : null, meta.etat === "ok" ? /* @__PURE__ */ h(CarteGarde, { meta: meta.valeur }) : null, meta.etat === "ok" ? /* @__PURE__ */ h(CartePersona, { meta: meta.valeur }) : null, meta.etat === "ok" ? /* @__PURE__ */ h(CarteCatalogue, { meta: meta.valeur }) : null, /* @__PURE__ */ h(CarteSessions, null), /* @__PURE__ */ h(CartePoste, null), /* @__PURE__ */ h(CarteRaccourcis, null)), /* @__PURE__ */ h(Pied, { meta: meta.etat === "ok" ? meta.valeur : null }));
  }

  // src/interface/Alertes.tsx
  function Alertes() {
    const meta = useChargement(() => lireMeta());
    if (meta.etat === "chargement") return null;
    if (meta.etat === "erreur") {
      return /* @__PURE__ */ h("div", { "data-acp-racine": "alertes", className: "acp-banniere" }, /* @__PURE__ */ h(BlocErreur, { erreur: meta.erreur, message: T.accueil.metaIndisponible }));
    }
    const alertes = listeDeChaines(meta.valeur.alertes);
    if (alertes.length === 0) return null;
    return /* @__PURE__ */ h("section", { "data-acp-racine": "alertes", className: "acp-banniere", "aria-labelledby": "acp-alertes-titre" }, /* @__PURE__ */ h("h2", { className: "acp-banniere__titre", id: "acp-alertes-titre" }, T.alertes.titre), /* @__PURE__ */ h("ul", { className: "acp-banniere__liste" }, alertes.map((alerte, rang) => /* @__PURE__ */ h("li", { key: String(rang) }, /* @__PURE__ */ h(Donnee, { valeur: alerte })))));
  }

  // src/interface/Marque.tsx
  function Marque() {
    return /* @__PURE__ */ h("span", { "data-acp-racine": "marque", className: "acp-marque-racine" }, /* @__PURE__ */ h("a", { className: "acp-marque", href: `${cheminDeBase()}/`, "aria-label": T.marque.lienAccueil }, /* @__PURE__ */ h("span", { "aria-hidden": "true" }, T.marque.sigle)));
  }

  // src/interface/VerrouFrancais.tsx
  var LANGUE = "fr";
  function forcerFrancais(i18n) {
    const valeur = i18n;
    if (!valeur || typeof valeur.setLocale !== "function" || valeur.locale === LANGUE) return false;
    valeur.setLocale(LANGUE);
    return true;
  }
  function VerrouFrancais() {
    const useI18n = sdk().useI18n;
    const i18n = typeof useI18n === "function" ? useI18n() : null;
    const langue = i18n?.locale;
    useEffect(() => {
      forcerFrancais(i18n);
    }, [langue]);
    return null;
  }

  // src/interface/index.ts
  installer({
    nom: "acp-interface",
    page: Accueil,
    emplacements: [
      ["header-left", Marque],
      ["header-banner", Alertes],
      ["overlay", VerrouFrancais]
    ]
  });
})();
