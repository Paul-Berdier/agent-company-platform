/* acp-interface 1.0.1 (ACP) — bundle généré par apps/interface/esbuild.mjs depuis apps/interface/src ; ne pas modifier à la main. Aucun code tiers embarqué : React vient du SDK du tableau de bord de Hermes. */

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
  function useRef(initial) {
    return react().useRef(initial);
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

  // src/flux.ts
  var ROUTE_FLUX = "/api/plugins/acp-poste/v1/flux";
  var SUJETS = ["projets", "questions", "poste", "quotas", "notifications", "pause", "discussions"];
  var VERSION_PARTAGE = 1;
  var REPRISES_MS = [1e3, 2e3, 5e3, 1e4, 3e4];
  var FENETRE_ECHECS_MS = 12e4;
  var ECHECS_AVANT_REPLI = 3;
  var NOUVEL_ESSAI_MS = 3e5;
  var FERMETURE_DIFFEREE_MS = 5e3;
  var CHIEN_DE_GARDE_MS = 4e4;
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
      let chien = null;
      const relancerChien = () => {
        if (chien !== null) clearTimeout(chien);
        chien = setTimeout(() => {
          chien = null;
          if (generation === this.generation) controleur.abort();
        }, CHIEN_DE_GARDE_MS);
      };
      relancerChien();
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
        relancerChien();
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
          relancerChien();
          for (const trame of analyseur.pousser(decodeur.decode(value, { stream: true }))) {
            if (trame.id !== null) this.dernierId = trame.id;
            fin = this.traiter(trame) || fin;
          }
        }
      } catch {
        if (generation !== this.generation) return;
      } finally {
        if (chien !== null) clearTimeout(chien);
        chien = null;
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
      const liste = empreinteSujets ? empreinteSujets.split(",") : [];
      const flux = fluxPartage();
      let actif = true;
      let enCours2 = false;
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
        if (actif && !enCours2 && visible2()) minuterie = setTimeout(lire, intervalleDeRelecture(flux.etat(), liste));
      };
      function lire() {
        arreter();
        if (!actif || !visible2()) return;
        if (enCours2) {
          aRelire = true;
          return;
        }
        enCours2 = true;
        lecteur.current().then(
          (valeur) => {
            if (actif) fixer({ valeur, erreur: null, luLe: Date.now() });
          },
          (erreur) => {
            if (actif) fixer((avant) => ({ ...avant, erreur: envelopper(erreur) }));
          }
        ).finally(() => {
          enCours2 = false;
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
      const desabonner = flux.abonner(liste, surSignal);
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
  function EtatActualisation(props = {}) {
    const etat = useEtatFlux();
    const portee = props.portee ?? "page";
    const actif = portee === "accueil" ? T.tempsReel.actifAccueil : portee === "discussions" ? T.tempsReel.actifDiscussions : T.tempsReel.actif;
    const texte = etat.mode === "temps_reel" ? actif : etat.mode === "sondage" ? T.tempsReel.repli : etat.mode === "indisponible" ? T.tempsReel.sansFlux : T.tempsReel.connexion;
    return /* @__PURE__ */ h(
      "p",
      {
        className: etat.mode === "sondage" ? "acp-alerte-texte" : "acp-discret",
        role: "status",
        "data-acp-temps-reel": etat.mode
      },
      /* @__PURE__ */ h("span", null, texte),
      portee === "accueil" ? /* @__PURE__ */ h("span", null, " ", T.tempsReel.noteAccueil) : null
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
  function nombre(valeur) {
    return typeof valeur === "number" && Number.isFinite(valeur) ? nombres.format(valeur) : null;
  }
  function court(valeur, longueur = 12) {
    if (typeof valeur !== "string" || !valeur) return null;
    const sans = valeur.includes(":") ? valeur.slice(valeur.indexOf(":") + 1) : valeur;
    return sans.slice(0, longueur);
  }

  // src/jsonrpc/canal.ts
  var METHODES_PERMISES = {
    "client.capabilities": ["server_requests"],
    "session.create": [],
    "session.resume": ["session_id"],
    "session.active_list": [],
    "prompt.submit": ["session_id", "text"],
    "session.interrupt": ["session_id"],
    ping: []
  };
  var CODE_NON_TRAITEE = -32601;
  var DELAI_OUVERTURE_MS = 1e4;
  var DELAI_APPEL_MS = 3e4;
  var INTERVALLE_PING_MS = 3e4;
  var ErreurCanal = class extends Error {
    constructor(genre, detail = "", code = null) {
      super(code === null ? genre : `${genre} ${code}`);
      __publicField(this, "genre");
      __publicField(this, "code");
      __publicField(this, "detail");
      this.name = "ErreurCanal";
      this.genre = genre;
      this.code = code;
      this.detail = detail.slice(0, 2e3);
    }
  };
  function verifierAppel(methode, params) {
    if (!Object.prototype.hasOwnProperty.call(METHODES_PERMISES, methode)) {
      throw new ErreurCanal("methode", methode);
    }
    const permis = METHODES_PERMISES[methode];
    const etrangers = Object.keys(params).filter((cle) => !permis.includes(cle));
    if (etrangers.length > 0) throw new ErreurCanal("parametre", `${methode} : ${etrangers.join(", ")}`);
  }
  function reponseClarifyValide(reponse) {
    if (!reponse || typeof reponse !== "object" || Array.isArray(reponse)) return false;
    const cles = Object.keys(reponse);
    if (cles.length !== 1) return false;
    const r = reponse;
    if (cles[0] === "answer") return typeof r.answer === "string";
    if (cles[0] !== "answers" || !r.answers || typeof r.answers !== "object" || Array.isArray(r.answers)) return false;
    return Object.values(r.answers).every((v) => typeof v === "string");
  }
  function texteErreur(erreur) {
    if (!erreur || typeof erreur !== "object") return { code: null, message: "" };
    const e = erreur;
    return {
      code: typeof e.code === "number" && Number.isInteger(e.code) ? e.code : null,
      message: typeof e.message === "string" ? e.message : ""
    };
  }
  var Canal = class {
    constructor(socket, options) {
      __publicField(this, "socket", socket);
      __publicField(this, "options", options);
      __publicField(this, "attentes", /* @__PURE__ */ new Map());
      /** Requêtes « clarify » du serveur encore ouvertes sur ce canal. */
      __publicField(this, "clarifyOuvertes", /* @__PURE__ */ new Set());
      __publicField(this, "compteur", 0);
      __publicField(this, "ferme", false);
      __publicField(this, "volontaire", false);
      /** Faux tant que l'ouverture n'a pas abouti : un échec d'ouverture n'est pas annoncé comme une fermeture. */
      __publicField(this, "actif", false);
      __publicField(this, "ping", null);
    }
    /** Une trame reçue (une ou plusieurs lignes JSON). */
    recevoir(donnees) {
      if (typeof donnees !== "string") return;
      for (const ligne of donnees.split("\n")) {
        if (!ligne.trim()) continue;
        let message;
        try {
          message = JSON.parse(ligne);
        } catch {
          continue;
        }
        if (message && typeof message === "object") this.traiter(message);
      }
    }
    traiter(message) {
      const methode = message.method;
      if (methode === "event") {
        const params = message.params && typeof message.params === "object" ? message.params : {};
        if (typeof params.type !== "string") return;
        this.options.surEvenement?.({
          type: params.type,
          sessionId: typeof params.session_id === "string" ? params.session_id : null,
          payload: params.payload
        });
        return;
      }
      if (typeof methode === "string") {
        const id2 = message.id;
        if (typeof id2 !== "string" && typeof id2 !== "number") return;
        const params = message.params && typeof message.params === "object" && !Array.isArray(message.params) ? message.params : {};
        if (methode === "clarify" && this.options.capacites && typeof id2 === "string" && this.options.surClarify) {
          this.clarifyOuvertes.add(id2);
          this.options.surClarify({ id: id2, methode, params });
          return;
        }
        this.envoyerBrut({ jsonrpc: "2.0", id: id2, error: { code: CODE_NON_TRAITEE, message: "M\xE9thode non trait\xE9e par ACP" } });
        this.options.surRefus?.(methode);
        return;
      }
      const id = message.id;
      if (typeof id !== "string") return;
      const attente = this.attentes.get(id);
      if (!attente) return;
      this.attentes.delete(id);
      clearTimeout(attente.minuterie);
      if ("error" in message) {
        const { code, message: texte } = texteErreur(message.error);
        attente.rejeter(new ErreurCanal("refus", texte, code));
      } else if ("result" in message) {
        if (attente.methode === "session.resume") this.adopterRequetesOuvertes(message.result);
        attente.resoudre(message.result);
      } else {
        attente.rejeter(new ErreurCanal("reponse"));
      }
    }
    /** Requêtes encore ouvertes rejouées par session.resume (open_requests) : une « clarify » devient répondable sur ce
     *  canal ; toute autre reçoit -32601, comme si elle venait d'arriver. */
    adopterRequetesOuvertes(resultat) {
      const ouvertes = resultat && typeof resultat === "object" ? resultat.open_requests : void 0;
      if (!Array.isArray(ouvertes)) return;
      for (const brut of ouvertes) {
        if (!brut || typeof brut !== "object") continue;
        const { id, method } = brut;
        if (typeof id !== "string" || typeof method !== "string") continue;
        if (method === "clarify" && this.options.capacites && this.options.surClarify) {
          this.clarifyOuvertes.add(id);
        } else {
          this.envoyerBrut({ jsonrpc: "2.0", id, error: { code: CODE_NON_TRAITEE, message: "M\xE9thode non trait\xE9e par ACP" } });
          this.options.surRefus?.(method);
        }
      }
    }
    envoyerBrut(objet) {
      if (this.ferme) return false;
      try {
        this.socket.send(`${JSON.stringify(objet)}
`);
        return true;
      } catch {
        return false;
      }
    }
    appeler(methode, params = {}, delaiMs) {
      try {
        verifierAppel(methode, params);
      } catch (erreur) {
        return Promise.reject(erreur);
      }
      if (this.ferme) return Promise.reject(new ErreurCanal("ferme"));
      this.compteur += 1;
      const id = `acp-${this.compteur}`;
      return new Promise((resoudre, rejeter) => {
        const minuterie = setTimeout(() => {
          this.attentes.delete(id);
          rejeter(new ErreurCanal("delai", methode));
        }, delaiMs ?? this.options.delaiAppelMs ?? DELAI_APPEL_MS);
        this.attentes.set(id, { methode, resoudre, rejeter, minuterie });
        if (!this.envoyerBrut({ jsonrpc: "2.0", id, method: methode, params })) {
          clearTimeout(minuterie);
          this.attentes.delete(id);
          rejeter(new ErreurCanal("ferme", methode));
        }
      });
    }
    repondreClarify(id, reponse) {
      if (!this.clarifyOuvertes.has(id)) throw new ErreurCanal("reponse", `requ\xEAte ${id} non ouverte sur ce canal`);
      if (!reponseClarifyValide(reponse)) throw new ErreurCanal("reponse", "forme de r\xE9ponse refus\xE9e");
      this.clarifyOuvertes.delete(id);
      if (!this.envoyerBrut({ jsonrpc: "2.0", id, result: reponse })) throw new ErreurCanal("ferme", "r\xE9ponse non envoy\xE9e");
    }
    refuserClarify(id) {
      if (!this.clarifyOuvertes.delete(id)) return;
      this.envoyerBrut({ jsonrpc: "2.0", id, error: { code: CODE_NON_TRAITEE, message: "M\xE9thode non trait\xE9e par ACP" } });
    }
    oublierClarify(id) {
      this.clarifyOuvertes.delete(id);
    }
    demarrerPing() {
      const intervalle = this.options.intervallePingMs ?? INTERVALLE_PING_MS;
      if (intervalle <= 0 || this.ping !== null) return;
      this.ping = setInterval(() => {
        this.appeler("ping", {}, Math.min(intervalle, 15e3)).catch((erreur) => {
          if (erreur instanceof ErreurCanal && erreur.genre === "delai") this.couper();
        });
      }, intervalle);
    }
    activer() {
      this.actif = true;
    }
    /** Fermeture constatée (socket fermé par le serveur ou le réseau). */
    surFermetureSocket() {
      if (this.ferme) return;
      this.ferme = true;
      this.liberer();
      if (this.actif) this.options.surFermeture?.(this.volontaire);
    }
    couper() {
      try {
        this.socket.close();
      } catch {
      }
      this.surFermetureSocket();
    }
    liberer() {
      if (this.ping !== null) clearInterval(this.ping);
      this.ping = null;
      for (const [, attente] of this.attentes) {
        clearTimeout(attente.minuterie);
        attente.rejeter(new ErreurCanal("ferme"));
      }
      this.attentes.clear();
      this.clarifyOuvertes.clear();
    }
    fermer() {
      this.volontaire = true;
      this.couper();
    }
  };
  async function ouvrirCanal(options = {}) {
    let construire;
    try {
      construire = sdk().buildWsUrl;
    } catch {
      construire = void 0;
    }
    if (typeof construire !== "function") throw new ErreurCanal("sdk");
    let url;
    try {
      url = await construire("/api/ws");
    } catch (erreur) {
      const statut = erreur && typeof erreur === "object" ? erreur.status : void 0;
      throw new ErreurCanal(
        "ticket",
        erreur instanceof Error ? erreur.message : String(erreur),
        typeof statut === "number" && Number.isInteger(statut) && statut > 0 ? statut : null
      );
    }
    const fabrique = options.fabrique ?? ((adresse) => new WebSocket(adresse));
    const canal = await new Promise((resoudre, rejeter) => {
      let pret = false;
      let socket;
      try {
        socket = fabrique(url);
      } catch (erreur) {
        rejeter(new ErreurCanal("connexion", erreur instanceof Error ? erreur.message : String(erreur)));
        return;
      }
      const instance = new Canal(socket, options);
      const echouer = (erreur) => {
        if (pret) return;
        pret = true;
        clearTimeout(minuterie);
        instance.fermer();
        rejeter(erreur);
      };
      const minuterie = setTimeout(
        () => echouer(new ErreurCanal("delai", "gateway.ready")),
        options.delaiOuvertureMs ?? DELAI_OUVERTURE_MS
      );
      socket.onerror = () => echouer(new ErreurCanal("connexion"));
      socket.onclose = () => {
        if (!pret) echouer(new ErreurCanal("ferme", "avant gateway.ready"));
        else instance.surFermetureSocket();
      };
      socket.onmessage = (evenement) => {
        if (!pret && typeof evenement.data === "string" && /"gateway\.ready"/.test(evenement.data)) {
          const lignes = evenement.data.split("\n").filter((l) => l.trim());
          const prete = lignes.some((l) => {
            try {
              const m = JSON.parse(l);
              return m.method === "event" && m.params?.type === "gateway.ready";
            } catch {
              return false;
            }
          });
          if (prete) {
            pret = true;
            clearTimeout(minuterie);
            resoudre(instance);
            return;
          }
        }
        instance.recevoir(evenement.data);
      };
    });
    if (options.capacites) {
      try {
        await canal.appeler("client.capabilities", { server_requests: true }, options.delaiOuvertureMs ?? DELAI_OUVERTURE_MS);
      } catch (erreur) {
        canal.fermer();
        throw erreur instanceof ErreurCanal ? erreur : new ErreurCanal("reponse");
      }
    }
    canal.activer();
    canal.demarrerPing();
    return canal;
  }

  // src/jsonrpc/discussions.ts
  var METHODE_LISTE = "session.active_list";
  var DELAI_LECTURE_MS = 5e3;
  var APERCU_MAX = 160;
  function chaine(valeur, max = 200) {
    return typeof valeur === "string" && valeur.trim() ? valeur.trim().slice(0, max) : null;
  }
  function sessionsEnAttente(resultat) {
    const sessions = resultat && typeof resultat === "object" ? resultat.sessions : void 0;
    if (!Array.isArray(sessions)) return null;
    const garde = [];
    for (const brut of sessions) {
      if (!brut || typeof brut !== "object") continue;
      const s = brut;
      const cle = chaine(s.session_key, 200);
      if (s.status !== "waiting" || !cle) continue;
      garde.push({
        cle,
        titre: chaine(s.title),
        apercu: chaine(s.preview, APERCU_MAX),
        derniereActivite: typeof s.last_active === "number" && Number.isFinite(s.last_active) ? s.last_active : null
      });
    }
    return garde;
  }
  var RAISONS = {
    sdk: "sdk",
    ticket: "ticket",
    connexion: "connexion",
    delai: "delai",
    ferme: "fermee"
  };
  async function lireDiscussionsEnAttente(delaiMs = DELAI_LECTURE_MS, fabrique = (url) => new WebSocket(url)) {
    let canal = null;
    let minuterie = null;
    const delai = new Promise((resoudre) => {
      minuterie = setTimeout(() => resoudre({ connu: false, raison: "delai" }), delaiMs);
    });
    const lecture = (async () => {
      try {
        canal = await ouvrirCanal({
          capacites: false,
          intervallePingMs: 0,
          fabrique,
          delaiOuvertureMs: delaiMs,
          delaiAppelMs: delaiMs
        });
        const sessions = sessionsEnAttente(await canal.appeler(METHODE_LISTE, {}));
        return sessions === null ? { connu: false, raison: "reponse" } : { connu: true, sessions };
      } catch (erreur) {
        const genre = erreur instanceof ErreurCanal ? erreur.genre : "reponse";
        return { connu: false, raison: RAISONS[genre] ?? "reponse" };
      }
    })();
    const resultat = await Promise.race([lecture, delai]);
    if (minuterie !== null) clearTimeout(minuterie);
    void lecture.then(() => canal?.fermer());
    canal?.fermer();
    return resultat;
  }

  // src/types.ts
  function chaine2(valeur) {
    return typeof valeur === "string" && valeur.trim() ? valeur : null;
  }
  function listeDeChaines(valeur) {
    return Array.isArray(valeur) ? valeur.filter((v) => typeof v === "string" && v.trim() !== "") : [];
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
  var pauseGenerale = (generale) => ecrireJSON(ROUTE_PAUSE, { generale });
  var notificationDeTest = () => ecrireJSON(ROUTE_NOTIFICATION_TEST, {});

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
          case "a_decider":
            return L(e.aDecider, "degrade");
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
  function libelleCanal(canal) {
    if (canal === "aucune") return T.projets.canalAucun;
    if (canal === "telegram") return T.projets.canalTelegram;
    if (canal === "ntfy") return T.projets.canalNtfy;
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
    const enCours2 = useRef(false);
    const envoyer = async (travail) => {
      if (enCours2.current) return null;
      enCours2.current = true;
      fixer({ etat: "envoi" });
      try {
        const resultat = await travail();
        fixer({ etat: "ok", resultat });
        return resultat;
      } catch (erreur) {
        fixer({ etat: "erreur", erreur: envelopper(erreur) });
        return null;
      } finally {
        enCours2.current = false;
      }
    };
    return { etat, envoyer, oublier: () => fixer({ etat: "repos" }) };
  }

  // src/projets/BandeauPause.tsx
  var RAISON_PAUSE_CROCHETS = "ACP : crochets shell d\xE9tect\xE9s en cours de route";
  function BandeauPause(props) {
    const envoi = useEnvoi();
    const crochets = props.pause.reason === RAISON_PAUSE_CROCHETS;
    const reprendre = async () => {
      if (await envoi.envoyer(() => pauseGenerale(false)) !== null) props.apres();
    };
    return /* @__PURE__ */ h("section", { className: "acp-banniere acp-banniere--pause", "aria-labelledby": "acp-pause-titre", "data-acp-pause": "" }, /* @__PURE__ */ h("h2", { className: "acp-banniere__titre", id: "acp-pause-titre" }, T.projets.pauseEnCours), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.pauseEffet), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, T.projets.raison), /* @__PURE__ */ h("dd", null, /* @__PURE__ */ h(Donnee, { valeur: chaine2(props.pause.reason) }))), /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, T.projets.depuisLe), /* @__PURE__ */ h("dd", null, /* @__PURE__ */ h(Horodatage, { valeur: props.pause.engaged_at })))), crochets ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "note" }, T.projets.pauseCrochets) : /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.projets.reprendreHermes, principal: true, surClic: reprendre, desactive: envoi.etat.etat === "envoi" })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }));
  }

  // src/projets/Notifications.tsx
  function Notifications(props) {
    const etat = props.etat ?? null;
    const envoi = useEnvoi();
    const configure = etat?.configure === true;
    const canal = etat?.connu ? etat.canal : null;
    const libelle = libelleCanal(canal);
    const message = envoi.etat.etat === "ok" ? chaine2(envoi.etat.resultat?.message) : null;
    return /* @__PURE__ */ h(Carte, { titre: T.projets.notificationsTitre, id: "acp-projets-notifications" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.canal }, libelle ? /* @__PURE__ */ h("span", null, libelle) : /* @__PURE__ */ h(Donnee, { valeur: chaine2(canal), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.etatNotifications }, /* @__PURE__ */ h(
      Etiquette,
      {
        libelle: etat?.connu !== true ? null : configure ? { texte: T.projets.notificationsActives, famille: "succes" } : { texte: T.projets.notificationsInactives, famille: "neutre" }
      }
    ))), configure ? null : /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-notifications-note" }, etat?.connu === true ? T.projets.notificationsNonConfigurees : T.projets.notificationsEtatInconnu), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
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

  // src/interface/accueil-api.ts
  var ROUTE_ACCUEIL = "/api/plugins/acp-poste/v1/accueil";
  var ROUTE_CRON = "/api/cron/jobs";
  var SCRIPT_BILAN = "acp-bilan.py";
  var TACHE_BILAN = {
    name: "Bilan ACP",
    schedule: "0 8 * * *",
    prompt: "",
    no_agent: true,
    script: SCRIPT_BILAN,
    deliver: "local"
  };
  var lireAccueil = () => lireJSON(ROUTE_ACCUEIL);
  async function lireTachesCron() {
    const brut = await lireJSON(ROUTE_CRON);
    const liste = Array.isArray(brut) ? brut : brut?.jobs;
    return Array.isArray(liste) ? liste.filter((t) => t && typeof t === "object") : [];
  }
  function tachesDuBilan(taches) {
    return taches.filter((t) => t.script === SCRIPT_BILAN && t.no_agent === true);
  }
  var creerBilanQuotidien = () => ecrireJSON(ROUTE_CRON, TACHE_BILAN);

  // src/interface/CarteATraiter.tsx
  var CIBLE = /^\/projets\?vue=questions(&(q|carte)=[A-Za-z0-9_\-/%]+)?$/;
  function libelleGenre(genre) {
    switch (genre) {
      case "question":
        return T.accueil.genreQuestion;
      case "decision":
        return T.accueil.genreDecision;
      case "revue":
        return T.accueil.genreRevue;
      case "arretee":
        return T.accueil.genreArretee;
      default:
        return null;
    }
  }
  function CarteATraiter(props) {
    const bloc = props.aTraiter ?? null;
    const connues = props.discussions !== null && props.discussions.connu;
    const nbDiscussions = connues && props.discussions?.connu ? props.discussions.sessions.length : null;
    const total = bloc && typeof bloc.total === "number" ? bloc.total + (nbDiscussions ?? 0) : null;
    const premieres = Array.isArray(bloc?.premieres) ? bloc.premieres : [];
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.aTraiterTitre, id: "acp-accueil-a-traiter" }, bloc === null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, /* @__PURE__ */ h("span", null, T.accueil.blocIllisible), " ", /* @__PURE__ */ h(Donnee, { valeur: props.illisible })) : /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h("p", { className: "acp-chiffre" }, /* @__PURE__ */ h(Donnee, { valeur: total }), nbDiscussions === null ? /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.projets.discussionsNonComptees) : null), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.questions }, /* @__PURE__ */ h(Donnee, { valeur: bloc.questions ?? null })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.decisions }, /* @__PURE__ */ h(Donnee, { valeur: bloc.decisions ?? null })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.revues }, /* @__PURE__ */ h(Donnee, { valeur: bloc.revues ?? null })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.arretees }, /* @__PURE__ */ h(Donnee, { valeur: bloc.arretees ?? null })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.discussionsEnAttente }, nbDiscussions === null ? /* @__PURE__ */ h("span", null, T.accueil.inconnues) : /* @__PURE__ */ h(Donnee, { valeur: nbDiscussions })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.chezHermes }, /* @__PURE__ */ h(Donnee, { valeur: typeof props.chezHermes === "number" ? props.chezHermes : null }))), premieres.length > 0 ? /* @__PURE__ */ h("ul", { className: "acp-noms" }, premieres.map((d, rang) => {
      const cible = chaine2(d.cible);
      const genre = libelleGenre(d.genre);
      return /* @__PURE__ */ h("li", { key: `${cible ?? rang}` }, genre ? /* @__PURE__ */ h("span", { className: "acp-discret" }, genre, " ") : null, cible && CIBLE.test(cible) ? /* @__PURE__ */ h(Lien, { vers: cible }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(d.titre) })) : /* @__PURE__ */ h(Donnee, { valeur: chaine2(d.titre) }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(d.projet_titre) })));
    })) : total === 0 && nbDiscussions !== null ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.rienATraiter) : null), /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/projets?vue=questions" }, T.accueil.ouvrirQuestions)));
  }

  // src/interface/CarteBilan.tsx
  function bilanEnPause(tache) {
    return tache.enabled === false || tache.state === "paused";
  }
  function bilanEnErreur(tache) {
    return !bilanEnPause(tache) && tache.state === "error";
  }
  function derniereEnEchec(tache) {
    return Boolean(tache.last_run_at) && typeof tache.last_status === "string" && tache.last_status !== "ok";
  }
  function CarteBilan(props) {
    const lecture = useDonnees(lireTachesCron, props.jeton, []);
    const creation = useEnvoi();
    const taches = lecture.valeur === null ? null : tachesDuBilan(lecture.valeur);
    const tache = taches && taches.length > 0 ? taches[0] : null;
    const creer = async () => {
      if (await creation.envoyer(creerBilanQuotidien) !== null) props.apres();
    };
    const notif = props.notifications ?? null;
    let contenu;
    if (taches === null) {
      contenu = lecture.erreur ? /* @__PURE__ */ h(BlocErreur, { erreur: lecture.erreur, message: T.accueil.bilanIllisible }) : /* @__PURE__ */ h(EnChargement, null);
    } else if (tache === null) {
      contenu = /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: { texte: T.accueil.bilanNonCree, famille: "neutre" } })), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.bilanExplication), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
        Bouton,
        {
          libelle: T.accueil.creerBilan,
          principal: true,
          surClic: () => void creer(),
          desactive: creation.etat.etat === "envoi"
        }
      )), creation.etat.etat === "erreur" ? /* @__PURE__ */ h(BlocErreur, { erreur: creation.etat.erreur, message: T.accueil.bilanCreationRefusee }) : /* @__PURE__ */ h(RetourEnvoi, { etat: creation.etat }));
    } else {
      const pause = bilanEnPause(tache);
      const erreur = bilanEnErreur(tache);
      const echec = derniereEnEchec(tache);
      const detail = chaine2(tache.last_error);
      contenu = /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.etat }, /* @__PURE__ */ h(Etiquette, { libelle: pause ? { texte: T.accueil.bilanEnPause, famille: "neutre" } : erreur ? { texte: T.accueil.bilanEnErreur, famille: "echec" } : { texte: T.accueil.bilanActif, famille: "succes" } })), pause || erreur ? null : /* @__PURE__ */ h(Ligne, { libelle: T.accueil.prochainEnvoi }, /* @__PURE__ */ h(Horodatage, { valeur: chaine2(tache.next_run_at) })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.dernierEnvoi }, tache.last_run_at ? /* @__PURE__ */ h(Horodatage, { valeur: chaine2(tache.last_run_at) }) : /* @__PURE__ */ h("span", null, T.accueil.jamais))), erreur ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.accueil.bilanTacheEnErreur) : echec ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.accueil.bilanDerniereEchec) : null, (erreur || echec) && (detail || tache.last_status) ? /* @__PURE__ */ h("details", { className: "acp-details" }, /* @__PURE__ */ h("summary", null, T.commun.detailTechnique), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.bilanStatut }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(tache.last_status), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.bilanErreurHermes }, /* @__PURE__ */ h(Donnee, { valeur: detail, mono: true })))) : null, taches.length > 1 ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.accueil.bilanPlusieurs) : null, creation.etat.etat === "ok" ? /* @__PURE__ */ h("p", { className: "acp-succes", role: "status" }, T.accueil.bilanCree) : null);
    }
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.bilanTitre, id: "acp-accueil-bilan" }, contenu, notif?.connu === true && notif.configure !== true ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.accueil.bilanSansCanal) : null, /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/cron" }, T.accueil.ouvrirCron)));
  }

  // src/poste/libelles.ts
  var L2 = (texte, famille) => ({ texte, famille });
  function libelleEtatDuPoste(etat) {
    const e = T.poste.etats;
    switch (etat) {
      case "non_configure":
        return L2(e.nonConfigure, "neutre");
      case "a_confirmer":
        return L2(e.aConfirmer, "degrade");
      case "en_ligne":
        return L2(e.enLigne, "succes");
      case "hors_ligne":
        return L2(e.horsLigne, "neutre");
      case "redeploiement":
        return L2(e.redeploiement, "degrade");
      case "revoque":
        return L2(e.revoque, "echec");
      default:
        return null;
    }
  }
  function libelleEtatQuotas(etat) {
    const e = T.poste.etatsQuotas;
    switch (etat) {
      case "releve":
        return L2(e.releve, "succes");
      case "perime":
        return L2(e.perime, "degrade");
      case "inconnu":
        return L2(e.inconnu, "neutre");
      default:
        return null;
    }
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
  function libelleVoie(voie) {
    const v = T.projets.voies;
    return voie === "hermes" ? v.hermes : voie === "poste-codex" ? v.posteCodex : voie === "poste-claude" ? v.posteClaude : null;
  }

  // src/interface/CarteExecutant.tsx
  function Illisible(props) {
    return /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, /* @__PURE__ */ h("span", null, T.accueil.blocIllisible), " ", /* @__PURE__ */ h(Donnee, { valeur: props.raison }));
  }
  function CarteExecutant(props) {
    const e = props.executant ?? null;
    const fermees = e?.voies_fermees && typeof e.voies_fermees === "object" ? Object.entries(e.voies_fermees) : [];
    const enCours2 = e?.carte_en_cours ?? null;
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.executantTitre, id: "acp-accueil-executant" }, e === null ? /* @__PURE__ */ h(Illisible, { raison: props.illisible }) : /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.etat }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatDuPoste(e.etat), brut: e.etat })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.machine }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(e.nom) })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.plateforme }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(e.plateforme), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.derniereVue }, /* @__PURE__ */ h(Horodatage, { valeur: e.derniere_vue, relative: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.carteEnCours }, enCours2 ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: chaine2(enCours2.titre) }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(enCours2.projet_titre) })), " ", /* @__PURE__ */ h(Etiquette, { libelle: libelleStatut(enCours2.statut), brut: enCours2.statut })) : /* @__PURE__ */ h("span", null, T.accueil.aucuneCarteEnCours))), chaine2(e.message) ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(e.message) })) : null, fermees.length > 0 ? /* @__PURE__ */ h("div", null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.voiesFermees), /* @__PURE__ */ h("ul", { className: "acp-noms" }, fermees.map(([voie, raison]) => /* @__PURE__ */ h("li", { key: voie }, libelleVoie(voie) ? /* @__PURE__ */ h("span", null, libelleVoie(voie)) : /* @__PURE__ */ h(Donnee, { valeur: voie, mono: true }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: typeof raison === "string" ? raison : null })))))) : null), /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/poste" }, T.accueil.ouvrirPoste)));
  }
  var VOIES_QUOTAS = ["poste-codex", "poste-claude"];
  function pourcentage(valeur) {
    return typeof valeur === "number" && Number.isFinite(valeur) && valeur >= 0 && valeur <= 100 ? `${valeur} %` : null;
  }
  function CarteQuotas(props) {
    const quotas = props.quotas ?? null;
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.quotasTitre, id: "acp-accueil-quotas" }, quotas === null ? /* @__PURE__ */ h(Illisible, { raison: props.illisible }) : /* @__PURE__ */ h("div", { className: "acp-sections" }, VOIES_QUOTAS.map((voie) => {
      const q = quotas[voie] ?? {};
      return /* @__PURE__ */ h("div", { key: voie, className: "acp-groupe" }, /* @__PURE__ */ h("h3", { className: "acp-sous-titre" }, libelleVoie(voie)), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.etat }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatQuotas(q.etat), brut: q.etat })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.utilise }, /* @__PURE__ */ h(Donnee, { valeur: pourcentage(q.resume?.pourcentage_utilise) })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.remiseAZero }, /* @__PURE__ */ h(Horodatage, { valeur: q.resume?.remise_a_zero })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.source }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(q.source_libelle) })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.releveLe }, /* @__PURE__ */ h(Horodatage, { valeur: q.releve_le }))));
    }), /* @__PURE__ */ h("div", { className: "acp-groupe" }, /* @__PURE__ */ h("h3", { className: "acp-sous-titre" }, T.accueil.quotasHermes), /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: chaine2(quotas.hermes?.libelle) })))), /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/poste?vue=quotas" }, T.accueil.ouvrirQuotas)));
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
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.hermes, id: "acp-accueil-hermes" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.version }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(hermes?.version), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.versionTestee }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(hermes?.version_testee), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.conformite }, /* @__PURE__ */ h(Pastille, { etat: etatConformite(hermes?.conforme) })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.image }, /* @__PURE__ */ h(Donnee, { valeur: court(image?.condensat_index), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.commit }, /* @__PURE__ */ h(Donnee, { valeur: court(deploiement?.commit), mono: true }))));
  }
  function CarteGarde(props) {
    const garde = props.meta.garde_execution;
    const presente = garde?.presente_dans_le_gestionnaire;
    const admis = Array.isArray(garde?.outils_admis) ? garde.outils_admis.length : null;
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.garde, id: "acp-accueil-garde" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.gardeEtat }, presente === true ? /* @__PURE__ */ h(Pastille, { etat: "active" }) : presente === false ? /* @__PURE__ */ h(Pastille, { etat: "absente" }) : /* @__PURE__ */ h(Pastille, { etat: "inconnu" })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.outilsAdmis }, /* @__PURE__ */ h(Donnee, { valeur: nombre(admis) }))), chaine2(garde?.alerte) ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(garde?.alerte) })) : null);
  }
  function CartePersona(props) {
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.persona, id: "acp-accueil-persona" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.personaEtat }, /* @__PURE__ */ h(Pastille, { etat: etatPersona(props.meta) }))));
  }
  function CarteCatalogue(props) {
    const resume = props.meta.catalogue ?? null;
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.catalogue, id: "acp-accueil-catalogue" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.skillsAcp }, /* @__PURE__ */ h(Donnee, { valeur: nombre(resume?.skills_actives) }), /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.commun.separateur, " "), /* @__PURE__ */ h(Donnee, { valeur: nombre(resume?.skills_attendues) }), /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.accueil.skillsAttendues)), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.context7 }, /* @__PURE__ */ h(Pastille, { etat: etatContext7(resume?.context7) }))), /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/catalogue" }, T.accueil.ouvrirCatalogue)));
  }
  function Horodatage2(props) {
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
      contenu = sessions.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.aucuneSession) : /* @__PURE__ */ h("ul", { className: "acp-sessions" }, sessions.map((session, rang) => /* @__PURE__ */ h("li", { key: session.id ?? String(rang), className: "acp-session" }, /* @__PURE__ */ h("span", { className: "acp-session__titre" }, chaine2(session.title) ? /* @__PURE__ */ h(Donnee, { valeur: chaine2(session.title) }) : /* @__PURE__ */ h("span", null, T.accueil.sansTitre)), /* @__PURE__ */ h("span", { className: "acp-session__meta" }, /* @__PURE__ */ h(Horodatage2, { valeur: session.last_active }), /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.commun.separateur, " "), /* @__PURE__ */ h(Donnee, { valeur: nombre(session.message_count) }), /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.accueil.messages)))));
    }
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.sessions, id: "acp-accueil-sessions" }, contenu, /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/sessions" }, T.accueil.toutesSessions)));
  }
  function CarteProjets(props) {
    const bloc = props.bloc ?? null;
    const liste = Array.isArray(bloc?.liste) ? bloc.liste : [];
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.projetsTitre, id: "acp-accueil-projets" }, bloc === null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, /* @__PURE__ */ h("span", null, T.accueil.blocIllisible), " ", /* @__PURE__ */ h(Donnee, { valeur: props.illisible })) : /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.accueil.projetsEnCours }, /* @__PURE__ */ h(Donnee, { valeur: nombre(bloc.en_cours) })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.projetsEnPause }, /* @__PURE__ */ h(Donnee, { valeur: nombre(bloc.en_pause) })), /* @__PURE__ */ h(Ligne, { libelle: T.accueil.projetsTermines7j }, /* @__PURE__ */ h(Donnee, { valeur: nombre(bloc.termines_7j) }))), liste.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.aucunProjetOuvert) : /* @__PURE__ */ h("ul", { className: "acp-noms" }, liste.map((p, rang) => {
      const id = chaine2(p.id);
      return /* @__PURE__ */ h("li", { key: id ?? String(rang), className: "acp-projet-court" }, /* @__PURE__ */ h("p", { className: "acp-etat" }, id ? /* @__PURE__ */ h(Lien, { vers: `/projets?projet=${encodeURIComponent(id)}` }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(p.titre) })) : /* @__PURE__ */ h(Donnee, { valeur: chaine2(p.titre) }), " ", /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatProjet(p.etat, p.etat_derive), brut: p.etat })), /* @__PURE__ */ h(Avancement, { faites: p.faites, total: p.total }), chaine2(p.derniere_note) ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(p.derniere_note) })) : null);
    }))), /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Lien, { vers: "/projets" }, T.accueil.ouvrirProjets)));
  }
  function CarteRaccourcis() {
    return /* @__PURE__ */ h(Carte, { titre: T.accueil.raccourcis, id: "acp-accueil-raccourcis" }, /* @__PURE__ */ h("ul", { className: "acp-raccourcis" }, /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/projets" }, T.accueil.lienProjets)), /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/discussion" }, T.accueil.discussion)), /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/sessions" }, T.accueil.lienSessions)), /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/kanban" }, T.accueil.kanban)), /* @__PURE__ */ h("li", null, /* @__PURE__ */ h(Lien, { vers: "/catalogue" }, T.accueil.lienCatalogue))));
  }
  function Pied(props) {
    return /* @__PURE__ */ h("div", { className: "acp-pied" }, /* @__PURE__ */ h("span", null, T.accueil.piedAcp), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine2(props.meta?.greffon?.version), mono: true }), " ", /* @__PURE__ */ h("span", null, T.commun.separateur), " ", /* @__PURE__ */ h("span", null, T.accueil.piedPropulse), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine2(props.meta?.hermes?.version), mono: true }), " ", /* @__PURE__ */ h("span", null, T.accueil.piedLicence));
  }
  function Accueil() {
    const meta = useChargement(() => lireMeta());
    const [jeton, fixerJeton] = useState(0);
    const apres = () => fixerJeton((j) => j + 1);
    const lecture = useDonnees(lireAccueil, jeton, SUJETS);
    const discussions = useDonnees(lireDiscussionsEnAttente, jeton, ["discussions"]);
    const accueil = lecture.valeur;
    const illisibles = accueil?.illisibles ?? {};
    const raison = (bloc) => typeof illisibles[bloc] === "string" ? illisibles[bloc] : null;
    const pause = accueil?.pause_generale && typeof accueil.pause_generale === "object" ? accueil.pause_generale : null;
    return /* @__PURE__ */ h("div", { className: "acp-page", "data-acp-racine": "accueil" }, /* @__PURE__ */ h("div", { className: "acp-entete" }, /* @__PURE__ */ h("h1", { className: "acp-titre" }, T.accueil.titre), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.accueil.intro)), pause ? /* @__PURE__ */ h(BandeauPause, { pause, apres }) : null, accueil === null && lecture.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : null, accueil === null && lecture.erreur !== null ? /* @__PURE__ */ h(BlocErreur, { erreur: lecture.erreur, message: T.accueil.accueilIndisponible }) : null, accueil !== null && lecture.erreur !== null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.accueil.actualisationImpossible) : null, /* @__PURE__ */ h("div", { className: "acp-grille acp-grille--accueil" }, accueil !== null ? /* @__PURE__ */ h(
      CarteATraiter,
      {
        aTraiter: accueil.a_traiter,
        chezHermes: accueil.chez_hermes,
        discussions: discussions.valeur,
        illisible: raison("a_traiter")
      }
    ) : null, accueil !== null ? /* @__PURE__ */ h(CarteProjets, { bloc: accueil.projets, illisible: raison("projets") }) : null, accueil !== null ? /* @__PURE__ */ h(CarteExecutant, { executant: accueil.executant, illisible: raison("executant") }) : null, accueil !== null ? /* @__PURE__ */ h(CarteQuotas, { quotas: accueil.quotas, illisible: raison("quotas") }) : null, accueil !== null ? /* @__PURE__ */ h(Notifications, { etat: accueil.notifications }) : null, accueil !== null ? /* @__PURE__ */ h(CarteBilan, { notifications: accueil.notifications, jeton, apres }) : null, /* @__PURE__ */ h(CarteSessions, null), meta.etat === "ok" ? /* @__PURE__ */ h(CarteHermes, { meta: meta.valeur }) : null, meta.etat === "ok" ? /* @__PURE__ */ h(CarteGarde, { meta: meta.valeur }) : null, meta.etat === "ok" ? /* @__PURE__ */ h(CartePersona, { meta: meta.valeur }) : null, meta.etat === "ok" ? /* @__PURE__ */ h(CarteCatalogue, { meta: meta.valeur }) : null, /* @__PURE__ */ h(CarteRaccourcis, null)), meta.etat === "chargement" ? /* @__PURE__ */ h(EnChargement, null) : null, meta.etat === "erreur" ? /* @__PURE__ */ h(BlocErreur, { erreur: meta.erreur, message: T.accueil.metaIndisponible }) : null, /* @__PURE__ */ h(EtatActualisation, { portee: "accueil" }), /* @__PURE__ */ h(Pied, { meta: meta.etat === "ok" ? meta.valeur : null }));
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
