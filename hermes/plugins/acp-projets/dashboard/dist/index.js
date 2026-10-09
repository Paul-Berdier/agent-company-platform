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
  function Fragment(props) {
    return props.children ?? null;
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
        if (actif && !enCours && visible2()) minuterie = setTimeout(lire, intervalleDeRelecture(flux.etat(), liste));
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
  var routeConclureTriage = (tableau, carte) => `${RACINE_POSTE}/triage/${segment(tableau)}/${segment(carte)}/conclure`;
  var routeCarteDuProjet = (id, carte) => `${routeProjet(id)}/cartes/${segment(carte)}`;
  var routeAccepterRevue = (tableau, carte) => `${RACINE_POSTE}/revues/${segment(tableau)}/${segment(carte)}/accepter`;
  var routeRefuserRevue = (tableau, carte) => `${RACINE_POSTE}/revues/${segment(tableau)}/${segment(carte)}/refuser`;
  var routeRelancerCarte = (tableau, carte) => `${RACINE_POSTE}/cartes/${segment(tableau)}/${segment(carte)}/relancer`;
  var routeReponsesProjet = (id) => `${routeProjet(id)}/reponses`;
  var routeClore = (id) => `${routeProjet(id)}/clore`;
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
  var lireCarte = (id, carte) => lireJSON(routeCarteDuProjet(id, carte));
  var lancerProjet = (demande, cle) => ecrireJSON(ROUTE_PROJETS, demande, { "Idempotency-Key": cle });
  var pauseProjet = (id) => ecrireJSON(routePauseProjet(id), {});
  var repriseProjet = (id) => ecrireJSON(routeRepriseProjet(id), {});
  var repondreQuestion = (question, reponse) => ecrireJSON(routeReponse(question), { reponse });
  var reprendreTriage = (tableau, carte, consigne) => ecrireJSON(routeReprendreTriage(tableau, carte), consigne ? { consigne } : {});
  var conclureTriage = (tableau, carte) => ecrireJSON(routeConclureTriage(tableau, carte), {});
  var pauseGenerale = (generale) => ecrireJSON(ROUTE_PAUSE, { generale });
  var notificationDeTest = () => ecrireJSON(ROUTE_NOTIFICATION_TEST, {});
  var accepterRevue = (tableau, carte) => ecrireJSON(routeAccepterRevue(tableau, carte), {});
  var refuserRevue = (tableau, carte, motif) => ecrireJSON(routeRefuserRevue(tableau, carte), { motif });
  var relancerCarte = (tableau, carte, consigne) => ecrireJSON(routeRelancerCarte(tableau, carte), { consigne });
  var changerReponses = (id, reponses) => ecrireJSON(routeReponsesProjet(id), { reponses });
  var clore = (id) => ecrireJSON(routeClore(id), { confirmation: true });

  // src/types.ts
  function chaine2(valeur) {
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
  function libelleEtatQuestion(etat, chez) {
    const q = T.projets.etatsQuestion;
    if (etat === "ouverte" && chez === "proprietaire") return L(q.escaladee, "degrade");
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
    if (reponses === "proprietaire") return T.projets.reponsesVous;
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
  function libellePalier(palier) {
    return palier === "default" ? T.projets.palierStandard : null;
  }
  function libelleActionJournal(action) {
    const table = T.projets.actionsJournal;
    return typeof action === "string" && Object.hasOwn(table, action) ? table[action] ?? null : null;
  }
  function libelleActeurJournal(acteur) {
    const a = T.projets.acteursJournal;
    if (typeof acteur !== "string") return { libelle: null, donnee: null };
    if (acteur.startsWith("proprietaire:")) return { libelle: a.vous, donnee: null };
    if (acteur === "acp-poste" || acteur.startsWith("acp-poste:")) return { libelle: a.acp, donnee: null };
    if (acteur === "poste") return { libelle: a.poste, donnee: null };
    if (acteur.startsWith("discussion:")) return { libelle: a.discussion, donnee: null };
    if (acteur.startsWith("carte:")) return { libelle: a.carte, donnee: acteur.slice("carte:".length) || null };
    return { libelle: null, donnee: acteur };
  }

  // src/projets/vue.ts
  var CHEMIN_PAGE = "/projets";
  var IDENTIFIANT = /^[A-Za-z0-9_-]{1,80}$/;
  var CIBLE_CARTE = /^[A-Za-z0-9_-]{1,80}\/[A-Za-z0-9_-]{1,80}$/;
  function vueDepuisAdresse(recherche) {
    const parametres = new URLSearchParams(recherche);
    const projet = parametres.get("projet");
    if (projet && IDENTIFIANT.test(projet)) return { genre: "detail", id: projet };
    const vue = parametres.get("vue");
    if (vue === "questions") {
      const q = parametres.get("q");
      const carte = parametres.get("carte");
      if (q && IDENTIFIANT.test(q)) return { genre: "questions", q };
      if (carte && CIBLE_CARTE.test(carte)) return { genre: "questions", carte };
      return { genre: "questions" };
    }
    if (vue === "nouveau") return { genre: "nouveau" };
    return { genre: "liste" };
  }
  function rechercheDeVue(vue, recherche = "") {
    const parametres = new URLSearchParams(recherche);
    for (const cle of ["projet", "vue", "q", "carte"]) parametres.delete(cle);
    if (vue.genre === "detail") parametres.set("projet", vue.id);
    else if (vue.genre !== "liste") parametres.set("vue", vue.genre);
    if (vue.genre === "questions" && vue.q) parametres.set("q", vue.q);
    if (vue.genre === "questions" && vue.carte) parametres.set("carte", vue.carte);
    const texte = parametres.toString().replace(/%2F/g, "/");
    return texte ? `?${texte}` : "";
  }
  function pousserAdresse(vue) {
    try {
      const { pathname, search } = window.location;
      const suivante = `${pathname}${rechercheDeVue(vue, search)}`;
      if (suivante !== `${pathname}${search}`) window.history.pushState(window.history.state, "", suivante);
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
  var RAISON_PAUSE_CROCHETS = "ACP : crochets shell d\xE9tect\xE9s en cours de route";
  function BandeauPause(props) {
    const envoi = useEnvoi();
    const crochets = props.pause.reason === RAISON_PAUSE_CROCHETS;
    const reprendre = async () => {
      if (await envoi.envoyer(() => pauseGenerale(false)) !== null) props.apres();
    };
    return /* @__PURE__ */ h("section", { className: "acp-banniere acp-banniere--pause", "aria-labelledby": "acp-pause-titre", "data-acp-pause": "" }, /* @__PURE__ */ h("h2", { className: "acp-banniere__titre", id: "acp-pause-titre" }, T.projets.pauseEnCours), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.pauseEffet), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, T.projets.raison), /* @__PURE__ */ h("dd", null, /* @__PURE__ */ h(Donnee, { valeur: chaine2(props.pause.reason) }))), /* @__PURE__ */ h("div", { className: "acp-ligne" }, /* @__PURE__ */ h("dt", null, T.projets.depuisLe), /* @__PURE__ */ h("dd", null, /* @__PURE__ */ h(Horodatage, { valeur: props.pause.engaged_at })))), crochets ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "note" }, T.projets.pauseCrochets) : /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.projets.reprendreHermes, principal: true, surClic: reprendre, desactive: envoi.etat.etat === "envoi" })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }));
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
  function DerniereNote(props) {
    const note = chaine2(props.projet.derniere_note);
    if (note && props.projet.derniere_note_tronquee === true) {
      return /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: note }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.noteTronquee));
    }
    if (note) return /* @__PURE__ */ h(Donnee, { valeur: note });
    if (entier(props.projet.compteurs?.faites) === 0) return /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.aucuneNote);
    return /* @__PURE__ */ h(Donnee, { valeur: null });
  }
  function CarteDeProjet(props) {
    const { projet } = props;
    const id = chaine2(projet.id);
    const compteurs = projet.compteurs ?? {};
    const questions = entier(projet.questions_ouvertes);
    return /* @__PURE__ */ h("li", { className: "acp-entree acp-projet" }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, id ? /* @__PURE__ */ h(LienVue, { vue: { genre: "detail", id }, naviguer: props.naviguer, className: "acp-lien acp-lien--titre" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(projet.titre) })) : /* @__PURE__ */ h(Donnee, { valeur: chaine2(projet.titre) })), /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatProjet(projet.etat, projet.etat_derive), brut: projet.etat }), questions !== null && questions > 0 ? /* @__PURE__ */ h("span", { className: "acp-pastille acp-pastille--degrade" }, /* @__PURE__ */ h("span", null, T.projets.questionsEnAttente), " ", /* @__PURE__ */ h(Donnee, { valeur: questions })) : null), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.cartesFaites }, /* @__PURE__ */ h(Avancement, { faites: compteurs.faites, total: compteurs.total })), entier(compteurs.en_attente_du_poste) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.enAttenteDuPoste }, /* @__PURE__ */ h(Donnee, { valeur: nombre(compteurs.en_attente_du_poste) })) : null, entier(compteurs.bloquees) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.bloquees }, /* @__PURE__ */ h(Donnee, { valeur: nombre(compteurs.bloquees) })) : null, entier(compteurs.triage) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.enTriage }, /* @__PURE__ */ h(Donnee, { valeur: nombre(compteurs.triage) })) : null, /* @__PURE__ */ h(Ligne, { libelle: T.projets.poste }, /* @__PURE__ */ h(EtatDuPoste, { poste: props.poste })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.derniereNote }, /* @__PURE__ */ h(DerniereNote, { projet })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.creeLe }, /* @__PURE__ */ h(Horodatage, { valeur: projet.cree_le, relative: true }))));
  }
  function titreDeLaMachine(poste) {
    const hote = poste?.poste?.hote;
    if (hote === "railway") return T.projets.posteTitreExecutant;
    if (hote === "pc") return T.projets.posteTitre;
    return T.projets.posteTitreNeutre;
  }
  function CartePoste(props) {
    const poste = props.poste;
    return /* @__PURE__ */ h(Carte, { titre: titreDeLaMachine(poste), id: "acp-projets-poste" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.etat }, /* @__PURE__ */ h(EtatDuPoste, { poste })), chaine2(poste?.machine) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.machine }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(poste?.machine), mono: true })) : null, poste?.derniere_vue ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.derniereVue }, /* @__PURE__ */ h(Horodatage, { valeur: poste.derniere_vue })) : null, /* @__PURE__ */ h(Ligne, { libelle: T.projets.cartesEnAttente }, /* @__PURE__ */ h(Donnee, { valeur: nombre(poste?.cartes_en_attente) }))), chaine2(poste?.message) ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(poste?.message) })) : null);
  }
  function ListeProjets(props) {
    const { donnees } = props;
    const projets = Array.isArray(donnees.projets) ? donnees.projets : [];
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h(Carte, { titre: T.projets.vosProjets, id: "acp-projets-liste" }, /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(LienVue, { vue: { genre: "nouveau" }, naviguer: props.naviguer, className: "acp-bouton acp-bouton--principal" }, T.projets.nouveauProjet)), projets.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucunProjet) : /* @__PURE__ */ h("ul", { className: "acp-entrees" }, projets.map((p, rang) => /* @__PURE__ */ h(CarteDeProjet, { key: chaine2(p.id) ?? String(rang), projet: p, poste: donnees.poste, naviguer: props.naviguer })))), /* @__PURE__ */ h("div", { className: "acp-grille" }, /* @__PURE__ */ h(CartePoste, { poste: donnees.poste }), /* @__PURE__ */ h(Notifications, { etat: donnees.notifications }), donnees.pause_generale ? null : /* @__PURE__ */ h(CommandePause, { apres: props.apres })));
  }

  // src/projets/DetailProjet.tsx
  var ETATS_REGLABLES = ["creation", "actif", "en_pause"];
  function Libre(props) {
    return props.texte ? /* @__PURE__ */ h("span", null, props.texte) : /* @__PURE__ */ h(Donnee, { valeur: chaine2(props.brut), mono: props.mono });
  }
  function ChangerQuiRepond(props) {
    const { projet } = props;
    const id = chaine2(projet.id);
    const actuel = projet.reponses === "proprietaire" ? "proprietaire" : "hermes_d_abord";
    const [ouvert, fixerOuvert] = useState(false);
    const [choix, fixerChoix] = useState(actuel);
    const envoi = useEnvoi();
    const reglable = Boolean(id) && Boolean(chaine2(projet.depot)) && ETATS_REGLABLES.includes(String(projet.etat));
    if (!reglable && envoi.etat.etat !== "ok") return null;
    const enregistrer = async (evenement) => {
      evenement.preventDefault();
      if (!id) return;
      if (await envoi.envoyer(() => changerReponses(id, choix)) !== null) {
        fixerOuvert(false);
        props.apres();
      }
    };
    const resultat = envoi.etat.etat === "ok" ? envoi.etat.resultat : null;
    return /* @__PURE__ */ h("div", { className: "acp-groupe" }, ouvert ? /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: (e) => void enregistrer(e) }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-qui-repond" }, T.projets.quiRepondSuivantes), /* @__PURE__ */ h(
      "select",
      {
        id: "acp-projet-qui-repond",
        value: choix,
        onChange: (e) => fixerChoix(e.target.value)
      },
      /* @__PURE__ */ h("option", { value: "hermes_d_abord" }, T.projets.reponsesHermes),
      /* @__PURE__ */ h("option", { value: "proprietaire" }, T.projets.reponsesProprietaire)
    )), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.quiRepondAide), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { type: "submit", principal: true, libelle: T.projets.enregistrer, desactive: envoi.etat.etat === "envoi" }), /* @__PURE__ */ h(Bouton, { libelle: T.projets.annuler, surClic: () => fixerOuvert(false) }))) : reglable ? /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.projets.changerQuiRepond,
        surClic: () => {
          envoi.oublier();
          fixerChoix(actuel);
          fixerOuvert(true);
        }
      }
    )) : null, resultat ? /* @__PURE__ */ h("p", { className: "acp-succes", role: "status" }, /* @__PURE__ */ h("span", null, T.projets.reglageEnregistre), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(resultat.questions_ouvertes_inchangees) })) : /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }));
  }
  function Cloture(props) {
    const { projet } = props;
    const id = chaine2(projet.id);
    const [confirmation, fixerConfirmation] = useState(false);
    const envoi = useEnvoi();
    const ouvert = projet.etat === "actif" || projet.etat === "en_pause";
    const resultat = envoi.etat.etat === "ok" ? envoi.etat.resultat : null;
    if (!id || !ouvert && resultat === null) return null;
    const confirmer = async () => {
      if (await envoi.envoyer(() => clore(id)) !== null) {
        fixerConfirmation(false);
        props.apres();
      }
    };
    const branches = listeDeChaines(resultat?.branches_rapportees);
    return /* @__PURE__ */ h("div", { className: "acp-groupe" }, resultat ? /* @__PURE__ */ h("div", { className: "acp-succes", role: "status" }, /* @__PURE__ */ h("p", null, resultat.etat === "termine" ? T.projets.closTermine : T.projets.closAbandonne), /* @__PURE__ */ h("p", null, /* @__PURE__ */ h("span", null, T.projets.cartesArchivees), " ", /* @__PURE__ */ h(Donnee, { valeur: listeDeChaines(resultat.cartes_archivees).length }), /* @__PURE__ */ h("span", null, " ", T.commun.separateur, " "), /* @__PURE__ */ h("span", null, T.projets.questionsAnnulees), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(resultat.questions_annulees) })), branches.length > 0 ? /* @__PURE__ */ h("div", null, /* @__PURE__ */ h("p", null, T.projets.branchesRestent), /* @__PURE__ */ h("ul", { className: "acp-noms" }, branches.map((b) => /* @__PURE__ */ h("li", { key: b }, /* @__PURE__ */ h(Donnee, { valeur: b, mono: true }))))) : null) : confirmation ? /* @__PURE__ */ h("div", { className: "acp-confirmation", role: "group", "aria-labelledby": "acp-clore-question" }, /* @__PURE__ */ h("p", { id: "acp-clore-question" }, T.projets.cloreQuestion), /* @__PURE__ */ h("ul", { className: "acp-noms" }, /* @__PURE__ */ h("li", null, T.projets.clorePoint1), /* @__PURE__ */ h("li", null, T.projets.clorePoint2), /* @__PURE__ */ h("li", null, T.projets.clorePoint3), /* @__PURE__ */ h("li", null, T.projets.clorePoint4)), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.projets.cloreConfirmer,
        danger: true,
        surClic: () => void confirmer(),
        desactive: envoi.etat.etat === "envoi"
      }
    ), /* @__PURE__ */ h(
      Bouton,
      {
        libelle: T.projets.annuler,
        surClic: () => {
          fixerConfirmation(false);
          envoi.oublier();
        }
      }
    ))) : /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.projets.clore, danger: true, surClic: () => fixerConfirmation(true) })), resultat ? null : /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }));
  }
  function EnTete(props) {
    const { projet } = props;
    const id = chaine2(projet.id);
    const envoi = useEnvoi();
    const geste = async (travail) => {
      if (await envoi.envoyer(travail) !== null) props.apres();
    };
    const plafonds = projet.plafonds ?? {};
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": "acp-projet-titre" }, /* @__PURE__ */ h("h2", { className: "acp-carte__titre acp-carte__titre--grand", id: "acp-projet-titre" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(projet.titre) })), /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatProjet(projet.etat, projet.etat_derive), brut: projet.etat })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.objectif }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(projet.objectif) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.cartesFaites }, /* @__PURE__ */ h(Avancement, { faites: projet.compteurs?.faites, total: projet.compteurs?.total })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.tour }, /* @__PURE__ */ h(Donnee, { valeur: nombre(projet.tour) }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.sur), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(plafonds.tours) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.cartesCreees }, /* @__PURE__ */ h(Donnee, { valeur: nombre(projet.cartes_creees) }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.sur), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(plafonds.cartes) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.correctionsParEtape }, /* @__PURE__ */ h(Donnee, { valeur: nombre(plafonds.corrections) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.profil }, /* @__PURE__ */ h(Libre, { texte: libelleProfil(projet.profil), brut: projet.profil, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.depot }, projet.depot === null ? /* @__PURE__ */ h("span", null, T.projets.sansDepot) : /* @__PURE__ */ h(Donnee, { valeur: chaine2(projet.depot), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.reponses }, chaine2(projet.depot) ? /* @__PURE__ */ h(Libre, { texte: libelleReponses(projet.reponses), brut: projet.reponses, mono: true }) : /* @__PURE__ */ h("span", null, T.projets.reponsesSansObjetCourt)), /* @__PURE__ */ h(Ligne, { libelle: T.projets.poste }, /* @__PURE__ */ h(EtatDuPoste, { poste: props.liste?.poste })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.origine }, /* @__PURE__ */ h(Libre, { texte: libelleOrigine(projet.origine), brut: projet.origine, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.creeLe }, /* @__PURE__ */ h(Horodatage, { valeur: projet.cree_le })), projet.termine_le ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.termineLe }, /* @__PURE__ */ h(Horodatage, { valeur: projet.termine_le })) : null), id && (projet.etat === "actif" || projet.etat === "en_pause") ? /* @__PURE__ */ h("div", { className: "acp-actions" }, projet.etat === "actif" ? /* @__PURE__ */ h(
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
    )) : null, /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }), /* @__PURE__ */ h(ChangerQuiRepond, { projet, apres: props.apres }), /* @__PURE__ */ h(Cloture, { projet, apres: props.apres }));
  }
  function Resume(props) {
    const resume = chaine2(props.carte.resume);
    const identifiant = chaine2(props.carte.carte);
    const [entier2, fixerEntier] = useState(null);
    const lecture = useEnvoi();
    if (!resume) return null;
    const tronque = props.carte.resume_tronque === true && entier2 === null;
    const lire = async () => {
      if (!props.projet || !identifiant) return;
      const lu = await lecture.envoyer(() => lireCarte(props.projet, identifiant));
      if (lu?.carte) fixerEntier(lu.carte);
    };
    return /* @__PURE__ */ h("details", { className: "acp-details" }, /* @__PURE__ */ h("summary", null, T.projets.resume), /* @__PURE__ */ h("p", { className: "acp-texte-long" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(entier2?.resume) ?? resume })), tronque ? /* @__PURE__ */ h("div", null, /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.projets.extrait), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(resume.length) }), " ", /* @__PURE__ */ h("span", null, T.projets.caracteresSur), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(props.carte.resume_longueur) })), props.projet && identifiant ? /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { libelle: T.projets.lireEnEntier, surClic: () => void lire(), desactive: lecture.etat.etat === "envoi" })) : null, /* @__PURE__ */ h(RetourEnvoi, { etat: lecture.etat })) : null, entier2?.tronque === true ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.texteBorne) : null);
  }
  function CarteDuGraphe(props) {
    const { carte } = props;
    return /* @__PURE__ */ h("li", { className: "acp-entree" }, /* @__PURE__ */ h("h4", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.titre) })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.statut }, /* @__PURE__ */ h(Etiquette, { libelle: libelleStatut(carte.statut), brut: carte.statut })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.voie }, /* @__PURE__ */ h(Libre, { texte: libelleVoie(carte.voie), brut: carte.voie, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.tour }, /* @__PURE__ */ h(Donnee, { valeur: nombre(carte.tour) })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.modeleDemande }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.modele), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.effort }, chaine2(carte.effort) ? /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.effort), mono: true }) : /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.effortParDefaut)), /* @__PURE__ */ h(Ligne, { libelle: T.projets.palier }, /* @__PURE__ */ h(Libre, { texte: libellePalier(carte.palier), brut: carte.palier, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.modeleServi }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.modele_servi) })), chaine2(carte.mention) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.mention }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.mention) })) : null, chaine2(carte.carte) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.carte }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.carte), mono: true })) : null), /* @__PURE__ */ h(Resume, { projet: props.projet, carte }));
  }
  function Cartes(props) {
    const groupes = /* @__PURE__ */ new Map();
    for (const carte of props.cartes) {
      const role = chaine2(carte.role) ?? "";
      groupes.set(role, [...groupes.get(role) ?? [], carte]);
    }
    const connus = [...ORDRE_DES_ROLES];
    const roles = [...connus.filter((r) => groupes.has(r)), ...[...groupes.keys()].filter((r) => !connus.includes(r))];
    return /* @__PURE__ */ h(Carte, { titre: T.projets.cartes, id: "acp-projet-cartes" }, props.cartes.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucuneCarte) : null, roles.map((role) => /* @__PURE__ */ h("div", { key: role || "?", className: "acp-groupe" }, /* @__PURE__ */ h("h3", { className: "acp-sous-titre" }, /* @__PURE__ */ h(Libre, { texte: libelleRole(role), brut: role, mono: true })), /* @__PURE__ */ h("ul", { className: "acp-entrees" }, (groupes.get(role) ?? []).map((c, rang) => /* @__PURE__ */ h(CarteDuGraphe, { key: chaine2(c.carte) ?? `${role}-${rang}`, projet: props.projet, carte: c }))))));
  }
  function Resultat(props) {
    const resultat = props.projet.resultat;
    const texte = chaine2(resultat?.texte);
    if (!texte) return null;
    return /* @__PURE__ */ h(Carte, { titre: T.projets.resultatTitre, id: "acp-projet-resultat" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.projets.resultatIntro), " ", /* @__PURE__ */ h("span", null, T.projets.tour), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(resultat?.tour) })), /* @__PURE__ */ h("p", { className: "acp-texte-long" }, /* @__PURE__ */ h(Donnee, { valeur: texte })), resultat?.tronque === true ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.texteBorne) : null);
  }
  function Tours(props) {
    const tours = Array.isArray(props.projet.tours) ? props.projet.tours : [];
    if (tours.length === 0) return null;
    return /* @__PURE__ */ h(Carte, { titre: T.projets.toursTitre, id: "acp-projet-tours" }, tours.map((t, rang) => {
      const decisions = listeDeChaines(t.decisions);
      return /* @__PURE__ */ h("div", { key: String(t.tour ?? rang), className: "acp-groupe" }, /* @__PURE__ */ h("h3", { className: "acp-sous-titre" }, /* @__PURE__ */ h("span", null, T.projets.tour), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(t.tour) })), /* @__PURE__ */ h("p", { className: "acp-texte-long" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(t.resume) })), decisions.length > 0 ? /* @__PURE__ */ h("div", null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.decisions), /* @__PURE__ */ h("ul", { className: "acp-noms" }, decisions.map((d, i) => /* @__PURE__ */ h("li", { key: String(i) }, /* @__PURE__ */ h(Donnee, { valeur: d }))))) : null);
    }));
  }
  function QuestionsDuProjet(props) {
    const questions = Array.isArray(props.projet.questions_ouvertes) ? props.projet.questions_ouvertes : [];
    if (questions.length === 0) return null;
    return /* @__PURE__ */ h(Carte, { titre: T.projets.questionsEnAttente, id: "acp-projet-questions" }, /* @__PURE__ */ h("ul", { className: "acp-noms" }, questions.map((q, rang) => /* @__PURE__ */ h("li", { key: chaine2(q.id) ?? String(rang), className: "acp-question-courte" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatQuestion(q.etat, q.chez), brut: q.etat }), /* @__PURE__ */ h("p", { className: "acp-texte-long" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(q.texte) }))))), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(LienVue, { vue: { genre: "questions" }, naviguer: props.naviguer }, T.projets.voirQuestions)));
  }
  function Journal(props) {
    const journal = Array.isArray(props.projet.journal) ? props.projet.journal : [];
    return /* @__PURE__ */ h(Carte, { titre: T.projets.journal, id: "acp-projet-journal" }, journal.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.journalVide) : /* @__PURE__ */ h("details", { className: "acp-details" }, /* @__PURE__ */ h("summary", null, /* @__PURE__ */ h("span", null, T.projets.journalOuvrir), " ", /* @__PURE__ */ h(Donnee, { valeur: nombre(journal.length) })), /* @__PURE__ */ h("ul", { className: "acp-journal" }, journal.map((j, rang) => {
      const acteur = libelleActeurJournal(j.acteur);
      return /* @__PURE__ */ h("li", { key: String(rang) }, /* @__PURE__ */ h(Horodatage, { valeur: j.quand }), " ", /* @__PURE__ */ h(Libre, { texte: libelleActionJournal(j.action), brut: j.action, mono: true }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, acteur.libelle ? /* @__PURE__ */ h("span", null, acteur.libelle) : null, acteur.libelle && acteur.donnee ? " " : null, acteur.donnee ? /* @__PURE__ */ h(Donnee, { valeur: acteur.donnee, mono: true }) : null), chaine2(j.detail) || chaine2(j.cible) ? /* @__PURE__ */ h("details", { className: "acp-journal__detail" }, /* @__PURE__ */ h("summary", null, T.projets.detailTechnique), chaine2(j.cible) ? /* @__PURE__ */ h(Donnee, { valeur: chaine2(j.cible), mono: true }) : null, " ", chaine2(j.detail) ? /* @__PURE__ */ h(Donnee, { valeur: chaine2(j.detail), mono: true }) : null) : null);
    }))));
  }
  function DetailProjet(props) {
    const sondage = useDonnees(() => lireProjet(props.id), props.jeton, ["projets", "questions", "pause"]);
    const projet = sondage.valeur?.projet ?? null;
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(LienVue, { vue: { genre: "liste" }, naviguer: props.naviguer }, T.projets.retour)), projet === null && sondage.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : null, sondage.erreur !== null ? /* @__PURE__ */ h(BlocRefus, { erreur: sondage.erreur }) : null, projet !== null ? /* @__PURE__ */ h("div", { className: "acp-sections" }, /* @__PURE__ */ h(EnTete, { projet, liste: props.liste, apres: props.apres }), /* @__PURE__ */ h(QuestionsDuProjet, { projet, naviguer: props.naviguer }), /* @__PURE__ */ h(Resultat, { projet }), /* @__PURE__ */ h(Cartes, { projet: chaine2(projet.id), cartes: Array.isArray(projet.cartes) ? projet.cartes : [] }), /* @__PURE__ */ h(Tours, { projet }), /* @__PURE__ */ h(Journal, { projet })) : null);
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
  function voiesFermeesPourDepot(poste, depot) {
    if (!depot) return {};
    const depots = Array.isArray(poste?.executant?.depots) ? poste.executant.depots : [];
    const trouve = depots.find((d) => d.alias === depot);
    const fermees = trouve?.voies_fermees;
    return fermees && typeof fermees === "object" ? fermees : {};
  }
  function effortsAdmis(voie, modele, interdits) {
    const modeles = Array.isArray(voie?.modeles) ? voie.modeles : [];
    const choisi = modele ? modeles.find((m) => m.id === modele) : modeles.find((m) => m.isDefault === true);
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
    const fermees = voiesFermeesPourDepot(props.poste, depot);
    const voieChoisie = voie !== "" && !fermees[voie] ? voie : voies.find((v) => !fermees[v]) ?? "";
    const releveVoie = voieChoisie ? cataloguePoste?.voies?.[voieChoisie] : void 0;
    const modeles = Array.isArray(releveVoie?.modeles) ? releveVoie.modeles.filter((m) => chaine2(m.id)) : [];
    const efforts = effortsAdmis(releveVoie, modele, interdits);
    const avecExploration = depot !== "" && voies.length > 0;
    const modeleExige = avecExploration && voieChoisie !== "" && modele === "" && !modeles.some((m) => m.isDefault === true);
    const sansDepot = depot === "";
    const complet = titre.trim() !== "" && objectif.trim() !== "" && !modeleExige;
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
      if (avecExploration && voieChoisie) {
        demande.exploration = { voie: voieChoisie, ...modele ? { modele } : {}, ...effort ? { effort } : {} };
      }
      const resultat = await envoi.envoyer(() => lancerProjet(demande, cle));
      const id = chaine2(resultat?.projet?.id);
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
    ))), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-depot" }, T.projets.champDepot), /* @__PURE__ */ h(
      "select",
      {
        id: "acp-projet-depot",
        value: depot,
        disabled: depots === null,
        "aria-describedby": depots === null ? "acp-projet-depot-aide" : void 0,
        onChange: (e) => {
          fixerDepot(valeurDe(e));
          fixerVoie("");
          fixerModele("");
          fixerEffort("");
        }
      },
      /* @__PURE__ */ h("option", { value: "" }, T.projets.sansDepot),
      (depots ?? []).map((d) => /* @__PURE__ */ h("option", { key: d, value: d, "data-acp-donnee": "" }, d))
    ), depots === null ? /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-projet-depot-aide" }, props.posteIllisible ? T.projets.depotsInconnus : T.projets.aucunDepotConnu) : null), /* @__PURE__ */ h("fieldset", { className: "acp-groupe-choix" }, /* @__PURE__ */ h("legend", null, T.projets.champReponses), sansDepot ? /* @__PURE__ */ h("p", { className: "acp-discret", id: "acp-projet-reponses-sans-objet" }, T.projets.reponsesSansObjet) : /* @__PURE__ */ h(Fragment, null, /* @__PURE__ */ h("label", { className: "acp-choix-radio" }, /* @__PURE__ */ h(
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
    ), /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-choix-radio__titre" }, T.projets.reponsesProprietaire), /* @__PURE__ */ h("span", { className: "acp-discret" }, T.projets.reponsesProprietaireAide))))), cataloguePoste?.releve_factice === true ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "note" }, T.projets.releveFactice) : null, avecExploration ? /* @__PURE__ */ h("fieldset", { className: "acp-groupe-choix" }, /* @__PURE__ */ h("legend", null, T.projets.exploration), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.explorationAide), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-voie" }, T.projets.champVoie), /* @__PURE__ */ h(
      "select",
      {
        id: "acp-projet-voie",
        value: voieChoisie,
        "aria-describedby": voies.some((v) => fermees[v]) ? "acp-projet-voie-fermee" : void 0,
        onChange: (e) => {
          fixerVoie(valeurDe(e));
          fixerModele("");
          fixerEffort("");
        }
      },
      voies.map(
        (v) => libelleVoie(v) ? /* @__PURE__ */ h("option", { key: v, value: v, disabled: Boolean(fermees[v]) }, libelleVoie(v)) : /* @__PURE__ */ h("option", { key: v, value: v, "data-acp-donnee": "", disabled: Boolean(fermees[v]) }, v)
      )
    ), voies.some((v) => fermees[v]) ? /* @__PURE__ */ h("ul", { className: "acp-liste", id: "acp-projet-voie-fermee" }, voies.filter((v) => fermees[v]).map((v) => /* @__PURE__ */ h("li", { key: v, className: "acp-discret" }, /* @__PURE__ */ h("span", null, libelleVoie(v) ?? v), " ", /* @__PURE__ */ h("span", null, T.projets.voiesFermeesPourDepot), " ", /* @__PURE__ */ h(Donnee, { valeur: fermees[v] })))) : null), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-modele" }, T.projets.champModele), /* @__PURE__ */ h(
      "select",
      {
        id: "acp-projet-modele",
        value: modele,
        onChange: (e) => {
          fixerModele(valeurDe(e));
          fixerEffort("");
        }
      },
      /* @__PURE__ */ h("option", { value: "", disabled: !modeles.some((m) => m.isDefault === true) }, modeles.some((m) => m.isDefault === true) ? T.projets.modeleParDefaut : T.projets.modeleAChoisir),
      modeles.map((m) => /* @__PURE__ */ h("option", { key: String(m.id), value: String(m.id), "data-acp-donnee": "" }, String(m.id)))
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-projet-effort" }, T.projets.champEffort), /* @__PURE__ */ h("select", { id: "acp-projet-effort", value: effort, onChange: (e) => fixerEffort(valeurDe(e)) }, /* @__PURE__ */ h("option", { value: "" }, T.projets.effortParDefaut), efforts.map((x) => /* @__PURE__ */ h("option", { key: x, value: x, "data-acp-donnee": "" }, x)))), /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.projets.releveDu), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine2(releveVoie?.releve_le_lisible) })), releveVoie?.perime === true ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.projets.relevePerime) : null, modeleExige ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.projets.modeleExige) : null, voieChoisie === "" ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "note", id: "acp-projet-sans-exploration" }, T.projets.aucunExecutantOuvert) : null) : null, /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
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
        posteIllisible: poste.etat === "erreur",
        naviguer: props.naviguer,
        apres: props.apres
      }
    ) : null);
  }

  // src/projets/Questions.tsx
  var cleCarte = (tableau, carte) => {
    const t = chaine2(tableau);
    const c = chaine2(carte);
    return t && c ? `${t}/${c}` : null;
  };
  function LienProjet(props) {
    const id = chaine2(props.id);
    const titre = /* @__PURE__ */ h(Donnee, { valeur: chaine2(props.titre) });
    return id ? /* @__PURE__ */ h(LienVue, { vue: { genre: "detail", id }, naviguer: props.naviguer }, titre) : titre;
  }
  function Entree(props) {
    const classes = ["acp-entree", props.classe, props.cible ? "acp-entree--cible" : null].filter(Boolean).join(" ");
    return /* @__PURE__ */ h("li", { className: classes, "aria-current": props.cible ? "true" : void 0, "data-acp-cible": props.cible ? "" : void 0 }, props.children);
  }
  function AnnonceSection(props) {
    const { annonce } = props;
    if (!annonce) return null;
    return /* @__PURE__ */ h("p", { className: annonce.alerte ? "acp-alerte-texte" : "acp-succes", role: "status" }, /* @__PURE__ */ h("span", null, annonce.texte), annonce.statut ? /* @__PURE__ */ h("span", null, " ", /* @__PURE__ */ h("span", null, T.projets.statutApres), " ", /* @__PURE__ */ h(Etiquette, { libelle: libelleStatut(annonce.statut), brut: annonce.statut })) : null);
  }
  function messageReponse(resultat) {
    if (resultat?.reprise_differee === true) return T.projets.reponseDifferee;
    if (resultat?.carte_debloquee === true) return T.projets.reponseEnvoyee;
    return T.projets.reponseSansReprise;
  }
  function annonceReponse(resultat) {
    const texte = messageReponse(resultat);
    return { texte, alerte: texte === T.projets.reponseSansReprise };
  }
  function messageTriage(resultat) {
    if (resultat?.reprise !== true) return T.projets.carteNonReprise;
    if (resultat.action === "prolongation") return T.projets.prolongationFaite;
    if (resultat.action === "relance_planification") return T.projets.relanceFaite;
    return T.projets.carteReprise;
  }
  function annonceTriage(resultat) {
    const texte = messageTriage(resultat);
    return { texte, alerte: texte === T.projets.carteNonReprise };
  }
  function QuiRepond(props) {
    const { question } = props;
    if (question.chez === "hermes") {
      const statut = libelleStatut(question.carte_repondre_statut);
      return /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: { texte: T.projets.chezHermes, famille: "actif" } }), statut ? /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.projets.carteRepondre), " ", /* @__PURE__ */ h(Etiquette, { libelle: statut })) : null);
    }
    if (question.chez === "proprietaire") return /* @__PURE__ */ h(Etiquette, { libelle: { texte: T.projets.aVous, famille: "degrade" } });
    return /* @__PURE__ */ h(Donnee, { valeur: chaine2(question.chez), mono: true });
  }
  function Question(props) {
    const { question } = props;
    const id = chaine2(question.id);
    const [reponse, fixerReponse] = useState("");
    const envoi = useEnvoi();
    const champ = `acp-reponse-${id ?? "inconnue"}`;
    const repondre = async (evenement) => {
      evenement.preventDefault();
      if (!id || !reponse.trim()) return;
      props.annoncer(null);
      const resultat = await envoi.envoyer(() => repondreQuestion(id, reponse.trim()));
      if (resultat !== null) {
        fixerReponse("");
        props.annoncer(annonceReponse(resultat));
        props.traitee(`q:${id}`);
        props.apres();
      }
    };
    return /* @__PURE__ */ h(Entree, { cible: props.cible, classe: "acp-question" }, /* @__PURE__ */ h("p", { className: "acp-question__texte" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(question.texte) })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.projet }, /* @__PURE__ */ h(LienProjet, { id: question.projet, titre: question.projet_titre, naviguer: props.naviguer })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.etat }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatQuestion(question.etat, question.chez), brut: question.etat })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.quiRepondQuestion }, /* @__PURE__ */ h(QuiRepond, { question })), chaine2(question.contexte) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.contexte }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(question.contexte) })) : null, chaine2(question.motif_escalade) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.motifEscalade }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(question.motif_escalade) })) : null, /* @__PURE__ */ h(Ligne, { libelle: T.projets.carteDeLaQuestion }, chaine2(question.carte_titre) ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: chaine2(question.carte_titre) }), " ", /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(question.carte), mono: true }))) : /* @__PURE__ */ h(Donnee, { valeur: chaine2(question.carte), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.poseeLe }, /* @__PURE__ */ h(Horodatage, { valeur: question.cree_le, relative: true }))), question.chez === "hermes" ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.chezHermesAide) : null, id ? /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: (e) => void repondre(e) }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: champ }, T.projets.votreReponse), /* @__PURE__ */ h(
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
    )), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat })) : null);
  }
  function Triage(props) {
    const { carte } = props;
    const tableau = chaine2(carte.tableau);
    const identifiant = chaine2(carte.carte);
    const actions = listeDeChaines(carte.actions);
    const gestes = actions.length > 0 ? actions : ["reprendre"];
    const avecConsigne = gestes.some((g) => g === "prolonger" || g === "relancer" || g === "reprendre");
    const [consigne, fixerConsigne] = useState("");
    const envoi = useEnvoi();
    const conclusion = useEnvoi();
    const champ = `acp-consigne-${identifiant ?? "inconnue"}`;
    const reprendre = async (evenement) => {
      evenement.preventDefault();
      if (!tableau || !identifiant) return;
      props.annoncer(null);
      const resultat = await envoi.envoyer(() => reprendreTriage(tableau, identifiant, consigne.trim() || null));
      if (resultat !== null) {
        fixerConsigne("");
        props.annoncer(annonceTriage(resultat));
        props.traitee(`carte:${tableau}/${identifiant}`);
        props.apres();
      }
    };
    const conclure = async () => {
      if (!tableau || !identifiant) return;
      props.annoncer(null);
      if (await conclusion.envoyer(() => conclureTriage(tableau, identifiant)) !== null) {
        props.annoncer({ texte: T.projets.conclusionFaite, alerte: false });
        props.traitee(`carte:${tableau}/${identifiant}`);
        props.apres();
      }
    };
    const libelleReprise = gestes.includes("prolonger") ? T.projets.prolonger : gestes.includes("relancer") ? T.projets.relancer : T.projets.reprendreCarte;
    const aide = carte.genre === "tours" ? T.projets.prolongerAideTours : carte.genre === "cartes" ? T.projets.prolongerAideCartes : carte.genre === "sans_plan" ? T.projets.relancerAide : carte.genre === "corrections" ? T.projets.prolongerP6 : null;
    const occupe = envoi.etat.etat === "envoi" || conclusion.etat.etat === "envoi";
    return /* @__PURE__ */ h(Entree, { cible: props.cible }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.titre) })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.projet }, /* @__PURE__ */ h(LienProjet, { id: carte.projet, titre: carte.projet_titre, naviguer: props.naviguer })), chaine2(carte.raison) ? /* @__PURE__ */ h(Ligne, { libelle: T.projets.raison }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.raison) })) : null), aide ? /* @__PURE__ */ h("p", { className: "acp-discret" }, aide) : null, gestes.includes("conclure") ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.conclureAide) : null, tableau && identifiant ? /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: (e) => void reprendre(e) }, avecConsigne ? /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: champ }, T.projets.consigne), /* @__PURE__ */ h(
      "textarea",
      {
        id: champ,
        "data-acp-donnee": "",
        rows: 3,
        maxLength: 8e3,
        value: consigne,
        onChange: (e) => fixerConsigne(e.target.value)
      }
    )) : null, /* @__PURE__ */ h("div", { className: "acp-actions" }, avecConsigne ? /* @__PURE__ */ h(Bouton, { type: "submit", principal: true, libelle: libelleReprise, desactive: occupe }) : null, gestes.includes("conclure") ? /* @__PURE__ */ h(Bouton, { libelle: T.projets.conclure, surClic: () => void conclure(), desactive: occupe }) : null), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat }), /* @__PURE__ */ h(RetourEnvoi, { etat: conclusion.etat })) : null);
  }
  function Revue(props) {
    const { revue } = props;
    const tableau = chaine2(revue.tableau);
    const identifiant = chaine2(revue.carte);
    const chemins = listeDeChaines(revue.chemins);
    const [motif, fixerMotif] = useState("");
    const acceptation = useEnvoi();
    const refus = useEnvoi();
    const champ = `acp-motif-revue-${identifiant ?? "inconnue"}`;
    const accepter = async () => {
      if (!tableau || !identifiant) return;
      props.annoncer(null);
      if (await acceptation.envoyer(() => accepterRevue(tableau, identifiant)) !== null) {
        props.annoncer({ texte: T.projets.revueAcceptee, alerte: false });
        props.traitee(`carte:${tableau}/${identifiant}`);
        props.apres();
      }
    };
    const refuser = async (evenement) => {
      evenement.preventDefault();
      if (!tableau || !identifiant || !motif.trim()) return;
      props.annoncer(null);
      if (await refus.envoyer(() => refuserRevue(tableau, identifiant, motif.trim())) !== null) {
        fixerMotif("");
        props.annoncer({ texte: T.projets.revueRefusee, alerte: false });
        props.traitee(`carte:${tableau}/${identifiant}`);
        props.apres();
      }
    };
    const d = revue.diffstat;
    const occupe = acceptation.etat.etat === "envoi" || refus.etat.etat === "envoi";
    return /* @__PURE__ */ h(Entree, { cible: props.cible }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(revue.titre) })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.projet }, /* @__PURE__ */ h(LienProjet, { id: revue.projet, titre: revue.projet_titre, naviguer: props.naviguer })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.chemins }, chemins.length === 0 ? /* @__PURE__ */ h(Donnee, { valeur: null }) : /* @__PURE__ */ h("ul", { className: "acp-noms" }, chemins.map((c) => /* @__PURE__ */ h("li", { key: c }, /* @__PURE__ */ h(Donnee, { valeur: c, mono: true }))))), /* @__PURE__ */ h(Ligne, { libelle: T.projets.diffstat }, d ? /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: d.fichiers ?? null }), " ", T.projets.fichiers), /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: d.ajouts ?? null }), " ", T.projets.ajouts), /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: d.retraits ?? null }), " ", T.projets.retraits)) : /* @__PURE__ */ h(Donnee, { valeur: null })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.branche }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(revue.branche), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.tete }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(revue.tete), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.resume }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(revue.resume) }))), /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(revue.diff) })), tableau && identifiant ? /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: (e) => void refuser(e) }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: champ }, T.projets.motifRefus), /* @__PURE__ */ h(
      "textarea",
      {
        id: champ,
        "data-acp-donnee": "",
        rows: 2,
        maxLength: 1e3,
        value: motif,
        onChange: (e) => fixerMotif(e.target.value)
      }
    )), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { principal: true, libelle: T.projets.accepterRevue, surClic: () => void accepter(), desactive: occupe }), /* @__PURE__ */ h(Bouton, { type: "submit", danger: true, libelle: T.projets.refuserRevue, desactive: occupe || !motif.trim() })), /* @__PURE__ */ h(RetourEnvoi, { etat: acceptation.etat }), /* @__PURE__ */ h(RetourEnvoi, { etat: refus.etat })) : null);
  }
  function messageRelance(resultat, integration = false) {
    if (resultat?.relancee === true) {
      if (resultat.branche_neuve === true) return T.projets.relanceeBrancheNeuve;
      if (integration) return T.projets.relanceeFusion;
      return resultat.session_neuve === true ? T.projets.relanceeSessionNeuve : T.projets.relancee;
    }
    return T.projets.nonRelancee;
  }
  function Arretee(props) {
    const { carte } = props;
    const tableau = chaine2(carte.tableau);
    const identifiant = chaine2(carte.carte);
    const [consigne, fixerConsigne] = useState("");
    const envoi = useEnvoi();
    const champ = `acp-relance-${identifiant ?? "inconnue"}`;
    const integration = carte.integration === true;
    const relancer = async (evenement) => {
      evenement.preventDefault();
      if (!tableau || !identifiant) return;
      props.annoncer(null);
      const envoyee = integration ? null : consigne.trim() || null;
      const resultat = await envoi.envoyer(() => relancerCarte(tableau, identifiant, envoyee));
      if (resultat !== null) {
        fixerConsigne("");
        const texte = messageRelance(resultat, integration);
        props.annoncer({ texte, alerte: texte === T.projets.nonRelancee, statut: chaine2(resultat.statut_apres) });
        props.traitee(`carte:${tableau}/${identifiant}`);
        props.apres();
      }
    };
    return /* @__PURE__ */ h(Entree, { cible: props.cible }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.titre) })), /* @__PURE__ */ h("p", { className: "acp-etat" }, carte.abandonnee === true ? /* @__PURE__ */ h(Etiquette, { libelle: { texte: T.projets.abandonnee, famille: "echec" } }) : /* @__PURE__ */ h(Etiquette, { libelle: { texte: T.projets.statuts.blocked, famille: "echec" } })), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.projet }, /* @__PURE__ */ h(LienProjet, { id: carte.projet, titre: carte.projet_titre, naviguer: props.naviguer })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.assigne }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.assigne), mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.raison }, /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.raison) }))), carte.relancable === true && tableau && identifiant ? /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: (e) => void relancer(e) }, carte.quarantaine === true ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.projets.relanceQuarantaineAide) : integration ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.relanceIntegrationAide) : carte.executant === true ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.relanceExecutantAide) : null, integration ? null : /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: champ }, T.projets.consigne), /* @__PURE__ */ h(
      "textarea",
      {
        id: champ,
        "data-acp-donnee": "",
        rows: 3,
        maxLength: 4e3,
        value: consigne,
        onChange: (e) => fixerConsigne(e.target.value)
      }
    )), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(Bouton, { type: "submit", principal: true, libelle: T.projets.relancerCarte, desactive: envoi.etat.etat === "envoi" })), /* @__PURE__ */ h(RetourEnvoi, { etat: envoi.etat })) : /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.projets.nonRelancable), " ", /* @__PURE__ */ h(Donnee, { valeur: chaine2(carte.refus_relance) })));
  }
  function Discussions(props) {
    const valeur = props.lecture.valeur;
    let contenu;
    if (valeur === null) {
      contenu = props.lecture.erreur ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.discussionsInconnues) : /* @__PURE__ */ h(EnChargement, null);
    } else if (!valeur.connu) {
      const requetes = props.serveur?.suivies === true ? props.serveur.requetes_ouvertes : null;
      contenu = /* @__PURE__ */ h("div", null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.discussionsInconnues), typeof requetes === "number" ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.projets.requetesOuvertes), " ", /* @__PURE__ */ h(Donnee, { valeur: requetes })) : null);
    } else if (valeur.sessions.length === 0) {
      contenu = /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucuneDiscussion);
    } else {
      contenu = /* @__PURE__ */ h("ul", { className: "acp-entrees acp-entrees--une" }, valeur.sessions.map((s) => /* @__PURE__ */ h("li", { key: s.cle, className: "acp-entree" }, /* @__PURE__ */ h("h3", { className: "acp-entree__nom" }, s.titre ? /* @__PURE__ */ h(Donnee, { valeur: s.titre }) : /* @__PURE__ */ h("span", null, T.projets.discussionSansTitre)), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.discussionEtat }, /* @__PURE__ */ h(Etiquette, { libelle: { texte: T.projets.discussionEnAttente, famille: "degrade" } })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.discussionActivite }, /* @__PURE__ */ h(Horodatage, { valeur: s.derniereActivite, relative: true })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.discussionApercu }, /* @__PURE__ */ h(Donnee, { valeur: s.apercu })), /* @__PURE__ */ h(Ligne, { libelle: T.projets.discussionCle }, /* @__PURE__ */ h(Donnee, { valeur: s.cle, mono: true }))), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
        "a",
        {
          className: "acp-bouton acp-bouton--principal",
          href: `${cheminDeBase()}/discussion?session=${encodeURIComponent(s.cle)}`
        },
        T.discussion.ouvrirDiscussion
      )))));
    }
    return /* @__PURE__ */ h(Carte, { titre: T.projets.discussionsTitre, id: "acp-questions-discussions" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.discussionsIntro), contenu, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.discussionsLimite));
  }
  function aTraiter(file, discussions) {
    const compteurs = file?.compteurs;
    if (!compteurs || typeof compteurs.a_traiter !== "number") return null;
    const connues = discussions !== null && discussions.connu;
    return {
      total: compteurs.a_traiter + (connues ? discussions.sessions.length : 0),
      chezHermes: typeof compteurs.chez_hermes === "number" ? compteurs.chez_hermes : null,
      discussionsConnues: connues
    };
  }
  function Resume2(props) {
    const compte = aTraiter(props.file, props.discussions);
    if (compte === null) return null;
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": "acp-questions-resume" }, /* @__PURE__ */ h("h2", { className: "acp-carte__titre", id: "acp-questions-resume" }, T.projets.fileTitre), /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.projets.aTraiterParVous }, /* @__PURE__ */ h("span", null, /* @__PURE__ */ h(Donnee, { valeur: compte.total }), compte.discussionsConnues ? null : /* @__PURE__ */ h("span", { className: "acp-discret" }, " ", T.projets.discussionsNonComptees))), /* @__PURE__ */ h(Ligne, { libelle: T.projets.chezHermesCompte }, /* @__PURE__ */ h(Donnee, { valeur: compte.chezHermes }))));
  }
  function Questions(props) {
    const [annonceQuestion, fixerAnnonceQuestion] = useState(null);
    const [annonceTriage2, fixerAnnonceTriage] = useState(null);
    const [annonceRevue, fixerAnnonceRevue] = useState(null);
    const [annonceRelance, fixerAnnonceRelance] = useState(null);
    const [traitees, fixerTraitees] = useState([]);
    const traitee = (cle) => fixerTraitees((avant) => avant.includes(cle) ? avant : [...avant, cle]);
    const defile = useRef(null);
    const donnees = props.lecture.valeur;
    const questions = Array.isArray(donnees?.questions) ? donnees.questions : [];
    const triage = Array.isArray(donnees?.triage) ? donnees.triage : [];
    const bloquees = Array.isArray(donnees?.bloquees) ? donnees.bloquees : [];
    const revues = Array.isArray(donnees?.revues) ? donnees.revues : [];
    const illisibles = listeDeChaines(donnees?.tableaux_illisibles);
    const estQuestion = (q) => Boolean(props.cible.q) && chaine2(q.id) === props.cible.q;
    const estCarte = (c) => Boolean(props.cible.carte) && cleCarte(c.tableau, c.carte) === props.cible.carte;
    const cibleVoulue = props.cible.q ? `q:${props.cible.q}` : props.cible.carte ? `carte:${props.cible.carte}` : null;
    const cibleTrouvee = questions.some(estQuestion) || triage.some(estCarte) || revues.some(estCarte) || bloquees.some(estCarte);
    const cibleTraiteeIci = cibleVoulue !== null && traitees.includes(cibleVoulue);
    const tableauCible = props.cible.carte ? props.cible.carte.split("/")[0] : null;
    const cibleIllisible = tableauCible !== null && illisibles.includes(tableauCible);
    useEffect(() => {
      if (!cibleVoulue || !cibleTrouvee || defile.current === cibleVoulue) return;
      defile.current = cibleVoulue;
      try {
        document.querySelector("[data-acp-cible]")?.scrollIntoView?.({ block: "center" });
      } catch {
      }
    }, [cibleVoulue, cibleTrouvee]);
    if (donnees === null) {
      return props.lecture.erreur ? /* @__PURE__ */ h(BlocErreur, { erreur: props.lecture.erreur, message: T.projets.questionsIndisponibles }) : /* @__PURE__ */ h(EnChargement, null);
    }
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, props.lecture.erreur ? /* @__PURE__ */ h(BlocRefus, { erreur: props.lecture.erreur }) : null, cibleVoulue && !cibleTrouvee && !cibleTraiteeIci ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, cibleIllisible ? T.projets.cibleIllisible : T.projets.cibleTraitee) : null, /* @__PURE__ */ h(Resume2, { file: donnees, discussions: props.discussions.valeur }), /* @__PURE__ */ h(Carte, { titre: T.projets.questionsTitre, id: "acp-questions-ouvertes" }, /* @__PURE__ */ h(AnnonceSection, { annonce: annonceQuestion }), questions.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucuneQuestion) : /* @__PURE__ */ h("ul", { className: "acp-entrees acp-entrees--une" }, questions.map((q, rang) => /* @__PURE__ */ h(
      Question,
      {
        key: chaine2(q.id) ?? String(rang),
        question: q,
        cible: estQuestion(q),
        naviguer: props.naviguer,
        apres: props.apres,
        annoncer: fixerAnnonceQuestion,
        traitee
      }
    )))), /* @__PURE__ */ h(Carte, { titre: T.projets.triageTitre, id: "acp-questions-triage" }, /* @__PURE__ */ h(AnnonceSection, { annonce: annonceTriage2 }), triage.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucunTriage) : /* @__PURE__ */ h("ul", { className: "acp-entrees acp-entrees--une" }, triage.map((c, rang) => /* @__PURE__ */ h(
      Triage,
      {
        key: chaine2(c.carte) ?? String(rang),
        carte: c,
        cible: estCarte(c),
        naviguer: props.naviguer,
        apres: props.apres,
        annoncer: fixerAnnonceTriage,
        traitee
      }
    )))), /* @__PURE__ */ h(Carte, { titre: T.projets.revuesTitre, id: "acp-questions-revues" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.revuesIntro), /* @__PURE__ */ h(AnnonceSection, { annonce: annonceRevue }), revues.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucuneRevue) : /* @__PURE__ */ h("ul", { className: "acp-entrees acp-entrees--une" }, revues.map((r, rang) => /* @__PURE__ */ h(
      Revue,
      {
        key: chaine2(r.carte) ?? String(rang),
        revue: r,
        cible: estCarte(r),
        naviguer: props.naviguer,
        apres: props.apres,
        annoncer: fixerAnnonceRevue,
        traitee
      }
    )))), /* @__PURE__ */ h(Carte, { titre: T.projets.bloqueesTitre, id: "acp-questions-bloquees" }, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.bloqueesIntro), /* @__PURE__ */ h(AnnonceSection, { annonce: annonceRelance }), bloquees.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.aucuneBloquee) : /* @__PURE__ */ h("ul", { className: "acp-entrees" }, bloquees.map((c, rang) => /* @__PURE__ */ h(
      Arretee,
      {
        key: chaine2(c.carte) ?? String(rang),
        carte: c,
        cible: estCarte(c),
        naviguer: props.naviguer,
        apres: props.apres,
        annoncer: fixerAnnonceRelance,
        traitee
      }
    )))), /* @__PURE__ */ h(Discussions, { lecture: props.discussions, serveur: donnees.discussions }), illisibles.length > 0 ? /* @__PURE__ */ h(Carte, { titre: T.projets.tableauxIllisibles, id: "acp-questions-illisibles" }, /* @__PURE__ */ h("ul", { className: "acp-noms" }, illisibles.map((t) => /* @__PURE__ */ h("li", { key: t }, /* @__PURE__ */ h(Donnee, { valeur: t, mono: true }))))) : null);
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
    const liste = useDonnees(lireProjets, jeton, ["projets", "questions", "poste", "notifications", "pause"]);
    const file = useDonnees(lireQuestions, jeton, ["questions", "projets", "discussions"]);
    const discussions = useDonnees(lireDiscussionsEnAttente, jeton, ["discussions"]);
    const racine = useRef(null);
    const naviguer = (suivante) => {
      fixerVue(suivante);
      pousserAdresse(suivante);
      rafraichir();
      try {
        racine.current?.scrollIntoView?.({ block: "start" });
      } catch {
      }
    };
    useEffect(() => {
      const surRetour = () => {
        fixerVue(vueDepuisAdresse(window.location.search));
        fixerJeton((j) => j + 1);
      };
      window.addEventListener("popstate", surRetour);
      return () => window.removeEventListener("popstate", surRetour);
    }, []);
    const donnees = liste.valeur;
    const compte = aTraiter(file.valeur, discussions.valeur);
    const pause = donnees?.pause_generale && typeof donnees.pause_generale === "object" ? donnees.pause_generale : null;
    return /* @__PURE__ */ h("div", { className: "acp-page", "data-acp-racine": "projets", ref: racine }, /* @__PURE__ */ h("div", { className: "acp-entete" }, /* @__PURE__ */ h("h1", { className: "acp-titre" }, T.projets.titre), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.projets.intro)), /* @__PURE__ */ h(Navigation, { vue, naviguer, questions: compte ? compte.total : null }), pause ? /* @__PURE__ */ h(BandeauPause, { pause, apres: rafraichir }) : null, donnees === null && liste.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : null, donnees === null && liste.erreur !== null ? /* @__PURE__ */ h(BlocErreur, { erreur: liste.erreur, message: T.projets.indisponible }) : null, donnees !== null && liste.erreur !== null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.projets.actualisationImpossible) : null, vue.genre === "liste" && donnees !== null ? /* @__PURE__ */ h(ListeProjets, { donnees, naviguer, apres: rafraichir }) : null, vue.genre === "nouveau" ? /* @__PURE__ */ h(NouveauProjet, { naviguer, apres: rafraichir }) : null, vue.genre === "detail" ? /* @__PURE__ */ h(DetailProjet, { key: vue.id, id: vue.id, jeton, liste: donnees, naviguer, apres: rafraichir }) : null, vue.genre === "questions" ? /* @__PURE__ */ h(
      Questions,
      {
        lecture: file,
        discussions,
        cible: { q: vue.q, carte: vue.carte },
        naviguer,
        apres: rafraichir
      }
    ) : null, /* @__PURE__ */ h(EtatActualisation, null));
  }

  // src/projets/index.ts
  installer({ nom: "acp-projets", page: Projets });
})();
