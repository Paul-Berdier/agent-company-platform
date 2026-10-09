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
      // Relecture finale de P7 : la tâche cron EXÉCUTE le script, qui ne fait qu'enfiler la notification ; Hermes date
      // last_run_at même en échec. Jamais « envoi » ici : « exécution », et l'issue dite d'après last_status.
      bilanEnErreur: "En erreur",
      prochainEnvoi: "Prochaine ex\xE9cution",
      dernierEnvoi: "Derni\xE8re ex\xE9cution",
      bilanDerniereEchec: "Derni\xE8re ex\xE9cution en \xE9chec\xA0: le bilan de ce jour n'est pas garanti. D\xE9tail ci-dessous et sur la page Cron.",
      bilanTacheEnErreur: "Hermes a mis la t\xE2che en erreur\xA0: elle ne s'ex\xE9cutera plus d'elle-m\xEAme. D\xE9tail ci-dessous et sur la page Cron.",
      bilanStatut: "Issue de la derni\xE8re ex\xE9cution (Hermes)",
      bilanErreurHermes: "Message de Hermes",
      bilanCreationRefusee: "Le bilan n'a pas \xE9t\xE9 cr\xE9\xE9\xA0: Hermes a refus\xE9 la t\xE2che (d\xE9tail technique ci-dessous).",
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
      // Relecture finale de P7 (constat produit-12) : la portée exacte du temps réel, là où toute la page ne suit pas.
      actifAccueil: "\xC0 traiter, projets, ex\xE9cutant, quotas et notifications actualis\xE9s en temps r\xE9el tant que la page est visible\xA0; bilan quotidien relu toutes les 2 minutes.",
      noteAccueil: "Sessions r\xE9centes et cartes Syst\xE8me\xA0: lues \xE0 l'ouverture de la page.",
      actifDiscussions: "Discussions en attente actualis\xE9es en temps r\xE9el tant que la page est visible\xA0; liste relue toutes les 2 minutes.",
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
      // Relecture finale de P7 (constat produit-10) : titre d'après l'hôte publié par la machine, jamais « Windows » à tort.
      posteTitreExecutant: "Ex\xE9cutant Railway",
      posteTitreNeutre: "Ex\xE9cutant",
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
      notificationsNonConfigurees: "Notifications non configur\xE9es\xA0: les variables du canal sont d\xE9j\xE0 d\xE9clar\xE9es dans l'IaC Railway\xA0; posez dans Railway celles de Telegram ou de ntfy, ACP_NOTIFICATIONS comprise, puis plan, apply et red\xE9ploiement (docs/refonte/railway.md, \xA7 14).",
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
      // Le réglage se LIT « Vous » (détail du projet), comme « À vous » dans la file ; « Moi » reste le choix du formulaire.
      reponsesVous: "Vous",
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
      // Partie E (cahier P7 § 11.2) : voie fermée pour le dépôt choisi (visibilité mesurée), avec la raison du greffon.
      voiesFermeesPourDepot: "Ferm\xE9 pour ce d\xE9p\xF4t (gris\xE9 dans la liste)",
      aucunExecutantOuvert: "Aucun ex\xE9cutant ouvert pour ce d\xE9p\xF4t. Le projet part sans exploration du d\xE9p\xF4t.",
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
      // Relecture finale de P7 (constat produit-9) : les titres des sections de la file sont ceux de l'Accueil et de la doc.
      questionsTitre: "Questions",
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
      triageTitre: "D\xE9cisions",
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
      revuesTitre: "Revues",
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
      bloqueesTitre: "Cartes arr\xEAt\xE9es",
      // Étape P7 : file Questions, « Qui répond », « Clore » (cahier P7 § 3, § 4.2, § 10).
      fileTitre: "\xC0 traiter",
      aTraiterParVous: "\xC0 traiter par vous",
      chezHermesCompte: "Chez Hermes",
      discussionsNonComptees: "(discussions en attente\xA0: \xE9tat inconnu, non compt\xE9es)",
      cibleTraitee: "Cette demande a d\xE9j\xE0 \xE9t\xE9 trait\xE9e\xA0: elle n'est plus dans la file.",
      cibleIllisible: "Le tableau de cette demande n'a pas pu \xEAtre lu\xA0: son \xE9tat est inconnu (voir \xAB\xA0Tableaux illisibles\xA0\xBB).",
      quiRepondQuestion: "Qui r\xE9pond",
      chezHermes: "Hermes y r\xE9pond",
      aVous: "\xC0 vous",
      carteRepondre: "Carte \xAB\xA0r\xE9pondre\xA0\xBB\xA0:",
      chezHermesAide: "Hermes pr\xE9pare la r\xE9ponse par sa carte \xAB\xA0r\xE9pondre\xA0\xBB\xA0; vous pouvez r\xE9pondre vous-m\xEAme avant lui.",
      bloqueesIntro: "\xAB\xA0Relancer\xA0\xBB remet la carte en route, avec votre consigne si vous en donnez une. Une carte qui rebloque pour la m\xEAme raison revient en d\xE9cision.",
      relancerCarte: "Relancer",
      relanceExecutantAide: "L'agent repart d'une session neuve, sur la branche d\xE9j\xE0 commenc\xE9e.",
      relanceIntegrationAide: "Carte d'int\xE9gration, sans agent\xA0: \xAB\xA0Relancer\xA0\xBB rejoue la m\xEAme fusion des branches, sans consigne. Un conflit revient tant qu'aucune branche ne change\xA0: r\xE9cup\xE9rez les branches sur l'ex\xE9cutant (git bundle) pour trancher, ou cl\xF4turez le projet.",
      relanceeFusion: "La carte repart\xA0: l'ex\xE9cutant rejoue la m\xEAme fusion.",
      relancee: "La carte repart.",
      // Partie E (K25) : carte bloquée pour un secret, travail fautif en quarantaine sur l'exécutant.
      relanceQuarantaineAide: "Bloqu\xE9e pour un secret d\xE9tect\xE9. Le travail fautif reste en quarantaine sur l'ex\xE9cutant, jamais int\xE9gr\xE9 ni pouss\xE9. La relance repart du d\xE9part de la carte, sur une branche neuve et en session neuve.",
      relanceeBrancheNeuve: "La carte repart sur une branche neuve, en session neuve. Le travail en quarantaine n'est pas repris.",
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
        correction: "Correction ins\xE9r\xE9e",
        // Relecture finale de P7 (constat produit-7) : actions de P6 et de P7 journalisées avec le projet.
        relance: "Carte relanc\xE9e",
        reglage_reponses: "Qui r\xE9pond chang\xE9",
        cloture: "Projet clos",
        revue_acceptee: "Revue accept\xE9e",
        revue_refusee: "Revue refus\xE9e",
        integration: "Int\xE9gration demand\xE9e",
        carte_servie: "Carte servie \xE0 l'ex\xE9cutant",
        carte_bloquee: "Carte bloqu\xE9e par l'ex\xE9cutant",
        carte_bloquee_ecart: "Carte bloqu\xE9e\xA0: demande hors de la politique de l'ex\xE9cutant",
        carte_non_construite: "Carte non construite pour l'ex\xE9cutant",
        carte_voie_fermee: "Carte bloqu\xE9e\xA0: voie ferm\xE9e",
        carte_etrangere_bloquee: "Carte \xE9trang\xE8re bloqu\xE9e",
        attente_quota_levee: "Attente de quota lev\xE9e"
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
      // Étape P7, partie E (cahier P7 § 11.2) : visibilité mesurée par l'exécutant, voies ouvertes par dépôt.
      depots: {
        aide: "Visibilit\xE9 mesur\xE9e par l'ex\xE9cutant \xE0 chaque inventaire et avant chaque carte Codex. Priv\xE9 veut dire acc\xE8s anonyme refus\xE9 et lecture avec le jeton r\xE9ussie. Codex ne travaille que sur un d\xE9p\xF4t prouv\xE9 priv\xE9 (D83), Claude sur tout d\xE9p\xF4t (D84).",
        visibilite: "Visibilit\xE9 mesur\xE9e",
        lecture: "Lecture par l'ex\xE9cutant",
        verifieLe: "Mesur\xE9e",
        voies: "Voies pour ce d\xE9p\xF4t",
        ouverte: "Ouverte",
        fermee: "Ferm\xE9e",
        nonMesure: "Jamais mesur\xE9e par l'ex\xE9cutant (Codex ferm\xE9)",
        visibilites: {
          prive: "Priv\xE9",
          public: "Public",
          inconnue: "Inconnue (Codex ferm\xE9)"
        },
        lectures: {
          ok: "R\xE9ussie",
          refusee: "Refus\xE9e",
          inconnue: "Inconnue"
        }
      },
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
      routageIntro: "Une \xE9tape d'un projet suit, dans cet ordre\xA0: la surcharge active du projet ou de la carte\xA0; sinon le choix explicite (ex\xE9cutant et mod\xE8le de l'exploration choisis dans \xAB\xA0Nouveau projet\xA0\xBB, ou fix\xE9s par Hermes dans son plan)\xA0; sinon la premi\xE8re entr\xE9e admise de sa classe dans cette table, Hermes faisant lui-m\xEAme les \xE9tapes d'un projet sans d\xE9p\xF4t qui l'admettent. Les listes viennent du relev\xE9 du poste\xA0; rien n'est devin\xE9, et ce que le poste interdit reste interdit.",
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
    // Étape P7, part D : discussion réduite (greffon acp-discussion, cahier P7 § 9), section à part.
    discussion: {
      titre: "Discussion",
      intro: "Discussion avec Hermes pens\xE9e pour le t\xE9l\xE9phone. La session vit dans le tableau de bord\xA0: fermez la page, reprenez-la depuis un autre appareil, la question en attente vous y attend.",
      limites: "Non pris en charge ici\xA0: d\xE9tail des outils (une ligne par outil), pi\xE8ces jointes, commandes \xAB\xA0/\xA0\xBB, changement de mod\xE8le, mise en forme riche.",
      persistance: "Une question pos\xE9e ici attend une heure au plus et dispara\xEEt si Hermes red\xE9marre\xA0; ce qui doit attendre passe par un projet.",
      navigation: "Navigation de la discussion",
      liste: "Discussions",
      nouvelle: "Nouvelle discussion",
      retourListe: "Toutes les discussions",
      listeTitre: "Discussions r\xE9centes",
      listeIntro: "Les vingt derni\xE8res discussions du tableau de bord, la plus r\xE9cente d'abord.",
      aucune: "Aucune discussion pour l'instant.",
      sansTitre: "Sans titre",
      messages: "Messages",
      activite: "Derni\xE8re activit\xE9",
      enAttente: "En attente d'une r\xE9ponse",
      ouvrir: "Ouvrir",
      ouvrirDiscussion: "Ouvrir la discussion",
      listeIndisponible: "La liste des discussions n'a pas pu \xEAtre lue.",
      attenteInconnue: "Discussions en attente\xA0: \xE9tat inconnu (le tableau de bord n'a pas pu \xEAtre interrog\xE9)\xA0; l'absence de la marque \xAB\xA0En attente d'une r\xE9ponse\xA0\xBB ne veut rien dire.",
      indisponible: "Discussion indisponible\xA0: ce tableau de bord n'expose pas buildWsUrl (contrat 1.1 du SDK).",
      introuvable: "Discussion introuvable\xA0: Hermes ne la conna\xEEt plus (ferm\xE9e, ou perdue au red\xE9marrage).",
      connexion: "Connexion \xE0 Hermes\u2026",
      prete: "Connect\xE9 \xE0 Hermes.",
      reconnexion: "Connexion perdue. Nouvelle tentative dans",
      reconnexionEnCours: "Connexion perdue\xA0: nouvelle tentative en cours\u2026",
      sessionExpiree: "Session expir\xE9e\xA0: reconnectez-vous pour reprendre la discussion (elle vous attend).",
      recharger: "Recharger la page",
      secondes: "s",
      nouvelleIntro: "\xC9crivez votre premier message\xA0: la discussion est cr\xE9\xE9e \xE0 l'envoi.",
      fil: "Messages de la discussion",
      vous: "Vous",
      hermes: "Hermes",
      outil: "Outil\xA0:",
      erreurHermes: "Erreur signal\xE9e par Hermes\xA0:",
      enCours: "R\xE9ponse en cours\u2026",
      interrompu: "Tour interrompu.",
      echoue: "Tour en \xE9chec.",
      etat: "\xC9tat\xA0:",
      message: "Votre message",
      envoyer: "Envoyer",
      interrompre: "Interrompre",
      tourEnCours: "Un tour est en cours\xA0: l'envoi reprend \xE0 sa fin, ou interrompez-le.",
      questionTitre: "Hermes vous pose une question",
      questionsTitre: "Hermes vous pose des questions",
      recommande: "recommand\xE9",
      choixMultiple: "Plusieurs choix possibles.",
      reponseLibre: "R\xE9ponse libre",
      reponseLibreAide: "Remplie, elle l'emporte sur le choix.",
      dejaRepondu: "R\xE9ponse d\xE9j\xE0 enregistr\xE9e\xA0:",
      repondre: "R\xE9pondre",
      refusee: "Demande refus\xE9e automatiquement\xA0: ACP ne traite ni approbation, ni mot de passe, ni secret.",
      demande: "Demande\xA0:",
      retiree: "Question retir\xE9e par Hermes.",
      raison: "Raison\xA0:",
      detail: "D\xE9tail\xA0:",
      erreurs: {
        envoi: "Le message n'a pas \xE9t\xE9 envoy\xE9.",
        creation: "La discussion n'a pas pu \xEAtre cr\xE9\xE9e.",
        reprise: "La discussion n'a pas pu \xEAtre reprise.",
        interruption: "L'interruption a \xE9chou\xE9.",
        reponse: "La r\xE9ponse n'a pas \xE9t\xE9 envoy\xE9e.",
        tour: "Le tour s'est termin\xE9 en erreur."
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
      // Côté poste (relecture de P3) : rien n'est promis hors du plan d'autonomie. Une skill du
      // poste est une candidate non planifiée ; un serveur MCP n'est « reporte-p8 » que si le plan le
      // prévoit en P8, sinon « hors-v1 ».
      case "candidate-poste":
        return "candidate";
      case "reporte-p8":
      case "reportee-p8":
        return "prevueP8";
      case "hors-v1":
        return "horsV1";
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
