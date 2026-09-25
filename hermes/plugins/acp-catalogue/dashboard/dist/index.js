/* acp-catalogue 0.11.0 (ACP) — bundle généré par apps/interface/esbuild.mjs depuis apps/interface/src ; ne pas modifier à la main. Aucun code tiers embarqué : React vient du SDK du tableau de bord de Hermes. */

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
      reportee: "Report\xE9e au poste (P8)",
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
      ciblePoste: "Poste \u2014 report\xE9 \xE0 P8",
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

  // src/api.ts
  var ROUTE_CATALOGUE = "/api/plugins/acp-poste/v1/catalogue";
  var ROUTE_SKILLS = "/api/skills";
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
  var lireSkills = () => lireJSON(ROUTE_SKILLS);

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
  function useMemo(calcul, dependances) {
    return react().useMemo(calcul, dependances);
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
    reportee: "neutre",
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
  var PALIERS = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 30],
    ["month", 12],
    ["year", Number.POSITIVE_INFINITY]
  ];
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

  // src/catalogue/Catalogue.tsx
  var TOUS = "";
  var LIBELLES_PROFILS = {
    base: T.catalogue.profilBase,
    web: T.catalogue.profilWeb,
    recherche: T.catalogue.profilRecherche,
    donnees: T.catalogue.profilDonnees
  };
  function etatEntree(etat) {
    switch (etat) {
      case "active":
      case "actif":
        return "active";
      case "desactivee":
      case "desactive":
        return "desactivee";
      case "absente":
      case "absent":
        return "absente";
      case "reportee":
      case "reportee-p8":
      case "reporte-p8":
        return "reportee";
      case "ambigue":
        return "ambigue";
      case "livree":
        return "livree";
      case "connecte":
        return "connecte";
      case "hors_ligne":
        return "horsLigne";
      default:
        return "inconnu";
    }
  }
  function Cible(props) {
    if (props.cible === "hermes") return /* @__PURE__ */ h("span", null, T.catalogue.cibleHermes);
    if (props.cible === "poste") return /* @__PURE__ */ h("span", null, T.catalogue.ciblePoste);
    return /* @__PURE__ */ h(Donnee, { valeur: chaine(props.cible) });
  }
  function Profil(props) {
    const libelle = LIBELLES_PROFILS[props.id];
    return libelle ? /* @__PURE__ */ h("span", null, libelle) : /* @__PURE__ */ h(Donnee, { valeur: props.id });
  }
  function Etat(props) {
    const cle = etatEntree(props.etat);
    return /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h(Pastille, { etat: cle }), cle === "inconnu" && chaine(props.etat) ? /* @__PURE__ */ h(Donnee, { valeur: chaine(props.etat), mono: true }) : null);
  }
  function libelleSource(nom, sources) {
    if (!nom) return null;
    const commit = court(sources[nom]?.commit, 8);
    return commit ? `${nom}@${commit}` : nom;
  }
  function nomsDeListe(valeur) {
    if (!Array.isArray(valeur)) return [];
    return valeur.map((v) => typeof v === "string" ? v : v && typeof v === "object" ? chaine(v.nom) : null).filter((v) => !!v);
  }
  function EntreeSkill(props) {
    const { skill, sources } = props;
    const source = chaine(skill.source);
    const profils = listeDeChaines(skill.profils);
    return /* @__PURE__ */ h("li", { className: "acp-entree" }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(skill.nom), mono: true })), chaine(skill.description_fr) ? /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: chaine(skill.description_fr) })) : null, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.source }, /* @__PURE__ */ h(Donnee, { valeur: libelleSource(source, sources), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.licence }, /* @__PURE__ */ h(Donnee, { valeur: source ? chaine(sources[source]?.licence) : null })), /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.cible }, /* @__PURE__ */ h(Cible, { cible: skill.cible })), /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.profil }, profils.length === 0 ? /* @__PURE__ */ h(Donnee, { valeur: null }) : profils.map((p, rang) => /* @__PURE__ */ h("span", { key: p, className: "acp-profil" }, rang > 0 ? /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.commun.separateur, " ") : null, /* @__PURE__ */ h(Profil, { id: p })))), /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.etat }, /* @__PURE__ */ h(Etat, { etat: skill.etat }))), chaine(skill.raison) ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(skill.raison) })) : null);
  }
  function EntreeMcp(props) {
    const { mcp } = props;
    const outils = listeDeChaines(mcp.outils_hermes);
    return /* @__PURE__ */ h("li", { className: "acp-entree" }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(mcp.nom), mono: true })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.cible }, /* @__PURE__ */ h(Cible, { cible: mcp.cible })), /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.etat }, /* @__PURE__ */ h(Etat, { etat: mcp.connexion ?? mcp.etat })), /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.outils }, outils.length === 0 ? /* @__PURE__ */ h(Donnee, { valeur: null }) : /* @__PURE__ */ h("ul", { className: "acp-outils" }, outils.map((o) => /* @__PURE__ */ h("li", { key: o }, /* @__PURE__ */ h(Donnee, { valeur: o, mono: true })))))), chaine(mcp.raison) ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(mcp.raison) })) : null);
  }
  function ListeEcarts(props) {
    if (props.noms.length === 0) return null;
    return /* @__PURE__ */ h("div", { className: "acp-ecart" }, /* @__PURE__ */ h("h3", { className: "acp-sous-titre" }, props.titre), /* @__PURE__ */ h("ul", { className: "acp-noms" }, props.noms.map((n) => /* @__PURE__ */ h("li", { key: n }, /* @__PURE__ */ h(Donnee, { valeur: n, mono: true })))));
  }
  function Choix(props) {
    return /* @__PURE__ */ h("div", { className: "acp-choix" }, /* @__PURE__ */ h("label", { htmlFor: props.id }, props.libelle), /* @__PURE__ */ h("select", { id: props.id, value: props.valeur, onChange: (e) => props.changer(e.target.value) }, /* @__PURE__ */ h("option", { value: TOUS }, props.toutLibelle), props.options.map(
      (o) => o.donnee ? /* @__PURE__ */ h("option", { key: o.valeur, value: o.valeur, "data-acp-donnee": "" }, o.libelle) : /* @__PURE__ */ h("option", { key: o.valeur, value: o.valeur }, o.libelle)
    )));
  }
  function VueCatalogue(props) {
    const { donnees } = props;
    const [profil, fixerProfil] = useState(TOUS);
    const [source, fixerSource] = useState(TOUS);
    const [cible, fixerCible] = useState(TOUS);
    const sources = donnees.sources && typeof donnees.sources === "object" ? donnees.sources : {};
    const skills = Array.isArray(donnees.skills) ? donnees.skills : [];
    const mcp = Array.isArray(donnees.mcp) ? donnees.mcp : [];
    const idsProfils = useMemo(() => {
      const ids = new Set(
        donnees.profils && typeof donnees.profils === "object" ? Object.keys(donnees.profils) : []
      );
      for (const s of skills) for (const p of listeDeChaines(s.profils)) ids.add(p);
      return [...ids].sort();
    }, [donnees]);
    const idsSources = useMemo(() => {
      const ids = new Set(Object.keys(sources));
      for (const s of skills) if (chaine(s.source)) ids.add(s.source);
      return [...ids].sort();
    }, [donnees]);
    const retenues = skills.filter(
      (s) => (profil === TOUS || listeDeChaines(s.profils).includes(profil)) && (source === TOUS || s.source === source) && (cible === TOUS || s.cible === cible)
    );
    const mcpRetenus = mcp.filter((m) => cible === TOUS || m.cible === cible);
    const horsCatalogue = nomsDeListe(donnees.hors_catalogue);
    const collisions = nomsDeListe(donnees.collisions);
    const nonAppliquees = nomsDeListe(donnees.desactivations_non_appliquees);
    const alertes = listeDeChaines(donnees.alertes);
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, alertes.length > 0 ? /* @__PURE__ */ h(Carte, { titre: T.catalogue.alertes, id: "acp-catalogue-alertes" }, /* @__PURE__ */ h("ul", { className: "acp-noms" }, alertes.map((a, rang) => /* @__PURE__ */ h("li", { key: String(rang) }, /* @__PURE__ */ h(Donnee, { valeur: a }))))) : null, /* @__PURE__ */ h("fieldset", { className: "acp-filtres" }, /* @__PURE__ */ h("legend", null, T.catalogue.filtres), /* @__PURE__ */ h(
      Choix,
      {
        id: "acp-filtre-profil",
        libelle: T.catalogue.profil,
        valeur: profil,
        changer: fixerProfil,
        toutLibelle: T.catalogue.tous,
        options: idsProfils.map((p) => ({
          valeur: p,
          libelle: LIBELLES_PROFILS[p] ?? p,
          donnee: !LIBELLES_PROFILS[p]
        }))
      }
    ), /* @__PURE__ */ h(
      Choix,
      {
        id: "acp-filtre-source",
        libelle: T.catalogue.source,
        valeur: source,
        changer: fixerSource,
        toutLibelle: T.catalogue.toutes,
        options: idsSources.map((s) => ({ valeur: s, libelle: s, donnee: true }))
      }
    ), /* @__PURE__ */ h(
      Choix,
      {
        id: "acp-filtre-cible",
        libelle: T.catalogue.cible,
        valeur: cible,
        changer: fixerCible,
        toutLibelle: T.catalogue.toutes,
        options: [
          { valeur: "hermes", libelle: T.catalogue.cibleHermes, donnee: false },
          { valeur: "poste", libelle: T.catalogue.ciblePoste, donnee: false }
        ]
      }
    )), /* @__PURE__ */ h(Carte, { titre: T.catalogue.skills, id: "acp-catalogue-skills" }, retenues.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.catalogue.aucuneEntree) : /* @__PURE__ */ h("ul", { className: "acp-entrees" }, retenues.map((s, rang) => /* @__PURE__ */ h(EntreeSkill, { key: chaine(s.nom) ?? String(rang), skill: s, sources })))), /* @__PURE__ */ h(Carte, { titre: T.catalogue.mcp, id: "acp-catalogue-mcp" }, mcpRetenus.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.catalogue.aucuneEntree) : /* @__PURE__ */ h("ul", { className: "acp-entrees" }, mcpRetenus.map((m, rang) => /* @__PURE__ */ h(EntreeMcp, { key: chaine(m.nom) ?? String(rang), mcp: m })))), /* @__PURE__ */ h(Carte, { titre: T.catalogue.ecarts, id: "acp-catalogue-ecarts" }, horsCatalogue.length + collisions.length + nonAppliquees.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.catalogue.aucunEcart) : null, /* @__PURE__ */ h(ListeEcarts, { titre: T.catalogue.horsCatalogue, noms: horsCatalogue }), /* @__PURE__ */ h(ListeEcarts, { titre: T.catalogue.collisions, noms: collisions }), /* @__PURE__ */ h(ListeEcarts, { titre: T.catalogue.desactivationsNonAppliquees, noms: nonAppliquees })));
  }
  function VueHermes() {
    const skills = useChargement(lireSkills);
    let contenu;
    if (skills.etat === "chargement") contenu = /* @__PURE__ */ h(EnChargement, null);
    else if (skills.etat === "erreur") contenu = /* @__PURE__ */ h(BlocErreur, { erreur: skills.erreur });
    else {
      const liste = Array.isArray(skills.valeur) ? skills.valeur : [];
      const activees = liste.filter((s) => s.enabled === true);
      const desactivees = liste.filter((s) => s.enabled === false);
      const tries = [...liste].sort((a, b) => String(a.name).localeCompare(String(b.name)));
      const etat = (s) => s.enabled === true ? "activee" : s.enabled === false ? "desactivee" : "inconnu";
      contenu = /* @__PURE__ */ h("div", null, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.skillsInstallees }, /* @__PURE__ */ h(Donnee, { valeur: nombre(liste.length) })), /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.skillsActivees }, /* @__PURE__ */ h(Donnee, { valeur: nombre(activees.length) })), /* @__PURE__ */ h(Ligne, { libelle: T.catalogue.skillsDesactivees }, /* @__PURE__ */ h(Donnee, { valeur: nombre(desactivees.length) }))), /* @__PURE__ */ h("details", { className: "acp-details" }, /* @__PURE__ */ h("summary", null, T.catalogue.listeSkills), /* @__PURE__ */ h("ul", { className: "acp-noms" }, tries.map((s, rang) => /* @__PURE__ */ h("li", { key: chaine(s.name) ?? String(rang), className: "acp-nom-etat" }, /* @__PURE__ */ h(Donnee, { valeur: chaine(s.name), mono: true }), " ", /* @__PURE__ */ h(Pastille, { etat: etat(s) }))))));
    }
    return /* @__PURE__ */ h(Carte, { titre: T.catalogue.vuParHermes, id: "acp-catalogue-hermes" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.catalogue.vuParHermesNote), contenu);
  }
  function Catalogue() {
    const catalogue = useChargement(lireCatalogue);
    return /* @__PURE__ */ h("div", { className: "acp-page", "data-acp-racine": "catalogue" }, /* @__PURE__ */ h("div", { className: "acp-entete" }, /* @__PURE__ */ h("h1", { className: "acp-titre" }, T.catalogue.titre), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.catalogue.intro)), catalogue.etat === "chargement" ? /* @__PURE__ */ h(EnChargement, null) : null, catalogue.etat === "erreur" ? /* @__PURE__ */ h(BlocErreur, { erreur: catalogue.erreur, message: T.catalogue.indisponible }) : null, catalogue.etat === "ok" ? /* @__PURE__ */ h(VueCatalogue, { donnees: catalogue.valeur }) : null, /* @__PURE__ */ h(VueHermes, null));
  }

  // src/catalogue/index.ts
  installer({ nom: "acp-catalogue", page: Catalogue });
})();
