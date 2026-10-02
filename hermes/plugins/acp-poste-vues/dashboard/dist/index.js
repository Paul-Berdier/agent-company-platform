/* acp-poste-vues 0.11.0 (ACP) — bundle généré par apps/interface/esbuild.mjs depuis apps/interface/src ; ne pas modifier à la main. Aucun code tiers embarqué : React vient du SDK du tableau de bord de Hermes. */

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
      intro: "Ce qui vous attend, vos projets, l'ex\xE9cutant et les quotas, tenus \xE0 jour tant que la page est visible.",
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
      // Étape P7 : Accueil agrégé (cahier P7 § 8) et bilan quotidien (§ 7).
      aTraiterTitre: "\xC0 traiter par vous",
      blocIllisible: "Bloc illisible\xA0:",
      questions: "Questions",
      decisions: "D\xE9cisions",
      revues: "Revues",
      arretees: "Cartes arr\xEAt\xE9es",
      discussionsEnAttente: "Discussions en attente",
      inconnues: "Inconnues",
      chezHermes: "Chez Hermes",
      rienATraiter: "Rien n'attend votre d\xE9cision.",
      ouvrirQuestions: "Ouvrir la file Questions",
      genreQuestion: "Question\xA0:",
      genreDecision: "D\xE9cision\xA0:",
      genreRevue: "Revue\xA0:",
      genreArretee: "Carte arr\xEAt\xE9e\xA0:",
      projetsTitre: "Projets en cours",
      projetsEnCours: "En cours",
      projetsEnPause: "En pause",
      projetsTermines7j: "Termin\xE9s ces 7 derniers jours",
      aucunProjetOuvert: "Aucun projet ouvert.",
      ouvrirProjets: "Ouvrir les projets",
      executantTitre: "Ex\xE9cutant",
      etat: "\xC9tat",
      machine: "Machine",
      plateforme: "Plateforme",
      derniereVue: "Vu pour la derni\xE8re fois",
      carteEnCours: "Carte en cours",
      aucuneCarteEnCours: "Aucune",
      voiesFermees: "Voies ferm\xE9es\xA0:",
      ouvrirPoste: "Ouvrir la page Poste",
      quotasTitre: "Quotas",
      utilise: "Utilis\xE9",
      remiseAZero: "Remise \xE0 z\xE9ro",
      source: "Source",
      releveLe: "Relev\xE9",
      quotasHermes: "Hermes",
      ouvrirQuotas: "Ouvrir les quotas",
      bilanTitre: "Bilan quotidien",
      bilanIllisible: "\xC9tat du bilan inconnu\xA0: la liste des t\xE2ches cron de Hermes ne r\xE9pond pas.",
      bilanNonCree: "Non cr\xE9\xE9",
      bilanExplication: "Une notification par jour, \xE0 8 h (heure de Paris)\xA0: des compteurs seulement, sans mod\xE8le ni jeton. Vous seul pouvez la cr\xE9er.",
      creerBilan: "Cr\xE9er le bilan quotidien (8 h)",
      bilanActif: "Actif",
      bilanEnPause: "En pause",
      prochainEnvoi: "Prochain envoi",
      dernierEnvoi: "Dernier envoi",
      jamais: "Jamais",
      bilanPlusieurs: "Plusieurs t\xE2ches du bilan existent\xA0: gardez-en une depuis la page Cron.",
      bilanCree: "Bilan quotidien cr\xE9\xE9.",
      bilanSansCanal: "Le bilan ne partira pas\xA0: notifications non configur\xE9es.",
      ouvrirCron: "Pause et suppression\xA0: page Cron",
      accueilIndisponible: "L'accueil est indisponible\xA0: le greffon acp-poste ne r\xE9pond pas sur /v1/accueil.",
      actualisationImpossible: "Derni\xE8re actualisation impossible\xA0: les donn\xE9es affich\xE9es sont celles de la lecture pr\xE9c\xE9dente.",
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
    tempsReel: {
      actif: "Page actualis\xE9e en temps r\xE9el tant qu'elle est visible.",
      connexion: "Connexion au temps r\xE9el en cours\xA0: actualisation toutes les 15 secondes en attendant.",
      repli: "Temps r\xE9el indisponible\xA0: actualisation toutes les 15 secondes tant que la page est visible.",
      sansFlux: "Temps r\xE9el non pris en charge par ce tableau de bord\xA0: actualisation toutes les 15 secondes tant que la page est visible."
    },
    projets: {
      titre: "Projets",
      intro: "Les projets que vous confiez \xE0 Hermes\xA0: il les planifie, les fait avancer carte par carte et vous pose ici ses questions.",
      navigation: "Pages des projets",
      vueListe: "Projets",
      vueQuestions: "Questions",
      vueNouveau: "Nouveau projet",
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
      aucunDepotConnu: "Aucun d\xE9p\xF4t connu\xA0: le poste n'a encore publi\xE9 aucun inventaire (page Poste).",
      depotsInconnus: "D\xE9p\xF4ts inconnus\xA0: l'inventaire du poste est illisible (voir l'erreur ci-dessus).",
      releveFactice: "Relev\xE9 factice\xA0: ces mod\xE8les viennent d'un relev\xE9 de test, pas de votre poste.",
      exploration: "Exploration du d\xE9p\xF4t",
      explorationAide: "Le poste lit le d\xE9p\xF4t, sans rien y modifier, avant la planification.",
      champVoie: "Ex\xE9cutant",
      champModele: "Mod\xE8le",
      modeleParDefaut: "Mod\xE8le par d\xE9faut du relev\xE9",
      modeleAChoisir: "Choisissez un mod\xE8le (le relev\xE9 n'en d\xE9signe aucun par d\xE9faut)",
      modeleExige: "Choisissez un mod\xE8le pour l'exploration\xA0: le relev\xE9 de cet ex\xE9cutant n'en d\xE9signe aucun par d\xE9faut.",
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
      prolongerP6: "Le plafond de corrections ne se prolonge pas\xA0: la relecture qui l'a atteint est close\xA0; concluez depuis cette carte.",
      prolongationFaite: "Plafond relev\xE9\xA0: Hermes planifie la suite avec votre consigne.",
      relanceFaite: "Planification relanc\xE9e\xA0: Hermes planifie avec votre consigne.",
      conclusionFaite: "Projet conclu.",
      noteTronquee: "Extrait\xA0; le d\xE9tail du projet donne les r\xE9sum\xE9s en entier.",
      revuesTitre: "Revues des fichiers de pilotage",
      revuesIntro: "Une carte de l'ex\xE9cutant a modifi\xE9 des fichiers qui pilotent les agents (CLAUDE.md, AGENTS.md, .github\u2026). Acceptez-la, ou refusez-la avec un motif\xA0: elle revient alors \xE0 l'ex\xE9cutant, qui retire la modification.",
      aucuneRevue: "Aucune carte en revue.",
      chemins: "Fichiers de pilotage touch\xE9s",
      diffstat: "Modification",
      fichiers: "fichier(s)",
      ajouts: "ajout(s)",
      retraits: "retrait(s)",
      branche: "Branche",
      tete: "T\xEAte",
      accepterRevue: "Accepter",
      refuserRevue: "Refuser",
      motifRefus: "Motif du refus",
      revueAcceptee: "Revue accept\xE9e\xA0: la carte est termin\xE9e.",
      revueRefusee: "Revue refus\xE9e\xA0: la carte revient \xE0 l'ex\xE9cutant avec votre motif.",
      bloqueesTitre: "Cartes bloqu\xE9es ou abandonn\xE9es",
      // Étape P7 : file Questions, « Qui répond », « Clore » (cahier P7 § 3, § 4.2, § 10).
      fileTitre: "\xC0 traiter",
      aTraiterParVous: "\xC0 traiter par vous",
      chezHermesCompte: "Chez Hermes",
      discussionsNonComptees: "(discussions en attente\xA0: \xE9tat inconnu, non compt\xE9es)",
      cibleTraitee: "Cette demande a d\xE9j\xE0 \xE9t\xE9 trait\xE9e\xA0: elle n'est plus dans la file.",
      quiRepondQuestion: "Qui r\xE9pond",
      chezHermes: "Hermes y r\xE9pond",
      aVous: "\xC0 vous",
      carteRepondre: "Carte \xAB\xA0r\xE9pondre\xA0\xBB\xA0:",
      chezHermesAide: "Hermes pr\xE9pare la r\xE9ponse par sa carte \xAB\xA0r\xE9pondre\xA0\xBB\xA0; vous pouvez r\xE9pondre vous-m\xEAme avant lui.",
      bloqueesIntro: "\xAB\xA0Relancer\xA0\xBB remet la carte en route, avec votre consigne si vous en donnez une. Une carte qui rebloque pour la m\xEAme raison revient en d\xE9cision.",
      relancerCarte: "Relancer",
      relanceExecutantAide: "L'agent repart d'une session neuve, sur la branche d\xE9j\xE0 commenc\xE9e.",
      relancee: "La carte repart.",
      relanceeSessionNeuve: "La carte repart\xA0: l'agent reprend d'une session neuve, sur la branche d\xE9j\xE0 commenc\xE9e.",
      nonRelancee: "La carte n'a pas \xE9t\xE9 relanc\xE9e.",
      statutApres: "Statut\xA0:",
      nonRelancable: "Relance impossible\xA0:",
      discussionsTitre: "Discussions en attente",
      discussionsIntro: "Discussions du tableau de bord dont une demande attend votre r\xE9ponse, en lecture seule.",
      discussionsInconnues: "Discussions\xA0: \xE9tat inconnu (le tableau de bord n'a pas pu \xEAtre interrog\xE9).",
      requetesOuvertes: "Requ\xEAtes ouvertes dans le tableau de bord\xA0:",
      aucuneDiscussion: "Aucune discussion en attente.",
      discussionSansTitre: "Sans titre",
      discussionEtat: "\xC9tat",
      discussionEnAttente: "En attente d'une r\xE9ponse",
      discussionActivite: "Derni\xE8re activit\xE9",
      discussionApercu: "Aper\xE7u",
      discussionCle: "Session",
      discussionsLimite: "Les questions pos\xE9es dans la discussion en terminal (/chat) ne sont visibles que dans cette discussion.",
      reponsesSansObjetCourt: "Sans objet (projet sans d\xE9p\xF4t)",
      changerQuiRepond: "Changer qui r\xE9pond",
      quiRepondSuivantes: "Qui r\xE9pond aux questions suivantes",
      quiRepondAide: "Le changement vaut pour les questions suivantes\xA0; les questions d\xE9j\xE0 ouvertes gardent leur traitement, et vous pouvez toujours y r\xE9pondre vous-m\xEAme.",
      enregistrer: "Enregistrer",
      reglageEnregistre: "R\xE9glage enregistr\xE9 pour les questions suivantes. Questions ouvertes qui gardent leur traitement\xA0:",
      clore: "Clore le projet",
      cloreQuestion: "Clore ce projet\xA0?",
      clorePoint1: "Les cartes ouvertes du projet sont archiv\xE9es\xA0; un travail en cours est arr\xEAt\xE9.",
      clorePoint2: "Ses questions ouvertes sont annul\xE9es.",
      clorePoint3: "Le projet passe \xAB\xA0Termin\xE9\xA0\xBB si la synth\xE8se du tour en cours est faite, sinon \xAB\xA0Abandonn\xE9\xA0\xBB.",
      clorePoint4: "Aucune notification n'est envoy\xE9e\xA0; les branches d\xE9j\xE0 rapport\xE9es restent sur l'ex\xE9cutant jusqu'\xE0 leur purge (7 jours).",
      cloreConfirmer: "Confirmer la cl\xF4ture",
      closTermine: "Projet clos\xA0: termin\xE9.",
      closAbandonne: "Projet clos\xA0: abandonn\xE9 (la synth\xE8se du tour en cours n'\xE9tait pas faite).",
      cartesArchivees: "Cartes archiv\xE9es\xA0:",
      questionsAnnulees: "Questions annul\xE9es\xA0:",
      branchesRestent: "Branches rest\xE9es sur l'ex\xE9cutant (purg\xE9es apr\xE8s 7 jours)\xA0:",
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
    poste: {
      titre: "Poste",
      intro: "Le poste qui ex\xE9cute vos projets sur d\xE9p\xF4t (ex\xE9cutant Railway, ou poste Windows)\xA0: enr\xF4lement, \xE9tat, isolement, carte en cours, routage des ex\xE9cutants et quotas relev\xE9s.",
      navigation: "Vues du poste",
      vueEtat: "Poste",
      vueRoutage: "Routage",
      vueQuotas: "Quotas",
      indisponible: "\xC9tat du poste indisponible.",
      actualisationImpossible: "Actualisation impossible\xA0: derni\xE8res valeurs lues affich\xE9es.",
      envoi: "Envoi\u2026",
      etatTitre: "\xC9tat du poste",
      etatTitreExecutant: "\xC9tat de l'ex\xE9cutant Railway",
      depuis: "depuis",
      vu: "Vu",
      revoqueLe: "R\xE9voqu\xE9 le",
      politiqueInvalide: "Politique locale invalide\xA0: le poste reste joignable mais ne publie plus rien.",
      pauseReclamations: "Pause g\xE9n\xE9rale\xA0: le poste n'ex\xE9cutera rien.",
      cartesEnAttente: "Cartes du poste en attente",
      enrolerTitre: "Enr\xF4ler un poste",
      enrolerAide: "G\xE9n\xE8re un code \xE0 usage unique, valable 10 minutes, \xE0 coller dans la commande d'enr\xF4lement ci-dessous, lanc\xE9e dans la console du compte du poste. Le jeton du poste n'est jamais affich\xE9.",
      enroler: "G\xE9n\xE9rer un code d'enr\xF4lement",
      codeTitre: "Code d'enr\xF4lement",
      codeUneFois: "Ce code ne s'affiche qu'une fois\xA0: il dispara\xEEt quand vous quittez la page.",
      copier: "Copier le code",
      copie: "Code copi\xE9\xA0: videz le presse-papiers apr\xE8s usage.",
      copieImpossible: "Copie impossible\xA0: s\xE9lectionnez le code \xE0 la main.",
      commande: "Commande \xE0 lancer sur le poste",
      expireDans: "Expire dans",
      secondes: "s",
      codeExpire: "Code expir\xE9\xA0: g\xE9n\xE9rez-en un nouveau.",
      confirmerTitre: "Confirmer le poste",
      empreinteAnnoncee: "Empreinte annonc\xE9e par le poste",
      empreinteAide: "Comparez-la \xE0 celle qu'affiche la commande d'enr\xF4lement sur le poste, puis recopiez-la. Si elles diff\xE8rent, r\xE9voquez ce poste.",
      champEmpreinte: "Empreinte affich\xE9e par le poste",
      confirmer: "Confirmer le poste",
      confirme: "Poste confirm\xE9\xA0: il compte d\xE9sormais.",
      revoquerTitre: "R\xE9voquer le poste",
      revoquerAide: "Le jeton du poste est refus\xE9 d\xE8s le prochain \xE9change\xA0; un nouvel enr\xF4lement devient possible.",
      revoquer: "R\xE9voquer",
      revoquerQuestion: "R\xE9voquer ce poste\xA0?",
      champMotif: "Motif",
      confirmerRevocation: "Confirmer la r\xE9vocation",
      annuler: "Annuler",
      revoque: "Poste r\xE9voqu\xE9.",
      releverTitre: "Relev\xE9",
      releverAide: "Demande au poste de relever ses catalogues et ses quotas, puis de publier son inventaire.",
      releverMaintenant: "Relever maintenant",
      machineTitre: "Poste enr\xF4l\xE9",
      nom: "Nom",
      empreinte: "Empreinte",
      protocole: "Protocole",
      versionPoste: "Version du poste",
      derniereRequete: "Dernier \xE9change",
      enroleLe: "Enr\xF4l\xE9",
      confirmeLe: "Confirm\xE9",
      compteTitre: "Compte d'ex\xE9cution",
      compte: "Compte",
      compteDedie: "Compte d\xE9di\xE9 acp-poste",
      compteProprietaire: "Compte du propri\xE9taire (repli d\xE9clar\xE9)",
      compteUidDedie: "Un compte Linux d\xE9di\xE9 par agent (ex\xE9cutant Railway)",
      windows: "Windows",
      python: "Python",
      empreintePolitique: "Empreinte de la politique (poste.toml ou executant.toml)",
      versionsTitre: "Versions des CLI",
      lue: "Lue",
      testee: "Test\xE9e",
      conformite: "Conforme",
      bacTitre: "Bac \xE0 sable Codex",
      readiness: "Readiness",
      modeLu: "Mode lu",
      origineMode: "Origine du mode",
      palierLu: "Palier lu",
      stockage: "Stockage des identifiants",
      ecritureAdmise: "\xC9criture admise",
      raison: "Raison",
      connexionsTitre: "Connexions",
      codex: "Codex",
      claude: "Claude Code",
      offre: "Offre",
      depotsTitre: "D\xE9p\xF4ts autoris\xE9s",
      aucunDepot: "Aucun d\xE9p\xF4t d\xE9clar\xE9 par le poste.",
      inventaireTitre: "Dernier inventaire",
      aucunInventaire: "Aucun inventaire re\xE7u.",
      recuLe: "Re\xE7u",
      releveLe: "Relev\xE9",
      alertesTitre: "Alertes du dernier inventaire",
      ordresTitre: "Ordres en attente",
      aucunOrdre: "Aucun ordre en attente.",
      livre: "Livr\xE9 au poste",
      nonLivre: "Pas encore livr\xE9",
      etats: {
        nonConfigure: "Non configur\xE9",
        aConfirmer: "\xC0 confirmer",
        enLigne: "En ligne",
        horsLigne: "Hors ligne",
        revoque: "R\xE9voqu\xE9",
        redeploiement: "En red\xE9ploiement"
      },
      executant: {
        titrePoste: "Poste Windows",
        titreExecutant: "Ex\xE9cutant Railway",
        plateforme: "Plateforme",
        noyau: "Noyau Linux",
        isolementTitre: "Isolement de l'ex\xE9cutant",
        isolementInconnu: "Inconnu\xA0: aucune sonde de plateforme publi\xE9e\xA0; l'\xE9criture est refus\xE9e.",
        regime: "R\xE9gime",
        regimeA: "A\xA0: bac \xE0 sable Linux (bubblewrap) en place",
        regimeB: "B\xA0: bac \xE0 sable Linux refus\xE9 par la plateforme",
        regimeInconnu: "Inconnu",
        sondeLe: "Sonde du",
        reseau: "R\xE9seau des commandes",
        reseauCoupe: "Coup\xE9",
        reseauNonCoupe: "Non coup\xE9",
        processus: "Processus visibles dans le bac \xE0 sable",
        identifiants: "Identifiants s\xE9par\xE9s par compte",
        identifiantsProuves: "Prouv\xE9 par la sonde",
        identifiantsNonProuves: "Non prouv\xE9",
        ecritureCodex: "\xC9criture Codex",
        ecritureClaude: "\xC9criture Claude",
        admise: "Admise",
        refusee: "Refus\xE9e",
        conditionsTitre: "Conditions d'usage",
        conditionsAide: "Date de votre d\xE9cision \xE9crite (D83, D84), consign\xE9e dans la politique de l'ex\xE9cutant\xA0; sans elle, la voie reste ferm\xE9e.",
        conditionsNonPubliees: "Non publi\xE9es par ce poste (inventaire de l'\xE9tape P5).",
        decideLe: "D\xE9cid\xE9 le",
        nonDecide: "Non d\xE9cid\xE9\xA0: voie ferm\xE9e",
        bornesTitre: "Bornes de la politique",
        cartesParJour: "Cartes par jour",
        dureeMax: "Dur\xE9e maximale d'une carte (s)",
        concurrence: "Cartes \xE0 la fois",
        annonceTitre: "Derni\xE8re r\xE9clamation",
        peutExecuter: "Peut ex\xE9cuter",
        voiesAnnoncees: "Voies annonc\xE9es",
        aucuneVoie: "Aucune voie annonc\xE9e.",
        espaceLibre: "Espace libre du volume (Mio)",
        carteTitre: "Carte en cours",
        aucuneCarte: "Aucune carte en main.",
        carteInconnue: "Carte annonc\xE9e par l'ex\xE9cutant, inconnue du greffon.",
        projet: "Projet",
        carte: "Carte",
        role: "R\xF4le",
        voie: "Voie",
        modeleDemande: "Mod\xE8le demand\xE9",
        modeleServi: "Mod\xE8le servi",
        statut: "Statut",
        dernierBattement: "Dernier battement",
        tenueParExecutant: "R\xE9clam\xE9e par l'ex\xE9cutant",
        voiesFermeesTitre: "Voies ferm\xE9es",
        aucuneVoieFermee: "Aucune voie ferm\xE9e d'apr\xE8s le dernier inventaire.",
        enAttenteDeVoie: "Cartes en attente d'une voie ferm\xE9e (jamais r\xE9assign\xE9es\xA0; bloqu\xE9es au-del\xE0 de 30 minutes)",
        depuis: "Depuis",
        branchesTitre: "Branches pr\xEAtes",
        branchesAide: "Branche int\xE9gr\xE9e sur l'ex\xE9cutant. Aucun push\xA0: r\xE9cup\xE9rez-la par un bundle avec la commande ci-dessous (railway ssh), puis v\xE9rifiez la t\xEAte sur votre PC.",
        aucuneBranche: "Aucune branche pr\xEAte.",
        branche: "Branche",
        tete: "T\xEAte",
        termineLe: "Int\xE9gr\xE9e",
        commande: "Commande de r\xE9cup\xE9ration",
        copier: "Copier la commande",
        copie: "Commande copi\xE9e.",
        copieImpossible: "Copie impossible\xA0: s\xE9lectionnez la commande \xE0 la main.",
        revuesEnAttente: "Cartes en revue (page Questions)"
      },
      genresOrdre: {
        releve: "Relev\xE9",
        pause: "Pause",
        reprise: "Reprise"
      },
      connexionsCodex: {
        compteChatgpt: "Compte ChatGPT",
        cleApi: "Cl\xE9 d'API (refus\xE9e)",
        autre: "Autre",
        nonConnecte: "Non connect\xE9",
        inconnu: "Inconnu"
      },
      connexionsClaude: {
        jetonReconnu: "Jeton reconnu",
        jetonPresentNonVerifie: "Jeton pr\xE9sent, non v\xE9rifi\xE9",
        refuse: "Refus\xE9",
        jetonAbsent: "Jeton absent",
        inconnu: "Inconnu"
      },
      routageIntro: "Chaque \xE9tape d'un projet part vers la premi\xE8re entr\xE9e admise de sa classe. Les listes viennent du relev\xE9 du poste\xA0; rien n'est devin\xE9, et ce que le poste interdit reste interdit.",
      listesTitre: "Listes relev\xE9es",
      resolutionsTitre: "R\xE9solutions observ\xE9es",
      resolutionsAide: "Mod\xE8le r\xE9ellement servi pour chaque alias, rapport\xE9 par l'ex\xE9cutant \xE0 la fin de ses cartes.",
      aucuneResolution: "Aucune r\xE9solution observ\xE9e\xA0: l'ex\xE9cutant n'a encore termin\xE9 aucune carte.",
      aliasObserve: "Alias demand\xE9",
      observeeLe: "Observ\xE9e le",
      aucunReleve: "Aucun relev\xE9\xA0: le poste n'a encore rien publi\xE9.",
      aucunModele: "Aucun mod\xE8le dans ce relev\xE9.",
      modeles: "Mod\xE8les",
      efforts: "Efforts",
      effortsInconnus: "Efforts inconnus",
      aucunEffort: "Aucun effort document\xE9",
      parDefaut: "par d\xE9faut",
      resolution: "R\xE9solution document\xE9e",
      accepterReleve: "Accepter ce relev\xE9 comme celui de mon compte",
      accepterAide: "La liste est identique au catalogue embarqu\xE9 de Codex. Acceptez-la seulement si vous savez que c'est bien celle de votre compte\xA0; l'acceptation vaut pour ce relev\xE9 seulement.",
      releveAccepte: "Relev\xE9 accept\xE9.",
      tableTitre: "Table de routage",
      classe: "Classe",
      entreeAdmise: "Admise",
      entreeRefusee: "Refus\xE9e",
      aucuneEntree: "Aucune entr\xE9e\xA0: la classe n'a pas de table.",
      appliquerSuggestion: "Appliquer la suggestion",
      ajouterEntree: "Ajouter une entr\xE9e",
      retirer: "Retirer",
      champVoie: "Ex\xE9cutant",
      champModele: "Mod\xE8le",
      champEffort: "Effort",
      champPalier: "Palier",
      modeleDuProfil: "Mod\xE8le par d\xE9faut du profil",
      modeleParDefaut: "Mod\xE8le par d\xE9faut du relev\xE9",
      modeleAChoisir: "Choisissez un mod\xE8le (le relev\xE9 n'en d\xE9signe aucun par d\xE9faut)",
      effortParDefaut: "Effort par d\xE9faut du mod\xE8le",
      palierStandard: "Standard (default)",
      validerTable: "Valider la table",
      tableValidee: "Table valid\xE9e.",
      refusDeLaTable: "Entr\xE9es refus\xE9es",
      rang: "entr\xE9e",
      etatsTable: {
        nonValidee: "Non valid\xE9e",
        validee: "Valid\xE9e",
        aRevalider: "\xC0 revalider"
      },
      classes: {
        exploration: "Exploration du d\xE9p\xF4t",
        planification: "Planification",
        synthese: "Synth\xE8se",
        repondre: "R\xE9ponses aux questions",
        rechercheWeb: "Recherche web",
        architecture: "Architecture",
        implementation: "Impl\xE9mentation",
        debogageTests: "D\xE9bogage et tests",
        petiteTache: "Petite t\xE2che",
        documentation: "Documentation",
        relecture: "Relecture crois\xE9e"
      },
      badges: {
        releveDuCompte: "Relev\xE9 du compte",
        listeDeSecours: "Liste de secours",
        listeDeSecoursProbable: "Liste de secours probable",
        listeAcceptee: "Relev\xE9 accept\xE9 par vous",
        aliasDocumentes: "Alias document\xE9s",
        perime: "P\xE9rim\xE9",
        inconnu: "Inconnu",
        releveFactice: "Relev\xE9 factice",
        indisponible: "Indisponible"
      },
      politiqueTitre: "Interdits c\xF4t\xE9 Hermes",
      politiqueAide: "Lever un effort max, ultra ou ultracode, ou admettre un palier autre que default, est une d\xE9pense hors enveloppe\xA0: recopiez la phrase demand\xE9e.",
      effortsInterdits: "Efforts interdits",
      paliersAdmis: "Paliers admis",
      separateurListe: "Valeurs s\xE9par\xE9es par des virgules",
      phrase: "Phrase de confirmation",
      phraseAttendue: "Phrase attendue",
      enregistrerPolitique: "Enregistrer les interdits",
      politiqueEnregistree: "Interdits enregistr\xE9s.",
      politiquePosteTitre: "Interdit par le poste (poste.toml)",
      politiquePosteAide: "Lecture seule\xA0: seule une modification locale sur le PC peut le lever.",
      executants: "Ex\xE9cutants",
      modelesPermis: "Mod\xE8les Codex permis",
      aliasPermis: "Alias Claude permis",
      tousDuReleve: "Tous ceux du relev\xE9",
      reseauExecutants: "R\xE9seau des ex\xE9cutants",
      surchargesTitre: "Surcharges globales",
      surchargesAide: "Une surcharge globale passe avant la table pour toute sa classe, jusqu'\xE0 sa d\xE9sactivation.",
      aucuneSurcharge: "Aucune surcharge active.",
      creerSurcharge: "Cr\xE9er la surcharge",
      surchargeCreee: "Surcharge cr\xE9\xE9e.",
      desactiver: "D\xE9sactiver",
      surchargeDesactivee: "Surcharge d\xE9sactiv\xE9e.",
      quotasIntro: "Quotas relev\xE9s par le poste, jamais estim\xE9s. Au-del\xE0 du seuil, le routage \xE9carte la voie.",
      seuil: "Seuil du routage",
      utilise: "Utilis\xE9",
      restant: "Restant",
      remiseAZero: "Remise \xE0 z\xE9ro",
      fenetre: "Fen\xEAtre",
      minutes: "min",
      limiteAtteinte: "Limite atteinte",
      aucunCompteur: "Aucun compteur relev\xE9.",
      hermesTitre: "Hermes (cerveau)",
      compteur: "Compteur",
      etatsQuotas: {
        releve: "Relev\xE9",
        perime: "P\xE9rim\xE9",
        inconnu: "Inconnu"
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
    return { ok: true, version: brut, tempsReel: typeof s.authedFetch === "function" };
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

  // src/flux.ts
  var ROUTE_FLUX = "/api/plugins/acp-poste/v1/flux";
  var SUJETS = ["projets", "questions", "poste", "quotas", "notifications", "pause", "discussions"];
  var VERSION_PARTAGE = 1;
  var REPRISES_MS = [1e3, 2e3, 5e3, 1e4, 3e4];
  var FENETRE_ECHECS_MS = 12e4;
  var ECHECS_AVANT_REPLI = 3;
  var NOUVEL_ESSAI_MS = 3e5;
  var FERMETURE_DIFFEREE_MS = 5e3;
  var TRAMES_GARDEES = 200;
  var AnalyseurSse = class {
    constructor() {
      __publicField(this, "dernierId", null);
      __publicField(this, "retry", null);
      __publicField(this, "commentaires", 0);
      __publicField(this, "reste", "");
      __publicField(this, "crEnSuspens", false);
      __publicField(this, "evenement", "");
      __publicField(this, "donnees", []);
      __publicField(this, "idTampon", null);
    }
    pousser(morceau) {
      let texte = morceau;
      if (this.crEnSuspens && texte.startsWith("\n")) texte = texte.slice(1);
      if (texte.length > 0) this.crEnSuspens = false;
      const tampon = this.reste + texte;
      const trames = [];
      let debut = 0;
      for (let i = 0; i < tampon.length; i += 1) {
        const c = tampon[i];
        if (c !== "\n" && c !== "\r") continue;
        const ligne = tampon.slice(debut, i);
        if (c === "\r") {
          if (i + 1 < tampon.length) {
            if (tampon[i + 1] === "\n") i += 1;
          } else {
            this.crEnSuspens = true;
          }
        }
        debut = i + 1;
        const trame = this.ligne(ligne);
        if (trame) trames.push(trame);
      }
      this.reste = tampon.slice(debut);
      return trames;
    }
    ligne(ligne) {
      if (ligne === "") return this.expedier();
      if (ligne.startsWith(":")) {
        this.commentaires += 1;
        return null;
      }
      const deuxPoints = ligne.indexOf(":");
      const champ = deuxPoints === -1 ? ligne : ligne.slice(0, deuxPoints);
      let valeur = deuxPoints === -1 ? "" : ligne.slice(deuxPoints + 1);
      if (valeur.startsWith(" ")) valeur = valeur.slice(1);
      if (champ === "event") this.evenement = valeur;
      else if (champ === "data") this.donnees.push(valeur);
      else if (champ === "id" && !valeur.includes("\0")) this.idTampon = valeur;
      else if (champ === "retry" && /^\d+$/.test(valeur)) this.retry = Number(valeur);
      return null;
    }
    expedier() {
      this.dernierId = this.idTampon;
      if (this.donnees.length === 0) {
        this.evenement = "";
        return null;
      }
      const trame = { id: this.dernierId, evenement: this.evenement || "message", donnees: this.donnees.join("\n") };
      this.donnees = [];
      this.evenement = "";
      return trame;
    }
  };
  function estSujet(valeur) {
    return typeof valeur === "string" && SUJETS.includes(valeur);
  }
  function visible() {
    return typeof document === "undefined" || document.visibilityState !== "hidden";
  }
  var FluxPartage = class {
    constructor() {
      __publicField(this, "version", VERSION_PARTAGE);
      __publicField(this, "abonnes", /* @__PURE__ */ new Map());
      __publicField(this, "ecouteurs", /* @__PURE__ */ new Set());
      __publicField(this, "compteur", 0);
      __publicField(this, "courant", { mode: "connexion", discussionsSuivies: null });
      __publicField(this, "controleur", null);
      __publicField(this, "generation", 0);
      __publicField(this, "reprise", null);
      __publicField(this, "fermeture", null);
      __publicField(this, "echecs", []);
      __publicField(this, "repliJusqua", 0);
      __publicField(this, "dernierId", null);
      __publicField(this, "recues", []);
      __publicField(this, "arrete", false);
      __publicField(this, "surVisibilite", () => visible() ? this.ouvrir() : this.fermer());
      if (typeof document !== "undefined") document.addEventListener("visibilitychange", this.surVisibilite);
    }
    /** S'abonne aux sujets ; rend la fonction de désabonnement. Le flux s'ouvre au premier abonné. */
    abonner(sujets, rappel) {
      this.compteur += 1;
      const numero = this.compteur;
      this.abonnes.set(numero, { sujets: new Set(sujets), rappel });
      if (this.fermeture !== null) {
        clearTimeout(this.fermeture);
        this.fermeture = null;
      }
      this.ouvrir();
      return () => {
        if (!this.abonnes.delete(numero) || this.abonnes.size > 0) return;
        if (this.fermeture !== null) clearTimeout(this.fermeture);
        this.fermeture = setTimeout(() => {
          this.fermeture = null;
          if (this.abonnes.size === 0) this.fermer();
        }, FERMETURE_DIFFEREE_MS);
      };
    }
    /** Suit les changements d'état (mode, discussions suivies) ; rend la fonction d'arrêt. */
    ecouter(rappel) {
      this.ecouteurs.add(rappel);
      return () => {
        this.ecouteurs.delete(rappel);
      };
    }
    etat() {
      return this.courant;
    }
    /** Dernières trames reçues (« etat », « changement », « fin »), pour le diagnostic et la preuve du parcours P7 (une
     *  relecture de la page suit-elle une trame ?). Aucune donnée : des noms de sujets. */
    trames() {
      return this.recues.map((r) => ({ ...r, sujets: [...r.sujets] }));
    }
    /** Nombre d'abonnés (tests et diagnostic). */
    abonnements() {
      return this.abonnes.size;
    }
    /** Ferme tout et oublie les écouteurs (tests). */
    detruire() {
      this.abonnes.clear();
      this.ecouteurs.clear();
      if (this.fermeture !== null) clearTimeout(this.fermeture);
      this.fermeture = null;
      this.fermer();
      if (typeof document !== "undefined") document.removeEventListener("visibilitychange", this.surVisibilite);
    }
    poser(etat) {
      const suivant = { ...this.courant, ...etat };
      if (suivant.mode === this.courant.mode && suivant.discussionsSuivies === this.courant.discussionsSuivies) return;
      this.courant = suivant;
      for (const ecouteur of [...this.ecouteurs]) ecouteur(suivant);
    }
    diffuser(sujets) {
      if (sujets.length === 0) return;
      for (const abonnement of [...this.abonnes.values()]) {
        const vises = sujets.filter((s) => abonnement.sujets.has(s));
        if (vises.length > 0) abonnement.rappel(vises);
      }
    }
    ouvrir() {
      if (this.abonnes.size === 0 || !visible() || this.controleur !== null || this.reprise !== null) return;
      let authedFetch;
      try {
        authedFetch = sdk().authedFetch;
      } catch {
        authedFetch = void 0;
      }
      if (typeof authedFetch !== "function") {
        this.poser({ mode: "indisponible" });
        return;
      }
      if (this.arrete) {
        this.poser({ mode: "sondage" });
        return;
      }
      const attente = this.repliJusqua - Date.now();
      if (attente > 0) {
        this.poser({ mode: "sondage" });
        this.planifier(attente);
        return;
      }
      void this.connecter(authedFetch);
    }
    fermer() {
      this.generation += 1;
      if (this.reprise !== null) clearTimeout(this.reprise);
      this.reprise = null;
      const controleur = this.controleur;
      this.controleur = null;
      controleur?.abort();
    }
    planifier(delai) {
      if (this.reprise !== null) clearTimeout(this.reprise);
      this.reprise = setTimeout(() => {
        this.reprise = null;
        this.ouvrir();
      }, delai);
    }
    async connecter(authedFetch) {
      this.generation += 1;
      const generation = this.generation;
      const controleur = new AbortController();
      this.controleur = controleur;
      let fin = false;
      try {
        const entetes = { Accept: "text/event-stream" };
        if (this.dernierId !== null) entetes["Last-Event-ID"] = this.dernierId;
        const reponse = await authedFetch(ROUTE_FLUX, { headers: entetes, signal: controleur.signal, cache: "no-store" });
        if (generation !== this.generation) return;
        if (reponse.status === 401) {
          this.arrete = true;
          this.controleur = null;
          this.poser({ mode: "sondage" });
          return;
        }
        if (!reponse.ok || reponse.body === null) throw new Error(`flux ${reponse.status}`);
        const lecteur = reponse.body.getReader();
        const decodeur = new TextDecoder();
        const analyseur = new AnalyseurSse();
        for (; ; ) {
          const { value, done } = await lecteur.read();
          if (generation !== this.generation) {
            void lecteur.cancel().catch(() => void 0);
            return;
          }
          if (done) break;
          for (const trame of analyseur.pousser(decodeur.decode(value, { stream: true }))) {
            if (trame.id !== null) this.dernierId = trame.id;
            fin = this.traiter(trame) || fin;
          }
        }
      } catch {
        if (generation !== this.generation) return;
      }
      if (generation !== this.generation) return;
      this.controleur = null;
      if (fin) {
        this.ouvrir();
        return;
      }
      this.echec();
    }
    /** Traite une trame ; rend vrai pour « fin ». */
    noter(evenement, sujets) {
      const t = typeof performance !== "undefined" ? performance.now() : Date.now();
      this.recues.push({ t, evenement, sujets });
      if (this.recues.length > TRAMES_GARDEES) this.recues.splice(0, this.recues.length - TRAMES_GARDEES);
    }
    traiter(trame) {
      if (trame.evenement === "fin") {
        this.noter("fin", []);
        return true;
      }
      if (trame.evenement !== "etat" && trame.evenement !== "changement") return false;
      let donnees;
      try {
        donnees = JSON.parse(trame.donnees);
      } catch {
        return false;
      }
      const brut = donnees && typeof donnees === "object" ? donnees : {};
      const sujets = Array.isArray(brut.sujets) ? brut.sujets.filter(estSujet) : [];
      this.noter(trame.evenement, sujets);
      if (trame.evenement === "etat") {
        this.echecs = [];
        this.repliJusqua = 0;
        const suivies = typeof brut.discussions_suivies === "boolean" ? brut.discussions_suivies : null;
        this.poser({ mode: "temps_reel", discussionsSuivies: suivies });
      }
      this.diffuser(sujets);
      return false;
    }
    echec() {
      const maintenant = Date.now();
      this.echecs = [...this.echecs.filter((t) => maintenant - t <= FENETRE_ECHECS_MS), maintenant];
      if (this.echecs.length >= ECHECS_AVANT_REPLI) {
        this.echecs = [];
        this.repliJusqua = maintenant + NOUVEL_ESSAI_MS;
        this.poser({ mode: "sondage" });
        this.planifier(NOUVEL_ESSAI_MS);
        return;
      }
      this.planifier(REPRISES_MS[Math.min(this.echecs.length - 1, REPRISES_MS.length - 1)]);
    }
  };
  function fluxPartage() {
    const registre = window.__ACP_FLUX__ ?? (window.__ACP_FLUX__ = {});
    const cle = `v${VERSION_PARTAGE}`;
    const existant = registre[cle];
    if (existant && typeof existant.abonner === "function" && existant.version === VERSION_PARTAGE) return existant;
    const flux = new FluxPartage();
    registre[cle] = flux;
    return flux;
  }

  // src/donnees.ts
  var INTERVALLE_SONDAGE_MS = 15e3;
  var RELECTURE_SURETE_MS = 12e4;
  var RELECTURE_DISCUSSIONS_MS = 6e4;
  var REGROUPEMENT_MS = 300;
  function visible2() {
    return typeof document === "undefined" || document.visibilityState !== "hidden";
  }
  function relectureDeSurete() {
    const demande = typeof window !== "undefined" ? window.__ACP_FLUX_REGLAGES__?.relectureSureteMs : void 0;
    return typeof demande === "number" && Number.isFinite(demande) && demande >= RELECTURE_SURETE_MS ? demande : RELECTURE_SURETE_MS;
  }
  function intervalleDeRelecture(etat, sujets) {
    if (etat.mode !== "temps_reel") return INTERVALLE_SONDAGE_MS;
    if (sujets.includes("discussions") && etat.discussionsSuivies === false) return RELECTURE_DISCUSSIONS_MS;
    return relectureDeSurete();
  }
  function useDonnees(charger, cle, sujets) {
    const [etat, fixer] = useState({ valeur: null, erreur: null, luLe: null });
    const lecteur = useRef(charger);
    lecteur.current = charger;
    const empreinteSujets = sujets.join(",");
    useEffect(() => {
      const liste2 = empreinteSujets ? empreinteSujets.split(",") : [];
      const flux = fluxPartage();
      let actif = true;
      let enCours = false;
      let aRelire = false;
      let minuterie = null;
      let regroupement = null;
      const arreter = () => {
        if (minuterie !== null) clearTimeout(minuterie);
        if (regroupement !== null) clearTimeout(regroupement);
        minuterie = null;
        regroupement = null;
      };
      const planifier = () => {
        if (minuterie !== null) clearTimeout(minuterie);
        minuterie = null;
        if (actif && !enCours && visible2()) minuterie = setTimeout(lire, intervalleDeRelecture(flux.etat(), liste2));
      };
      function lire() {
        arreter();
        if (!actif || !visible2()) return;
        if (enCours) {
          aRelire = true;
          return;
        }
        enCours = true;
        lecteur.current().then(
          (valeur) => {
            if (actif) fixer({ valeur, erreur: null, luLe: Date.now() });
          },
          (erreur) => {
            if (actif) fixer((avant) => ({ ...avant, erreur: envelopper(erreur) }));
          }
        ).finally(() => {
          enCours = false;
          if (!actif) return;
          if (aRelire) {
            aRelire = false;
            lire();
          } else {
            planifier();
          }
        });
      }
      const surSignal = () => {
        if (!actif || !visible2() || regroupement !== null) return;
        regroupement = setTimeout(() => {
          regroupement = null;
          lire();
        }, REGROUPEMENT_MS);
      };
      const surVisibilite = () => {
        if (visible2()) lire();
        else arreter();
      };
      lire();
      const desabonner = flux.abonner(liste2, surSignal);
      const arreterEcoute = flux.ecouter(() => planifier());
      document.addEventListener("visibilitychange", surVisibilite);
      return () => {
        actif = false;
        arreter();
        desabonner();
        arreterEcoute();
        document.removeEventListener("visibilitychange", surVisibilite);
      };
    }, [cle, empreinteSujets]);
    return etat;
  }
  function useEtatFlux() {
    const [etat, fixer] = useState(() => fluxPartage().etat());
    useEffect(() => {
      const flux = fluxPartage();
      fixer(flux.etat());
      return flux.ecouter(fixer);
    }, []);
    return etat;
  }

  // src/actualisation.tsx
  function EtatActualisation() {
    const etat = useEtatFlux();
    const texte = etat.mode === "temps_reel" ? T.tempsReel.actif : etat.mode === "sondage" ? T.tempsReel.repli : etat.mode === "indisponible" ? T.tempsReel.sansFlux : T.tempsReel.connexion;
    return /* @__PURE__ */ h(
      "p",
      {
        className: etat.mode === "sondage" ? "acp-alerte-texte" : "acp-discret",
        role: "status",
        "data-acp-temps-reel": etat.mode
      },
      texte
    );
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

  // src/projets/api.ts
  var RACINE_POSTE = "/api/plugins/acp-poste/v1";
  var ROUTE_PROJETS = `${RACINE_POSTE}/projets`;
  var ROUTE_QUESTIONS = `${RACINE_POSTE}/questions`;
  var ROUTE_POSTE = `${RACINE_POSTE}/poste`;
  var ROUTE_PAUSE = `${RACINE_POSTE}/pause`;
  var ROUTE_NOTIFICATION_TEST = `${RACINE_POSTE}/notifications/test`;
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

  // src/projets/briques.tsx
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

  // src/poste/api.ts
  var ROUTE_ENROLEMENT = `${ROUTE_POSTE}/enrolement`;
  var ROUTE_CONFIRMATION = `${ROUTE_POSTE}/confirmation`;
  var ROUTE_REVOCATION = `${ROUTE_POSTE}/revocation`;
  var ROUTE_RELEVE = `${ROUTE_POSTE}/releve`;
  var ROUTE_ROUTAGE = `${RACINE_POSTE}/routage`;
  var ROUTE_POLITIQUE = `${ROUTE_ROUTAGE}/politique`;
  var ROUTE_SURCHARGES = `${ROUTE_ROUTAGE}/surcharges`;
  var ROUTE_RELEVE_ACCEPTE = `${ROUTE_ROUTAGE}/releve-accepte`;
  var ROUTE_QUOTAS = `${RACINE_POSTE}/quotas`;
  var routeDesactiverSurcharge = (id) => `${ROUTE_SURCHARGES}/${encodeURIComponent(String(id))}/desactiver`;
  var lirePostePage = () => lireJSON(ROUTE_POSTE);
  var lireRoutage = () => lireJSON(ROUTE_ROUTAGE);
  var lireQuotas = () => lireJSON(ROUTE_QUOTAS);
  var creerCode = () => ecrireJSON(ROUTE_ENROLEMENT, {});
  var confirmer = (machineId, empreinte) => ecrireJSON(ROUTE_CONFIRMATION, { machine_id: machineId, empreinte });
  var revoquer = (machineId, motif) => ecrireJSON(ROUTE_REVOCATION, { machine_id: machineId, motif });
  var releverMaintenant = () => ecrireJSON(ROUTE_RELEVE, {});
  var validerTable = (releves, classes) => ecrireJSON(ROUTE_ROUTAGE, { releves, classes });
  var poserPolitique = (corps) => ecrireJSON(ROUTE_POLITIQUE, corps);
  var creerSurcharge = (corps) => ecrireJSON(ROUTE_SURCHARGES, corps);
  var desactiverSurcharge = (id) => ecrireJSON(routeDesactiverSurcharge(id), {});
  var accepterReleve = (releveId) => ecrireJSON(ROUTE_RELEVE_ACCEPTE, { releve_id: releveId });
  function refusDeLaTable(detail) {
    try {
      const corps = JSON.parse(detail);
      const refus = corps?.detail?.refus;
      return Array.isArray(refus) ? refus : [];
    } catch {
      return [];
    }
  }

  // src/poste/Enrolement.tsx
  function secondesRestantes(expireLe, maintenant) {
    return typeof expireLe === "number" && Number.isFinite(expireLe) ? Math.max(0, Math.round(expireLe - maintenant / 1e3)) : null;
  }
  function Enrolement(props) {
    const envoi = useEnvoi();
    const [code, fixerCode] = useState(null);
    const [maintenant, fixerMaintenant] = useState(() => Date.now());
    const [copie, fixerCopie] = useState(null);
    useEffect(() => {
      if (!code) return void 0;
      const minuterie = setInterval(() => fixerMaintenant(Date.now()), 1e3);
      return () => clearInterval(minuterie);
    }, [code]);
    const generer = async () => {
      fixerCopie(null);
      const resultat = await envoi.envoyer(() => creerCode());
      if (resultat) {
        fixerCode(resultat);
        fixerMaintenant(Date.now());
        props.apres();
      }
    };
    const copier = async () => {
      const presse = globalThis.navigator?.clipboard;
      if (!code?.code || !presse || typeof presse.writeText !== "function") {
        fixerCopie("impossible");
        return;
      }
      try {
        await presse.writeText(code.code);
        fixerCopie("ok");
      } catch {
        fixerCopie("impossible");
      }
    };
    const restant = code ? secondesRestantes(code.expire_le, maintenant) : null;
    const expire = restant !== null && restant <= 0;
    return /* @__PURE__ */ h("div", { className: "acp-groupe" }, /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-poste-enroler-aide" }, T.poste.enrolerAide), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.poste.enroler,
        principal: true,
        surClic: generer,
        desactive: envoi.etat.etat === "envoi",
        decritPar: "acp-poste-enroler-aide"
      }
    )), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }), code && !expire ? /* @__PURE__ */ h("div", { className: "acp-code", "data-acp-code": "" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.codeTitre), /* @__PURE__ */ h("p", { className: "acp-code__valeur" }, /* @__PURE__ */ h(Donnee, { valeur: code.code, mono: true })), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.codeUneFois), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.poste.copier, surClic: copier })), copie === "ok" ? /* @__PURE__ */ h("p", { className: "acp-succes", role: "status" }, T.poste.copie) : null, copie === "impossible" ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.poste.copieImpossible) : null, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, T.poste.commande), /* @__PURE__ */ h("dd", null, /* @__PURE__ */ h(Donnee, { valeur: code.commande, mono: true }))), /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, T.poste.expireDans), /* @__PURE__ */ h("dd", null, /* @__PURE__ */ h(Donnee, { valeur: restant }), " ", /* @__PURE__ */ h("span", null, T.poste.secondes))))) : null, code && expire ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.poste.codeExpire) : null);
  }

  // src/poste/Executant.tsx
  var X = T.poste.executant;
  function OuiNon(props) {
    if (typeof props.valeur !== "boolean") return /* @__PURE__ */ h(Donnee, { valeur: null });
    return /* @__PURE__ */ h("span", null, props.valeur ? T.commun.oui : T.commun.non);
  }
  function libelleRegime(regime) {
    if (regime === "A") return X.regimeA;
    if (regime === "B") return X.regimeB;
    return X.regimeInconnu;
  }
  function Ecriture(props) {
    if (typeof props.valeur !== "boolean") return /* @__PURE__ */ h(Donnee, { valeur: null });
    return /* @__PURE__ */ h(Etiquette, { libelle: { texte: props.valeur ? X.admise : X.refusee, famille: props.valeur ? "succes" : "echec" } });
  }
  function Isolement(props) {
    const i = props.isolement;
    if (!i) {
      return /* @__PURE__ */ h(Carte, { titre: X.isolementTitre, id: "acp-poste-isolement" }, /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, X.isolementInconnu));
    }
    const ecriture = i.ecriture_admise ?? {};
    const reseau = i.reseau_coupe === true ? X.reseauCoupe : i.reseau_coupe === false ? X.reseauNonCoupe : null;
    const processus = typeof i.proc_neuf === "boolean" ? !i.proc_neuf : null;
    return /* @__PURE__ */ h(Carte, { titre: X.isolementTitre, id: "acp-poste-isolement" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: X.regime }, /* @__PURE__ */ h(
      Etiquette,
      {
        libelle: { texte: libelleRegime(i.regime), famille: i.regime === "A" ? "succes" : "degrade" },
        brut: i.regime
      }
    )), /* @__PURE__ */ h(Ligne, { libelle: X.sondeLe }, /* @__PURE__ */ h(Donnee, { valeur: i.sonde_le, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.raison }, /* @__PURE__ */ h(Donnee, { valeur: i.raison })), /* @__PURE__ */ h(Ligne, { libelle: X.reseau }, /* @__PURE__ */ h(Donnee, { valeur: reseau })), /* @__PURE__ */ h(Ligne, { libelle: X.processus }, /* @__PURE__ */ h(OuiNon, { valeur: processus })), /* @__PURE__ */ h(Ligne, { libelle: X.identifiants }, i.uid_separes === true ? /* @__PURE__ */ h("span", null, X.identifiantsProuves) : /* @__PURE__ */ h("span", null, X.identifiantsNonProuves)), /* @__PURE__ */ h(Ligne, { libelle: X.ecritureCodex }, /* @__PURE__ */ h(Ecriture, { valeur: ecriture.codex })), /* @__PURE__ */ h(Ligne, { libelle: X.ecritureClaude }, /* @__PURE__ */ h(Ecriture, { valeur: ecriture.claude }))));
  }
  function Conditions(props) {
    const conditions = props.executant.conditions;
    const bornes = props.executant.bornes ?? {};
    return /* @__PURE__ */ h(Carte, { titre: X.conditionsTitre, id: "acp-poste-conditions" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, X.conditionsAide), conditions === null || conditions === void 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, X.conditionsNonPubliees) : /* @__PURE__ */ h("dl", { className: "acp-liste" }, ["codex", "claude"].map((cle) => /* @__PURE__ */ h(Ligne, { key: cle, libelle: cle === "codex" ? T.poste.codex : T.poste.claude }, typeof conditions[cle] === "string" ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-discret" }, X.decideLe), " ", /* @__PURE__ */ h(Donnee, { valeur: conditions[cle], mono: true })) : /* @__PURE__ */ h(Etiquette, { libelle: { texte: X.nonDecide, famille: "echec" } }))), /* @__PURE__ */ h(Ligne, { libelle: X.cartesParJour }, /* @__PURE__ */ h(Donnee, { valeur: bornes.cartes_par_jour ?? null })), /* @__PURE__ */ h(Ligne, { libelle: X.dureeMax }, /* @__PURE__ */ h(Donnee, { valeur: bornes.duree_max_carte_s ?? null })), /* @__PURE__ */ h(Ligne, { libelle: X.concurrence }, /* @__PURE__ */ h(Donnee, { valeur: bornes.concurrence ?? null }))));
  }
  function CarteEnCours(props) {
    const c = props.carte;
    const voies = Array.isArray(props.executant.voies_disponibles) ? props.executant.voies_disponibles : null;
    return /* @__PURE__ */ h(Carte, { titre: X.carteTitre, id: "acp-poste-carte-en-cours" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: X.peutExecuter }, /* @__PURE__ */ h(OuiNon, { valeur: props.executant.peut_executer })), /* @__PURE__ */ h(Ligne, { libelle: X.voiesAnnoncees }, voies === null ? /* @__PURE__ */ h(Donnee, { valeur: null }) : voies.length === 0 ? /* @__PURE__ */ h("span", null, X.aucuneVoie) : /* @__PURE__ */ h(Donnee, { valeur: voies.join(", "), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: X.espaceLibre }, /* @__PURE__ */ h(Donnee, { valeur: props.executant.espace_libre_mio ?? null }))), !c ? /* @__PURE__ */ h("p", { className: "acp-discret" }, X.aucuneCarte) : c.connue === false ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, X.carteInconnue) : /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: X.projet }, /* @__PURE__ */ h(Donnee, { valeur: c.projet_titre })), /* @__PURE__ */ h(Ligne, { libelle: X.carte }, /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: c.titre }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: c.carte, mono: true })))), /* @__PURE__ */ h(Ligne, { libelle: X.role }, /* @__PURE__ */ h(Donnee, { valeur: c.role })), /* @__PURE__ */ h(Ligne, { libelle: X.voie }, /* @__PURE__ */ h(Donnee, { valeur: c.voie, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: X.modeleDemande }, /* @__PURE__ */ h(Donnee, { valeur: c.modele_demande, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: X.modeleServi }, /* @__PURE__ */ h(Donnee, { valeur: c.modele_servi, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: X.statut }, /* @__PURE__ */ h(Donnee, { valeur: c.statut, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: X.tenueParExecutant }, /* @__PURE__ */ h(OuiNon, { valeur: c.a_nous })), /* @__PURE__ */ h(Ligne, { libelle: X.dernierBattement }, /* @__PURE__ */ h(Horodatage, { valeur: c.dernier_battement, relative: true }))));
  }
  function VoiesFermees(props) {
    const fermees = Object.entries(props.executant.voies_fermees ?? {});
    const attente = Array.isArray(props.executant.cartes_en_attente_de_voie) ? props.executant.cartes_en_attente_de_voie : [];
    return /* @__PURE__ */ h(Carte, { titre: X.voiesFermeesTitre, id: "acp-poste-voies-fermees" }, fermees.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, X.aucuneVoieFermee) : /* @__PURE__ */ h("ul", { className: "acp-liste" }, fermees.map(([voie, raison]) => /* @__PURE__ */ h("li", { key: voie, className: "acp-etat" }, /* @__PURE__ */ h(Donnee, { valeur: voie, mono: true }), " ", /* @__PURE__ */ h(Donnee, { valeur: raison })))), attente.length > 0 ? /* @__PURE__ */ h("div", { className: "acp-groupe" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, X.enAttenteDeVoie), /* @__PURE__ */ h("ul", { className: "acp-liste" }, attente.map((a, rang) => /* @__PURE__ */ h("li", { key: a.carte ?? String(rang), className: "acp-etat" }, /* @__PURE__ */ h(Donnee, { valeur: a.titre }), " ", /* @__PURE__ */ h(Donnee, { valeur: a.voie, mono: true }), /* @__PURE__ */ h("span", { className: "acp-discret" }, X.depuis), " ", /* @__PURE__ */ h(Horodatage, { valeur: a.depuis, relative: true }))))) : null);
  }
  function Branche(props) {
    const b = props.branche;
    const [copie, fixerCopie] = useState(null);
    const copier = async () => {
      const presse = globalThis.navigator?.clipboard;
      if (!b.commande || !presse || typeof presse.writeText !== "function") {
        fixerCopie("impossible");
        return;
      }
      try {
        await presse.writeText(b.commande);
        fixerCopie("ok");
      } catch {
        fixerCopie("impossible");
      }
    };
    return /* @__PURE__ */ h("li", { className: "acp-entree" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: X.projet }, /* @__PURE__ */ h(Donnee, { valeur: b.projet_titre })), /* @__PURE__ */ h(Ligne, { libelle: X.branche }, /* @__PURE__ */ h(Donnee, { valeur: b.branche, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: X.tete }, /* @__PURE__ */ h(Donnee, { valeur: b.tete, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: X.termineLe }, /* @__PURE__ */ h(Horodatage, { valeur: b.termine_le })), /* @__PURE__ */ h(Ligne, { libelle: X.commande }, /* @__PURE__ */ h(Donnee, { valeur: b.commande, mono: true }))), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: X.copier, surClic: copier })), copie === "ok" ? /* @__PURE__ */ h("p", { className: "acp-succes", role: "status" }, X.copie) : null, copie === "impossible" ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, X.copieImpossible) : null);
  }
  function BranchesPretes(props) {
    return /* @__PURE__ */ h(Carte, { titre: X.branchesTitre, id: "acp-poste-branches" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, X.branchesAide), props.branches.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, X.aucuneBranche) : /* @__PURE__ */ h("ul", { className: "acp-entrees acp-entrees--une" }, props.branches.map((b, rang) => /* @__PURE__ */ h(Branche, { key: `${b.branche ?? rang}`, branche: b }))));
  }
  function Executant(props) {
    const e = props.executant;
    if (!e || e.connu !== true) return null;
    const linux = e.plateforme === "linux";
    const branches = Array.isArray(e.branches_pretes) ? e.branches_pretes : [];
    return /* @__PURE__ */ h("div", { className: "acp-grille" }, linux ? /* @__PURE__ */ h(Isolement, { isolement: e.isolement }) : null, /* @__PURE__ */ h(Conditions, { executant: e }), /* @__PURE__ */ h(CarteEnCours, { carte: e.carte_en_cours, executant: e }), /* @__PURE__ */ h(VoiesFermees, { executant: e }), /* @__PURE__ */ h(BranchesPretes, { branches }), typeof e.revues === "number" && e.revues > 0 ? /* @__PURE__ */ h(Carte, { titre: X.revuesEnAttente, id: "acp-poste-revues" }, /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: e.revues }))) : null);
  }

  // src/poste/libelles.ts
  var L = (texte, famille) => ({ texte, famille });
  function libelleEtatDuPoste(etat) {
    const e = T.poste.etats;
    switch (etat) {
      case "non_configure":
        return L(e.nonConfigure, "neutre");
      case "a_confirmer":
        return L(e.aConfirmer, "degrade");
      case "en_ligne":
        return L(e.enLigne, "succes");
      case "hors_ligne":
        return L(e.horsLigne, "neutre");
      case "redeploiement":
        return L(e.redeploiement, "degrade");
      case "revoque":
        return L(e.revoque, "echec");
      default:
        return null;
    }
  }
  function libelleBadge(badge) {
    const b = T.poste.badges;
    switch (badge) {
      case "releve_du_compte":
        return L(b.releveDuCompte, "succes");
      case "liste_de_secours":
        return L(b.listeDeSecours, "echec");
      case "liste_de_secours_probable":
        return L(b.listeDeSecoursProbable, "degrade");
      case "liste_acceptee":
        return L(b.listeAcceptee, "succes");
      case "alias_documentes":
        return L(b.aliasDocumentes, "actif");
      case "perime":
        return L(b.perime, "degrade");
      case "inconnu":
        return L(b.inconnu, "neutre");
      case "releve_factice":
        return L(b.releveFactice, "degrade");
      case "indisponible":
        return L(b.indisponible, "echec");
      default:
        return null;
    }
  }
  function libelleEtatTable(etat) {
    const e = T.poste.etatsTable;
    switch (etat) {
      case "non_validee":
        return L(e.nonValidee, "neutre");
      case "validee":
        return L(e.validee, "succes");
      case "a_revalider":
        return L(e.aRevalider, "degrade");
      default:
        return null;
    }
  }
  function libelleEtatQuotas(etat) {
    const e = T.poste.etatsQuotas;
    switch (etat) {
      case "releve":
        return L(e.releve, "succes");
      case "perime":
        return L(e.perime, "degrade");
      case "inconnu":
        return L(e.inconnu, "neutre");
      default:
        return null;
    }
  }
  function libelleConnexionCodex(etat) {
    const c = T.poste.connexionsCodex;
    switch (etat) {
      case "compte_chatgpt":
        return L(c.compteChatgpt, "succes");
      case "cle_api":
        return L(c.cleApi, "echec");
      case "autre":
        return L(c.autre, "degrade");
      case "non_connecte":
        return L(c.nonConnecte, "neutre");
      case "inconnu":
        return L(c.inconnu, "neutre");
      default:
        return null;
    }
  }
  function libelleConnexionClaude(etat) {
    const c = T.poste.connexionsClaude;
    switch (etat) {
      case "jeton_reconnu":
        return L(c.jetonReconnu, "succes");
      case "jeton_present_non_verifie":
        return L(c.jetonPresentNonVerifie, "degrade");
      case "refuse":
        return L(c.refuse, "echec");
      case "jeton_absent":
        return L(c.jetonAbsent, "neutre");
      case "inconnu":
        return L(c.inconnu, "neutre");
      default:
        return null;
    }
  }
  function libelleGenreOrdre(genre) {
    const g = T.poste.genresOrdre;
    return genre === "releve" ? g.releve : genre === "pause" ? g.pause : genre === "reprise" ? g.reprise : null;
  }
  var CLASSES = {
    exploration: T.poste.classes.exploration,
    planification: T.poste.classes.planification,
    synthese: T.poste.classes.synthese,
    repondre: T.poste.classes.repondre,
    recherche_web: T.poste.classes.rechercheWeb,
    architecture: T.poste.classes.architecture,
    implementation: T.poste.classes.implementation,
    debogage_tests: T.poste.classes.debogageTests,
    petite_tache: T.poste.classes.petiteTache,
    documentation: T.poste.classes.documentation,
    relecture: T.poste.classes.relecture
  };
  function libelleClasse(classe) {
    return typeof classe === "string" && classe in CLASSES ? CLASSES[classe] ?? null : null;
  }
  function libelleVoie(voie) {
    const v = T.projets.voies;
    return voie === "hermes" ? v.hermes : voie === "poste-codex" ? v.posteCodex : voie === "poste-claude" ? v.posteClaude : null;
  }

  // src/poste/EtatPoste.tsx
  function OuiNon2(props) {
    if (typeof props.valeur !== "boolean") return /* @__PURE__ */ h(Donnee, { valeur: null });
    return /* @__PURE__ */ h("span", null, props.valeur ? T.commun.oui : T.commun.non);
  }
  function Bandeau(props) {
    const etat = props.donnees.poste;
    const machine = props.donnees.machine?.machine;
    const executant = props.donnees.executant?.hote === "railway";
    return /* @__PURE__ */ h(Carte, { titre: executant ? T.poste.etatTitreExecutant : T.poste.etatTitre, id: "acp-poste-etat" }, /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatDuPoste(etat?.etat), brut: etat?.etat }), etat?.etat === "a_confirmer" ? /* @__PURE__ */ h(Donnee, { valeur: machine?.empreinte, mono: true }) : null, etat?.etat === "en_ligne" ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.vu), " ", /* @__PURE__ */ h(Horodatage, { valeur: etat.derniere_vue, relative: true })) : null, (etat?.etat === "hors_ligne" || etat?.etat === "redeploiement") && etat.hors_ligne_depuis ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.depuis), " ", /* @__PURE__ */ h(Horodatage, { valeur: etat.hors_ligne_depuis })) : null, etat?.etat === "revoque" ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.revoqueLe), " ", /* @__PURE__ */ h(Horodatage, { valeur: machine?.revoque_le })) : null), etat?.message ? /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: etat.message })) : null, machine && machine.politique_valide === false ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.poste.politiqueInvalide) : null, etat?.pause_reclamations ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.poste.pauseReclamations) : null, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.cartesEnAttente }, /* @__PURE__ */ h(Donnee, { valeur: typeof etat?.cartes_en_attente === "number" ? etat.cartes_en_attente : null }))));
  }
  function Confirmation(props) {
    const [saisie, fixerSaisie] = useState("");
    const envoi = useEnvoi();
    const envoyer = async (evenement) => {
      evenement.preventDefault();
      const fait = await envoi.envoyer(() => confirmer(String(props.machine.id ?? ""), saisie));
      if (fait) props.apres();
    };
    return /* @__PURE__ */ h(Carte, { titre: T.poste.confirmerTitre, id: "acp-poste-confirmation" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.empreinteAnnoncee }, /* @__PURE__ */ h(Donnee, { valeur: props.machine.empreinte, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.nom }, /* @__PURE__ */ h(Donnee, { valeur: props.machine.nom }))), /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-poste-empreinte-aide" }, T.poste.empreinteAide), /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: envoyer }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-poste-empreinte" }, T.poste.champEmpreinte), /* @__PURE__ */ h(
      "input",
      {
        id: "acp-poste-empreinte",
        value: saisie,
        autoComplete: "off",
        spellCheck: false,
        "aria-describedby": "acp-poste-empreinte-aide",
        onChange: (e) => fixerSaisie(e.currentTarget.value)
      }
    )), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { type: "submit", libelle: T.poste.confirmer, principal: true, desactive: envoi.etat.etat === "envoi" || !saisie.trim() }))), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat, reussite: T.poste.confirme }));
  }
  function Revocation(props) {
    const [ouvert, fixerOuvert] = useState(false);
    const [motif, fixerMotif] = useState("");
    const envoi = useEnvoi();
    const envoyer = async () => {
      const fait = await envoi.envoyer(() => revoquer(String(props.machine.id ?? ""), motif));
      if (fait) {
        fixerOuvert(false);
        props.apres();
      }
    };
    return /* @__PURE__ */ h(Carte, { titre: T.poste.revoquerTitre, id: "acp-poste-revocation" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.revoquerAide), !ouvert ? /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.poste.revoquer, danger: true, surClic: () => fixerOuvert(true) })) : /* @__PURE__ */ h("div", { className: "acp-confirmation", role: "group", "aria-labelledby": "acp-poste-revoquer-question" }, /* @__PURE__ */ h("p", { id: "acp-poste-revoquer-question" }, T.poste.revoquerQuestion), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-poste-motif" }, T.poste.champMotif), /* @__PURE__ */ h("input", { id: "acp-poste-motif", value: motif, maxLength: 200, onChange: (e) => fixerMotif(e.currentTarget.value) })), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.poste.confirmerRevocation,
        danger: true,
        surClic: envoyer,
        desactive: envoi.etat.etat === "envoi" || !motif.trim()
      }
    ), /* @__PURE__ */ h(Bouton, { libelle: T.poste.annuler, surClic: () => fixerOuvert(false) }))), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat, reussite: T.poste.revoque }));
  }
  function Releve(props) {
    const envoi = useEnvoi();
    const envoyer = async () => {
      const fait = await envoi.envoyer(() => releverMaintenant());
      if (fait) props.apres();
    };
    const message = envoi.etat.etat === "ok" ? envoi.etat.resultat?.message : null;
    return /* @__PURE__ */ h(Carte, { titre: T.poste.releverTitre, id: "acp-poste-releve" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.releverAide), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.poste.releverMaintenant, surClic: envoyer, desactive: envoi.etat.etat === "envoi" })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }), typeof message === "string" ? /* @__PURE__ */ h("p", { className: "acp-succes", role: "status" }, /* @__PURE__ */ h(Donnee, { valeur: message })) : null);
  }
  function Machine(props) {
    const m = props.machine;
    return /* @__PURE__ */ h(Carte, { titre: T.poste.machineTitre, id: "acp-poste-machine" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.nom }, /* @__PURE__ */ h(Donnee, { valeur: m.nom })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.empreinte }, /* @__PURE__ */ h(Donnee, { valeur: m.empreinte, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.versionPoste }, /* @__PURE__ */ h(Donnee, { valeur: m.version_poste, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.protocole }, /* @__PURE__ */ h(Donnee, { valeur: m.protocole, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.enroleLe }, /* @__PURE__ */ h(Horodatage, { valeur: m.cree_le })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.confirmeLe }, /* @__PURE__ */ h(Horodatage, { valeur: m.confirme_le })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.derniereRequete }, /* @__PURE__ */ h(Horodatage, { valeur: m.derniere_requete, relative: true }))));
  }
  function Inventaire(props) {
    const inventaire = props.donnees.inventaire;
    const c = inventaire?.contenu ?? {};
    if (!inventaire) {
      return /* @__PURE__ */ h(Carte, { titre: T.poste.inventaireTitre, id: "acp-poste-inventaire" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucunInventaire));
    }
    const bac = c.bac_a_sable_codex ?? {};
    const versions = c.versions ?? {};
    const depots = Array.isArray(c.depots) ? c.depots : [];
    return /* @__PURE__ */ h("div", { className: "acp-grille" }, /* @__PURE__ */ h(Carte, { titre: T.poste.inventaireTitre, id: "acp-poste-inventaire" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.recuLe }, /* @__PURE__ */ h(Horodatage, { valeur: inventaire.recu_le })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.releveLe }, /* @__PURE__ */ h(Horodatage, { valeur: inventaire.releve_le })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.versionPoste }, /* @__PURE__ */ h(Donnee, { valeur: c.version_poste, mono: true })))), /* @__PURE__ */ h(Carte, { titre: T.poste.compteTitre, id: "acp-poste-compte" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.compte }, c.poste?.compte === "dedie" ? /* @__PURE__ */ h("span", null, T.poste.compteDedie) : c.poste?.compte === "proprietaire" ? /* @__PURE__ */ h("span", null, T.poste.compteProprietaire) : c.poste?.compte === "uid_dedie" ? /* @__PURE__ */ h("span", null, T.poste.compteUidDedie) : /* @__PURE__ */ h(Donnee, { valeur: c.poste?.compte })), c.poste?.plateforme === "linux" ? /* @__PURE__ */ h(Ligne, { libelle: T.poste.executant.noyau }, /* @__PURE__ */ h(Donnee, { valeur: c.poste?.noyau, mono: true })) : /* @__PURE__ */ h(Ligne, { libelle: T.poste.windows }, /* @__PURE__ */ h(Donnee, { valeur: c.poste?.windows, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.python }, /* @__PURE__ */ h(Donnee, { valeur: c.poste?.python, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.empreintePolitique }, /* @__PURE__ */ h(Donnee, { valeur: c.poste?.politique_empreinte, mono: true })))), /* @__PURE__ */ h(Carte, { titre: T.poste.versionsTitre, id: "acp-poste-versions" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, ["codex", "claude"].map((cle) => /* @__PURE__ */ h(Ligne, { key: cle, libelle: cle === "codex" ? T.poste.codex : T.poste.claude }, /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.lue), " ", /* @__PURE__ */ h(Donnee, { valeur: versions[cle]?.lue, mono: true }), /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.testee), " ", /* @__PURE__ */ h(Donnee, { valeur: versions[cle]?.testee, mono: true }), /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.conformite), " ", /* @__PURE__ */ h(OuiNon2, { valeur: versions[cle]?.conforme })))))), c.poste?.plateforme === "linux" ? null : /* @__PURE__ */ h(Carte, { titre: T.poste.bacTitre, id: "acp-poste-bac" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.readiness }, /* @__PURE__ */ h(Donnee, { valeur: bac.readiness, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.modeLu }, /* @__PURE__ */ h(Donnee, { valeur: bac.mode_lu, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.origineMode }, /* @__PURE__ */ h(Donnee, { valeur: bac.origine_mode, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.palierLu }, /* @__PURE__ */ h(Donnee, { valeur: bac.palier_lu, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.stockage }, /* @__PURE__ */ h(Donnee, { valeur: bac.stockage_identifiants_lu, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.ecritureAdmise }, /* @__PURE__ */ h(OuiNon2, { valeur: bac.ecriture_admise })), bac.raison ? /* @__PURE__ */ h(Ligne, { libelle: T.poste.raison }, /* @__PURE__ */ h(Donnee, { valeur: bac.raison })) : null)), /* @__PURE__ */ h(Carte, { titre: T.poste.connexionsTitre, id: "acp-poste-connexions" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.codex }, /* @__PURE__ */ h(Etiquette, { libelle: libelleConnexionCodex(c.connexions?.codex), brut: c.connexions?.codex })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.offre }, /* @__PURE__ */ h(Donnee, { valeur: c.connexions?.plan_codex, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.claude }, /* @__PURE__ */ h(Etiquette, { libelle: libelleConnexionClaude(c.connexions?.claude), brut: c.connexions?.claude })))), /* @__PURE__ */ h(Carte, { titre: T.poste.depotsTitre, id: "acp-poste-depots" }, depots.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucunDepot) : /* @__PURE__ */ h("ul", { className: "acp-liste" }, depots.map((d, i) => /* @__PURE__ */ h("li", { key: `${d.alias ?? i}` }, /* @__PURE__ */ h(Donnee, { valeur: d.alias, mono: true }))))));
  }
  function EtatPoste(props) {
    const lecture = useDonnees(lirePostePage, props.jeton, ["poste", "projets", "pause", "quotas"]);
    const donnees = lecture.valeur;
    if (donnees === null) {
      return lecture.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : /* @__PURE__ */ h(BlocErreur, { erreur: lecture.erreur, message: T.poste.indisponible });
    }
    const etat = donnees.poste?.etat;
    const machine = donnees.machine?.machine ?? null;
    const alertes = Array.isArray(donnees.alertes) ? donnees.alertes : [];
    const ordres = Array.isArray(donnees.ordres) ? donnees.ordres : [];
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, lecture.erreur !== null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.poste.actualisationImpossible) : null, /* @__PURE__ */ h(Bandeau, { donnees }), etat === "non_configure" || etat === "revoque" || etat === "a_confirmer" ? /* @__PURE__ */ h(Carte, { titre: T.poste.enrolerTitre, id: "acp-poste-enroler" }, /* @__PURE__ */ h(Enrolement, { apres: props.apres })) : null, etat === "a_confirmer" && machine ? /* @__PURE__ */ h(Confirmation, { machine, apres: props.apres }) : null, machine && machine.etat !== "revoque" ? /* @__PURE__ */ h(Machine, { machine }) : null, machine && machine.etat === "actif" ? /* @__PURE__ */ h(Releve, { apres: props.apres }) : null, /* @__PURE__ */ h(Executant, { executant: donnees.executant }), alertes.length > 0 ? /* @__PURE__ */ h(Carte, { titre: T.poste.alertesTitre, id: "acp-poste-alertes" }, /* @__PURE__ */ h("ul", { className: "acp-liste" }, alertes.map((a, i) => /* @__PURE__ */ h("li", { key: i }, /* @__PURE__ */ h(Donnee, { valeur: a }))))) : null, machine && machine.etat === "actif" ? /* @__PURE__ */ h(Carte, { titre: T.poste.ordresTitre, id: "acp-poste-ordres" }, ordres.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucunOrdre) : /* @__PURE__ */ h("ul", { className: "acp-liste" }, ordres.map((o) => /* @__PURE__ */ h("li", { key: o.id, className: "acp-etat" }, /* @__PURE__ */ h(Donnee, { valeur: libelleGenreOrdre(o.genre) ?? o.genre }), /* @__PURE__ */ h(Horodatage, { valeur: o.cree_le, relative: true }), /* @__PURE__ */ h("span", { className: "acp-discret" }, o.livre ? T.poste.livre : T.poste.nonLivre))))) : null, /* @__PURE__ */ h(Inventaire, { donnees }), machine && machine.etat !== "revoque" ? /* @__PURE__ */ h(Revocation, { machine, apres: props.apres }) : null);
  }

  // src/poste/Quotas.tsx
  function pourcentage(valeur) {
    return typeof valeur === "number" && Number.isFinite(valeur) && valeur >= 0 && valeur <= 100 ? valeur : null;
  }
  function Jauge(props) {
    const utilise = pourcentage(props.fenetre.used_percent);
    const seuil = pourcentage(props.seuil);
    const depasse = utilise !== null && seuil !== null && utilise >= seuil;
    return /* @__PURE__ */ h("div", { className: "acp-jauge-bloc" }, /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.fenetre), " ", /* @__PURE__ */ h(Donnee, { valeur: props.fenetre.key, mono: true }), typeof props.fenetre.window_minutes === "number" ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: props.fenetre.window_minutes }), " ", /* @__PURE__ */ h("span", null, T.poste.minutes)) : null), /* @__PURE__ */ h(
      "div",
      {
        className: depasse ? "acp-jauge acp-jauge--depasse" : "acp-jauge",
        role: "meter",
        "aria-labelledby": props.id,
        "aria-valuemin": 0,
        "aria-valuemax": 100,
        "aria-valuenow": utilise ?? void 0
      },
      /* @__PURE__ */ h("span", { className: "acp-jauge__plein", style: { width: `${utilise ?? 0}%` } }),
      seuil !== null ? /* @__PURE__ */ h("span", { className: "acp-jauge__seuil", style: { left: `${seuil}%` } }) : null
    ), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.utilise }, /* @__PURE__ */ h("span", { id: props.id }, /* @__PURE__ */ h(Donnee, { valeur: utilise === null ? null : `${utilise} %` }))), /* @__PURE__ */ h(Ligne, { libelle: T.poste.restant }, /* @__PURE__ */ h(Donnee, { valeur: pourcentage(props.fenetre.remaining_percent) === null ? null : `${props.fenetre.remaining_percent} %` })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.remiseAZero }, /* @__PURE__ */ h(Horodatage, { valeur: props.fenetre.resets_at }))));
  }
  function Compteur(props) {
    const c = props.compteur;
    const fenetres = Array.isArray(c.windows) ? c.windows : [];
    return /* @__PURE__ */ h("div", { className: "acp-groupe" }, /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.compteur), " ", /* @__PURE__ */ h(Donnee, { valeur: c.limit_id, mono: true }), c.limit_reached === true ? /* @__PURE__ */ h("span", { className: "acp-pastille acp-pastille--echec" }, T.poste.limiteAtteinte) : null), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.offre }, /* @__PURE__ */ h(Donnee, { valeur: c.plan, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.releveLe }, /* @__PURE__ */ h(Horodatage, { valeur: c.observed_at }))), c.status !== "ok" && c.detail ? /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: c.detail })) : null, fenetres.map((f, i) => /* @__PURE__ */ h(Jauge, { key: `${f.key ?? i}`, fenetre: f, seuil: props.seuil, id: `${props.prefixe}-${c.limit_id ?? "c"}-${i}` })));
  }
  function Voie(props) {
    const q = props.quotas ?? {};
    const compteurs = Array.isArray(q.compteurs) ? q.compteurs : [];
    const seuil = typeof q.seuil_pct === "number" ? q.seuil_pct : null;
    const id = `acp-quotas-${props.voie}`;
    return /* @__PURE__ */ h(Carte, { titre: libelleVoie(props.voie) ?? props.voie, id }, /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatQuotas(q.etat), brut: q.etat }), q.releve_le ? /* @__PURE__ */ h(Horodatage, { valeur: q.releve_le }) : null), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.seuil }, /* @__PURE__ */ h(Donnee, { valeur: seuil === null ? null : `${seuil} %` }))), q.source_libelle ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: q.source_libelle })) : null, q.detail ? /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: q.detail })) : null, compteurs.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucunCompteur) : compteurs.map((c, i) => /* @__PURE__ */ h(Compteur, { key: `${c.limit_id ?? i}`, compteur: c, seuil, prefixe: id })));
  }
  function Quotas(props) {
    const lecture = useDonnees(lireQuotas, props.jeton, ["quotas", "poste"]);
    const envoi = useEnvoi();
    const vue = lecture.valeur;
    if (vue === null) {
      return lecture.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : /* @__PURE__ */ h(BlocErreur, { erreur: lecture.erreur, message: T.poste.indisponible });
    }
    const relever = async () => {
      const fait = await envoi.envoyer(() => releverMaintenant());
      if (fait) props.apres();
    };
    const message = envoi.etat.etat === "ok" ? envoi.etat.resultat?.message : null;
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, lecture.erreur !== null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.poste.actualisationImpossible) : null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.quotasIntro), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.poste.releverMaintenant, surClic: relever, desactive: envoi.etat.etat === "envoi" })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }), typeof message === "string" ? /* @__PURE__ */ h("p", { className: "acp-succes", role: "status" }, /* @__PURE__ */ h(Donnee, { valeur: message })) : null, /* @__PURE__ */ h("div", { className: "acp-grille" }, /* @__PURE__ */ h(Voie, { voie: "poste-codex", quotas: vue["poste-codex"] }), /* @__PURE__ */ h(Voie, { voie: "poste-claude", quotas: vue["poste-claude"] }), /* @__PURE__ */ h(Carte, { titre: T.poste.hermesTitre, id: "acp-quotas-hermes" }, /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: vue.hermes?.libelle })))));
  }

  // src/poste/EditeurClasse.tsx
  function modelesDe(contexte, voie) {
    const cle = voie === "hermes" ? "poste-codex" : voie;
    const modeles = cle ? contexte.voies[cle]?.modeles : void 0;
    return Array.isArray(modeles) ? modeles : [];
  }
  function avecModeleParDefaut(modeles) {
    return modeles.some((m) => m.isDefault === true);
  }
  function effortsDe(contexte, entree) {
    if (entree.voie === "hermes") return [];
    const modele = modelesDe(contexte, entree.voie).find((m) => m.id === entree.modele);
    return Array.isArray(modele?.supportedReasoningEfforts) ? modele.supportedReasoningEfforts : [];
  }
  function LigneEntree(props) {
    const { classe, rang, entree, contexte } = props;
    const id = `acp-routage-${classe}-${rang}`;
    const modeles = modelesDe(contexte, entree.voie);
    const efforts = effortsDe(contexte, entree);
    const hermes = entree.voie === "hermes";
    const choixExige = !hermes && !avecModeleParDefaut(modeles);
    return /* @__PURE__ */ h("div", { className: "acp-entree-routage", role: "group", "aria-labelledby": `${id}-titre` }, /* @__PURE__ */ h("p", { className: "acp-discret", id: `${id}-titre` }, /* @__PURE__ */ h("span", null, T.poste.rang), " ", /* @__PURE__ */ h(Donnee, { valeur: rang + 1 })), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: `${id}-voie` }, T.poste.champVoie), /* @__PURE__ */ h(
      "select",
      {
        id: `${id}-voie`,
        value: entree.voie ?? "",
        onChange: (e) => props.changer({
          voie: e.currentTarget.value,
          modele: null,
          effort: null,
          palier: entree.palier ?? null
        })
      },
      props.voies.map((v) => /* @__PURE__ */ h("option", { key: v, value: v, "data-acp-donnee": libelleVoie(v) ? void 0 : "" }, libelleVoie(v) ?? v))
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: `${id}-modele` }, T.poste.champModele), /* @__PURE__ */ h(
      "select",
      {
        id: `${id}-modele`,
        value: entree.modele ?? "",
        onChange: (e) => props.changer({ ...entree, modele: e.currentTarget.value || null, effort: null })
      },
      /* @__PURE__ */ h("option", { value: "", disabled: choixExige }, hermes ? T.poste.modeleDuProfil : choixExige ? T.poste.modeleAChoisir : T.poste.modeleParDefaut),
      modeles.map((m) => /* @__PURE__ */ h("option", { key: m.id, value: m.id, "data-acp-donnee": "" }, m.id))
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: `${id}-effort` }, T.poste.champEffort), /* @__PURE__ */ h(
      "select",
      {
        id: `${id}-effort`,
        value: entree.effort ?? "",
        onChange: (e) => props.changer({ ...entree, effort: e.currentTarget.value || null })
      },
      /* @__PURE__ */ h("option", { value: "" }, T.poste.effortParDefaut),
      efforts.map((effort) => /* @__PURE__ */ h("option", { key: effort, value: effort, "data-acp-donnee": "" }, effort))
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: `${id}-palier` }, T.poste.champPalier), /* @__PURE__ */ h(
      "select",
      {
        id: `${id}-palier`,
        value: entree.palier ?? "",
        onChange: (e) => props.changer({ ...entree, palier: e.currentTarget.value || null })
      },
      /* @__PURE__ */ h("option", { value: "" }, T.poste.palierStandard),
      contexte.paliers.filter((p) => p !== "default").map((p) => /* @__PURE__ */ h("option", { key: p, value: p, "data-acp-donnee": "" }, p))
    )), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.poste.retirer, surClic: props.retirer })));
  }
  function EditeurClasse(props) {
    const { classe, vue, brouillon } = props;
    const voies = Array.isArray(vue.voies) ? vue.voies : [];
    const suggestion = vue.suggestion ?? {};
    const jugees = Array.isArray(vue.entrees) ? vue.entrees : [];
    const id = `acp-routage-${classe}`;
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": id }, /* @__PURE__ */ h("h3", { className: "acp-carte__titre", id }, libelleClasse(classe) ?? classe), /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatTable(vue.etat), brut: vue.etat })), jugees.length > 0 ? /* @__PURE__ */ h("ul", { className: "acp-liste" }, jugees.map((e, i) => /* @__PURE__ */ h("li", { key: i, className: "acp-groupe" }, /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h("span", { className: `acp-pastille acp-pastille--${e.admise ? "succes" : "echec"}` }, e.admise ? T.poste.entreeAdmise : T.poste.entreeRefusee), /* @__PURE__ */ h(Donnee, { valeur: [e.voie, e.modele, e.effort, e.palier].filter(Boolean).join(" \xB7 "), mono: true })), !e.admise && e.message ? /* @__PURE__ */ h(Donnee, { valeur: e.message }) : null))) : /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucuneEntree), brouillon.map((entree, rang) => /* @__PURE__ */ h(
      LigneEntree,
      {
        key: rang,
        classe,
        rang,
        entree,
        voies,
        contexte: props.contexte,
        changer: (nouvelle) => props.changer(brouillon.map((e, i) => i === rang ? nouvelle : e)),
        retirer: () => props.changer(brouillon.filter((_e, i) => i !== rang))
      }
    )), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.poste.ajouterEntree,
        desactive: voies.length === 0 || brouillon.length >= 8,
        surClic: () => props.changer([...brouillon, {
          voie: voies[0],
          modele: null,
          effort: null,
          palier: null
        }])
      }
    ), Array.isArray(suggestion.entrees) && suggestion.entrees.length > 0 ? /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.poste.appliquerSuggestion,
        surClic: () => props.changer((suggestion.entrees ?? []).map((e) => ({ ...e })))
      }
    ) : null), suggestion.libelle ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: suggestion.libelle })) : null, (suggestion.remarques ?? []).map((r, i) => /* @__PURE__ */ h("p", { key: i, className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: r }))));
  }

  // src/poste/Politique.tsx
  function liste(texte) {
    return texte.split(",").map((v) => v.trim()).filter(Boolean);
  }
  function Valeurs(props) {
    const valeurs = Array.isArray(props.valeurs) ? props.valeurs.filter((v) => typeof v === "string") : null;
    if (valeurs === null) return /* @__PURE__ */ h(Donnee, { valeur: null });
    if (valeurs.length === 0) return props.vide ? /* @__PURE__ */ h("span", null, props.vide) : /* @__PURE__ */ h(Donnee, { valeur: null });
    return /* @__PURE__ */ h(Donnee, { valeur: valeurs.join(", "), mono: true });
  }
  function PolitiqueHermes(props) {
    const politique = props.vue.politique_hermes ?? {};
    const [efforts, fixerEfforts] = useState(() => (politique.efforts_interdits ?? []).join(", "));
    const [paliers, fixerPaliers] = useState(() => (politique.paliers_admis ?? []).join(", "));
    const [motif, fixerMotif] = useState("");
    const [phrase, fixerPhrase] = useState("");
    const envoi = useEnvoi();
    const envoyer = async (evenement) => {
      evenement.preventDefault();
      const fait = await envoi.envoyer(() => poserPolitique({
        efforts_interdits: liste(efforts),
        paliers_admis: liste(paliers),
        motif,
        confirmation: phrase.trim() || null
      }));
      if (fait) props.apres();
    };
    return /* @__PURE__ */ h(Carte, { titre: T.poste.politiqueTitre, id: "acp-poste-politique" }, /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-poste-politique-aide" }, T.poste.politiqueAide), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.phraseAttendue }, /* @__PURE__ */ h(Donnee, { valeur: politique.confirmation }))), /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: envoyer }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-poste-efforts" }, T.poste.effortsInterdits), /* @__PURE__ */ h(
      "input",
      {
        id: "acp-poste-efforts",
        value: efforts,
        "aria-describedby": "acp-poste-liste-aide",
        onChange: (e) => fixerEfforts(e.currentTarget.value)
      }
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-poste-paliers" }, T.poste.paliersAdmis), /* @__PURE__ */ h(
      "input",
      {
        id: "acp-poste-paliers",
        value: paliers,
        "aria-describedby": "acp-poste-liste-aide",
        onChange: (e) => fixerPaliers(e.currentTarget.value)
      }
    )), /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-poste-liste-aide" }, T.poste.separateurListe), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-poste-politique-motif" }, T.poste.champMotif), /* @__PURE__ */ h(
      "input",
      {
        id: "acp-poste-politique-motif",
        value: motif,
        maxLength: 200,
        onChange: (e) => fixerMotif(e.currentTarget.value)
      }
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-poste-phrase" }, T.poste.phrase), /* @__PURE__ */ h(
      "input",
      {
        id: "acp-poste-phrase",
        value: phrase,
        autoComplete: "off",
        "aria-describedby": "acp-poste-politique-aide",
        onChange: (e) => fixerPhrase(e.currentTarget.value)
      }
    )), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        type: "submit",
        libelle: T.poste.enregistrerPolitique,
        desactive: envoi.etat.etat === "envoi" || !motif.trim()
      }
    ))), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat, reussite: T.poste.politiqueEnregistree }));
  }
  function PolitiqueDuPoste(props) {
    const p = props.politique;
    return /* @__PURE__ */ h(Carte, { titre: T.poste.politiquePosteTitre, id: "acp-poste-politique-poste" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.politiquePosteAide), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.executants }, /* @__PURE__ */ h(Valeurs, { valeurs: p?.executants })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.effortsInterdits }, /* @__PURE__ */ h(Valeurs, { valeurs: p?.efforts_interdits })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.paliersAdmis }, /* @__PURE__ */ h(Valeurs, { valeurs: p?.paliers_admis })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.modelesPermis }, /* @__PURE__ */ h(Valeurs, { valeurs: p?.modeles_codex_permis, vide: T.poste.tousDuReleve })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.aliasPermis }, /* @__PURE__ */ h(Valeurs, { valeurs: p?.alias_claude_permis })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.reseauExecutants }, typeof p?.reseau_executants === "boolean" ? /* @__PURE__ */ h("span", null, p.reseau_executants ? T.commun.oui : T.commun.non) : /* @__PURE__ */ h(Donnee, { valeur: null }))));
  }

  // src/poste/Surcharges.tsx
  function Surcharges(props) {
    const surcharges = Array.isArray(props.vue.surcharges) ? props.vue.surcharges : [];
    const classes = Object.keys(props.vue.classes ?? {});
    const [classe, fixerClasse] = useState(() => classes[0] ?? "");
    const voies = props.vue.classes?.[classe]?.voies ?? [];
    const [voie, fixerVoie] = useState("");
    const [modele, fixerModele] = useState("");
    const [effort, fixerEffort] = useState("");
    const [motif, fixerMotif] = useState("");
    const creation = useEnvoi();
    const desactivation = useEnvoi();
    const voieChoisie = voie && voies.includes(voie) ? voie : voies[0] ?? "";
    const envoyer = async (evenement) => {
      evenement.preventDefault();
      const fait = await creation.envoyer(() => creerSurcharge({
        classe,
        voie: voieChoisie,
        modele: modele.trim() || null,
        effort: effort.trim() || null,
        palier: null,
        motif
      }));
      if (fait) props.apres();
    };
    const desactiver = async (id) => {
      const fait = await desactivation.envoyer(() => desactiverSurcharge(id));
      if (fait) props.apres();
    };
    return /* @__PURE__ */ h(Carte, { titre: T.poste.surchargesTitre, id: "acp-poste-surcharges" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.surchargesAide), surcharges.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucuneSurcharge) : /* @__PURE__ */ h("ul", { className: "acp-liste" }, surcharges.map((s) => /* @__PURE__ */ h("li", { key: s.id, className: "acp-groupe" }, /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h(Donnee, { valeur: libelleClasse(s.classe) ?? s.classe }), /* @__PURE__ */ h(Donnee, { valeur: [s.voie, s.modele, s.effort, s.palier].filter(Boolean).join(" \xB7 "), mono: true }), /* @__PURE__ */ h(Horodatage, { valeur: s.cree_le })), /* @__PURE__ */ h(Donnee, { valeur: s.motif }), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.poste.desactiver,
        surClic: () => desactiver(Number(s.id)),
        desactive: desactivation.etat.etat === "envoi"
      }
    ))))), /* @__PURE__ */ h(RetourEnvoi, { etat: desactivation.etat, reussite: T.poste.surchargeDesactivee }), /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: envoyer }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-classe" }, T.poste.classe), /* @__PURE__ */ h("select", { id: "acp-surcharge-classe", value: classe, onChange: (e) => fixerClasse(e.currentTarget.value) }, classes.map((c) => /* @__PURE__ */ h("option", { key: c, value: c, "data-acp-donnee": libelleClasse(c) ? void 0 : "" }, libelleClasse(c) ?? c)))), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-voie" }, T.poste.champVoie), /* @__PURE__ */ h("select", { id: "acp-surcharge-voie", value: voieChoisie, onChange: (e) => fixerVoie(e.currentTarget.value) }, voies.map((v) => /* @__PURE__ */ h("option", { key: v, value: v, "data-acp-donnee": libelleVoie(v) ? void 0 : "" }, libelleVoie(v) ?? v)))), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-modele" }, T.poste.champModele), /* @__PURE__ */ h("input", { id: "acp-surcharge-modele", value: modele, onChange: (e) => fixerModele(e.currentTarget.value) })), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-effort" }, T.poste.champEffort), /* @__PURE__ */ h("input", { id: "acp-surcharge-effort", value: effort, onChange: (e) => fixerEffort(e.currentTarget.value) })), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-motif" }, T.poste.champMotif), /* @__PURE__ */ h("input", { id: "acp-surcharge-motif", value: motif, maxLength: 200, onChange: (e) => fixerMotif(e.currentTarget.value) })), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        type: "submit",
        libelle: T.poste.creerSurcharge,
        desactive: creation.etat.etat === "envoi" || !motif.trim() || !classe || !voieChoisie
      }
    ))), /* @__PURE__ */ h(RetourEnvoi, { etat: creation.etat, reussite: T.poste.surchargeCreee }));
  }

  // src/poste/Routage.tsx
  function Liste(props) {
    const c = props.catalogue;
    const envoi = useEnvoi();
    const modeles = Array.isArray(c?.modeles) ? c.modeles : [];
    const accepter = async () => {
      if (typeof c?.releve_id !== "number") return;
      const fait = await envoi.envoyer(() => accepterReleve(c.releve_id));
      if (fait) props.apres();
    };
    const id = `acp-routage-liste-${props.voie}`;
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": id }, /* @__PURE__ */ h("h3", { className: "acp-carte__titre", id }, libelleVoie(props.voie) ?? props.voie), /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleBadge(c?.badge), brut: c?.badge }), c?.releve_le ? /* @__PURE__ */ h(Horodatage, { valeur: c.releve_le }) : null, c?.version_cli ? /* @__PURE__ */ h(Donnee, { valeur: c.version_cli, mono: true }) : null), c?.detail ? /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: c.detail })) : null, c?.documentation_lue_le ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: c.documentation_lue_le, mono: true })) : null, modeles.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, !c || c.badge === "inconnu" ? T.poste.aucunReleve : T.poste.aucunModele) : /* @__PURE__ */ h("ul", { className: "acp-liste" }, modeles.map((m) => /* @__PURE__ */ h("li", { key: m.id, className: "acp-groupe" }, /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h(Donnee, { valeur: m.id, mono: true }), m.isDefault === true ? /* @__PURE__ */ h("span", { className: "acp-pastille acp-pastille--actif" }, T.poste.parDefaut) : null), /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.poste.efforts), " ", Array.isArray(m.supportedReasoningEfforts) && m.supportedReasoningEfforts.length === 0 ? /* @__PURE__ */ h("span", null, T.poste.aucunEffort) : Array.isArray(m.supportedReasoningEfforts) ? /* @__PURE__ */ h(Donnee, { valeur: m.supportedReasoningEfforts.join(", "), mono: true }) : /* @__PURE__ */ h("span", null, T.poste.effortsInconnus)), m.resolution_documentee ? /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.poste.resolution), " ", /* @__PURE__ */ h(Donnee, { valeur: m.resolution_documentee, mono: true })) : null))), c?.badge === "liste_de_secours_probable" && typeof c.releve_id === "number" ? /* @__PURE__ */ h("div", { className: "acp-groupe" }, /* @__PURE__ */ h("p", { className: "acp-discret", id: `${id}-accepter` }, T.poste.accepterAide), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.poste.accepterReleve,
        surClic: accepter,
        desactive: envoi.etat.etat === "envoi",
        decritPar: `${id}-accepter`
      }
    )), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat, reussite: T.poste.releveAccepte })) : null);
  }
  function brouillonDepuis(vue) {
    const brouillon = {};
    for (const [classe, c] of Object.entries(vue.classes ?? {})) {
      brouillon[classe] = (c.entrees ?? []).map((e) => ({
        voie: e.voie,
        modele: e.modele ?? null,
        effort: e.effort ?? null,
        palier: e.palier ?? null
      }));
    }
    return brouillon;
  }
  function Table(props) {
    const [brouillon, fixerBrouillon] = useState(() => brouillonDepuis(props.vue));
    const envoi = useEnvoi();
    const contexte = { voies: props.vue.voies ?? {}, paliers: props.vue.politique_hermes?.paliers_admis ?? [] };
    const valider = async () => {
      const classes = {};
      for (const [classe, entrees] of Object.entries(brouillon)) if (entrees.length > 0) classes[classe] = entrees;
      const vue = await envoi.envoyer(() => validerTable(props.vue.releves ?? {}, classes));
      if (vue) {
        fixerBrouillon(brouillonDepuis(vue));
        props.apres();
      }
    };
    const refus = envoi.etat.etat === "erreur" ? refusDeLaTable(envoi.etat.erreur.detail) : [];
    const vide = Object.values(brouillon).every((e) => e.length === 0);
    return /* @__PURE__ */ h(Carte, { titre: T.poste.tableTitre, id: "acp-poste-table" }, /* @__PURE__ */ h("div", { className: "acp-sections" }, Object.entries(props.vue.classes ?? {}).map(([classe, c]) => /* @__PURE__ */ h(
      EditeurClasse,
      {
        key: classe,
        classe,
        vue: c,
        brouillon: brouillon[classe] ?? [],
        contexte,
        changer: (entrees) => fixerBrouillon((avant) => ({ ...avant, [classe]: entrees }))
      }
    ))), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.poste.validerTable, principal: true, surClic: valider, desactive: envoi.etat.etat === "envoi" || vide })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat, reussite: T.poste.tableValidee }), refus.length > 0 ? /* @__PURE__ */ h("div", { className: "acp-erreur", role: "alert" }, /* @__PURE__ */ h("p", null, T.poste.refusDeLaTable), /* @__PURE__ */ h("ul", { className: "acp-liste" }, refus.map((r, i) => /* @__PURE__ */ h("li", { key: i }, /* @__PURE__ */ h(Donnee, { valeur: libelleClasse(r.classe) ?? r.classe }), " ", /* @__PURE__ */ h("span", null, T.poste.rang), " ", /* @__PURE__ */ h(Donnee, { valeur: typeof r.rang === "number" ? r.rang + 1 : null }), " ", /* @__PURE__ */ h(Donnee, { valeur: r.message }))))) : null);
  }
  function Resolutions(props) {
    return /* @__PURE__ */ h(Carte, { titre: T.poste.resolutionsTitre, id: "acp-poste-resolutions" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.resolutionsAide), props.resolutions.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucuneResolution) : props.resolutions.map((r, rang) => /* @__PURE__ */ h("dl", { key: `${r.voie ?? ""}-${r.alias ?? rang}`, className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.executant.voie }, /* @__PURE__ */ h(Donnee, { valeur: r.voie, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.aliasObserve }, /* @__PURE__ */ h(Donnee, { valeur: r.alias, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.executant.modeleServi }, /* @__PURE__ */ h(Donnee, { valeur: r.modele_servi, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.observeeLe }, /* @__PURE__ */ h(Horodatage, { valeur: r.observe_le })))));
  }
  function Routage(props) {
    const lecture = useDonnees(lireRoutage, props.jeton, ["quotas", "poste"]);
    const vue = lecture.valeur;
    if (vue === null) {
      return lecture.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : /* @__PURE__ */ h(BlocErreur, { erreur: lecture.erreur, message: T.poste.indisponible });
    }
    const voies = vue.voies ?? {};
    const cleTable = JSON.stringify(vue.releves ?? {});
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, lecture.erreur !== null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.poste.actualisationImpossible) : null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.routageIntro), /* @__PURE__ */ h(Carte, { titre: T.poste.listesTitre, id: "acp-poste-listes" }, /* @__PURE__ */ h("div", { className: "acp-grille" }, ["poste-codex", "poste-claude"].map((voie) => /* @__PURE__ */ h(Liste, { key: voie, voie, catalogue: voies[voie], apres: props.apres })))), /* @__PURE__ */ h(Resolutions, { resolutions: Array.isArray(vue.resolutions_observees) ? vue.resolutions_observees : [] }), /* @__PURE__ */ h(Table, { key: cleTable, vue, apres: props.apres }), /* @__PURE__ */ h(PolitiqueHermes, { vue, apres: props.apres }), /* @__PURE__ */ h(PolitiqueDuPoste, { politique: vue.politique_poste }), /* @__PURE__ */ h(Surcharges, { vue, apres: props.apres }));
  }

  // src/poste/vue.ts
  var CHEMIN_POSTE = "/poste";
  var VUES = ["etat", "routage", "quotas"];
  function vuePosteDepuisAdresse(recherche) {
    const vue = new URLSearchParams(recherche).get("vue");
    return vue === "routage" || vue === "quotas" ? vue : "etat";
  }
  function rechercheDeVuePoste(vue, recherche = "") {
    const parametres = new URLSearchParams(recherche);
    parametres.delete("vue");
    if (vue !== "etat") parametres.set("vue", vue);
    const texte = parametres.toString();
    return texte ? `?${texte}` : "";
  }
  function pousserVuePoste(vue) {
    try {
      const { pathname, search } = window.location;
      const suivante = `${pathname}${rechercheDeVuePoste(vue, search)}`;
      if (suivante !== `${pathname}${search}`) window.history.pushState(window.history.state, "", suivante);
    } catch {
    }
  }

  // src/poste/Poste.tsx
  var LIBELLES = {
    etat: T.poste.vueEtat,
    routage: T.poste.vueRoutage,
    quotas: T.poste.vueQuotas
  };
  function Onglet(props) {
    const adresse = `${cheminDeBase()}${CHEMIN_POSTE}${rechercheDeVuePoste(props.vue)}`;
    const surClic = (evenement) => {
      if (evenement.defaultPrevented || evenement.button !== 0) return;
      if (evenement.metaKey || evenement.ctrlKey || evenement.shiftKey || evenement.altKey) return;
      evenement.preventDefault();
      props.naviguer(props.vue);
    };
    return /* @__PURE__ */ h(
      "a",
      {
        className: "acp-onglet",
        href: adresse,
        "aria-current": props.vue === props.courante ? "page" : void 0,
        onClick: surClic
      },
      /* @__PURE__ */ h("span", null, LIBELLES[props.vue])
    );
  }
  function Poste() {
    const [vue, fixerVue] = useState(() => vuePosteDepuisAdresse(window.location.search));
    const [jeton, fixerJeton] = useState(0);
    const racine = useRef(null);
    const rafraichir = () => fixerJeton((j) => j + 1);
    const naviguer = (suivante) => {
      fixerVue(suivante);
      pousserVuePoste(suivante);
      rafraichir();
      try {
        racine.current?.scrollIntoView?.({ block: "start" });
      } catch {
      }
    };
    useEffect(() => {
      const surRetour = () => {
        fixerVue(vuePosteDepuisAdresse(window.location.search));
        fixerJeton((j) => j + 1);
      };
      window.addEventListener("popstate", surRetour);
      return () => window.removeEventListener("popstate", surRetour);
    }, []);
    return /* @__PURE__ */ h("div", { className: "acp-page", "data-acp-racine": "poste", ref: racine }, /* @__PURE__ */ h("div", { className: "acp-entete" }, /* @__PURE__ */ h("h1", { className: "acp-titre" }, T.poste.titre), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.intro)), /* @__PURE__ */ h("nav", { className: "acp-onglets", "aria-label": T.poste.navigation }, VUES.map((v) => /* @__PURE__ */ h(Onglet, { key: v, vue: v, courante: vue, naviguer }))), vue === "etat" ? /* @__PURE__ */ h(EtatPoste, { jeton, apres: rafraichir }) : null, vue === "routage" ? /* @__PURE__ */ h(Routage, { jeton, apres: rafraichir }) : null, vue === "quotas" ? /* @__PURE__ */ h(Quotas, { jeton, apres: rafraichir }) : null, /* @__PURE__ */ h(EtatActualisation, null));
  }

  // src/poste/index.ts
  installer({ nom: "acp-poste-vues", page: Poste });
})();
