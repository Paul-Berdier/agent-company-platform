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
      posteNote: "Enr\xF4lement, \xE9tat, routage et quotas du poste\xA0: page Poste. L'ex\xE9cution de vos projets sur d\xE9p\xF4t arrive \xE0 l'\xE9tape P6.",
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
      aucunDepotConnu: "Aucun d\xE9p\xF4t connu\xA0: le poste n'a encore publi\xE9 aucun inventaire (page Poste).",
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
    poste: {
      titre: "Poste",
      intro: "Le poste Windows qui ex\xE9cutera vos projets sur d\xE9p\xF4t\xA0: enr\xF4lement, \xE9tat, routage des ex\xE9cutants et quotas relev\xE9s.",
      navigation: "Vues du poste",
      vueEtat: "Poste",
      vueRoutage: "Routage",
      vueQuotas: "Quotas",
      indisponible: "\xC9tat du poste indisponible.",
      actualisationImpossible: "Actualisation impossible\xA0: derni\xE8res valeurs lues affich\xE9es.",
      actualisation: "Actualis\xE9 toutes les 15 secondes tant que la page est visible.",
      envoi: "Envoi\u2026",
      etatTitre: "\xC9tat du poste",
      depuis: "depuis",
      vu: "Vu",
      revoqueLe: "R\xE9voqu\xE9 le",
      politiqueInvalide: "Politique locale invalide\xA0: le poste reste joignable mais ne publie plus rien.",
      pauseReclamations: "Pause g\xE9n\xE9rale\xA0: le poste n'ex\xE9cutera rien.",
      cartesEnAttente: "Cartes du poste en attente",
      enrolerTitre: "Enr\xF4ler un poste",
      enrolerAide: "G\xE9n\xE8re un code \xE0 usage unique, valable 10 minutes, \xE0 coller dans \xAB\xA0acp-poste enroler\xA0\xBB sur le poste, dans le compte du poste. Le jeton du poste n'est jamais affich\xE9.",
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
      empreinteAide: "Comparez-la \xE0 celle qu'affiche \xAB\xA0acp-poste enroler\xA0\xBB sur le poste, puis recopiez-la. Si elles diff\xE8rent, r\xE9voquez ce poste.",
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
      windows: "Windows",
      python: "Python",
      empreintePolitique: "Empreinte de poste.toml",
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
      ecritureAdmise: "\xC9criture admise (P6)",
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
        revoque: "R\xE9voqu\xE9"
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
      aucunReleve: "Aucun relev\xE9\xA0: le poste n'a encore rien publi\xE9.",
      aucunModele: "Aucun mod\xE8le dans ce relev\xE9.",
      modeles: "Mod\xE8les",
      efforts: "Efforts",
      effortsInconnus: "Efforts inconnus",
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
      suggestion: "Suggestion",
      appliquerSuggestion: "Appliquer la suggestion",
      ajouterEntree: "Ajouter une entr\xE9e",
      retirer: "Retirer",
      champVoie: "Ex\xE9cutant",
      champModele: "Mod\xE8le",
      champEffort: "Effort",
      champPalier: "Palier",
      modeleDuProfil: "Mod\xE8le par d\xE9faut du profil",
      modeleParDefaut: "Mod\xE8le par d\xE9faut du relev\xE9",
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
  function OuiNon(props) {
    if (typeof props.valeur !== "boolean") return /* @__PURE__ */ h(Donnee, { valeur: null });
    return /* @__PURE__ */ h("span", null, props.valeur ? T.commun.oui : T.commun.non);
  }
  function Bandeau(props) {
    const etat = props.donnees.poste;
    const machine = props.donnees.machine?.machine;
    return /* @__PURE__ */ h(Carte, { titre: T.poste.etatTitre, id: "acp-poste-etat" }, /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleEtatDuPoste(etat?.etat), brut: etat?.etat }), etat?.etat === "a_confirmer" ? /* @__PURE__ */ h(Donnee, { valeur: machine?.empreinte, mono: true }) : null, etat?.etat === "en_ligne" ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.vu), " ", /* @__PURE__ */ h(Horodatage, { valeur: etat.derniere_vue, relative: true })) : null, etat?.etat === "hors_ligne" && etat.hors_ligne_depuis ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.depuis), " ", /* @__PURE__ */ h(Horodatage, { valeur: etat.hors_ligne_depuis })) : null, etat?.etat === "revoque" ? /* @__PURE__ */ h("span", null, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.revoqueLe), " ", /* @__PURE__ */ h(Horodatage, { valeur: machine?.revoque_le })) : null), etat?.message ? /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: etat.message })) : null, machine && machine.politique_valide === false ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.poste.politiqueInvalide) : null, etat?.pause_reclamations ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte" }, T.poste.pauseReclamations) : null, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.cartesEnAttente }, /* @__PURE__ */ h(Donnee, { valeur: typeof etat?.cartes_en_attente === "number" ? etat.cartes_en_attente : null }))));
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
    return /* @__PURE__ */ h("div", { className: "acp-grille" }, /* @__PURE__ */ h(Carte, { titre: T.poste.inventaireTitre, id: "acp-poste-inventaire" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.recuLe }, /* @__PURE__ */ h(Horodatage, { valeur: inventaire.recu_le })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.releveLe }, /* @__PURE__ */ h(Horodatage, { valeur: inventaire.releve_le })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.versionPoste }, /* @__PURE__ */ h(Donnee, { valeur: c.version_poste, mono: true })))), /* @__PURE__ */ h(Carte, { titre: T.poste.compteTitre, id: "acp-poste-compte" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.compte }, c.poste?.compte === "dedie" ? /* @__PURE__ */ h("span", null, T.poste.compteDedie) : c.poste?.compte === "proprietaire" ? /* @__PURE__ */ h("span", null, T.poste.compteProprietaire) : /* @__PURE__ */ h(Donnee, { valeur: c.poste?.compte })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.windows }, /* @__PURE__ */ h(Donnee, { valeur: c.poste?.windows, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.python }, /* @__PURE__ */ h(Donnee, { valeur: c.poste?.python, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.empreintePolitique }, /* @__PURE__ */ h(Donnee, { valeur: c.poste?.politique_empreinte, mono: true })))), /* @__PURE__ */ h(Carte, { titre: T.poste.versionsTitre, id: "acp-poste-versions" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, ["codex", "claude"].map((cle) => /* @__PURE__ */ h(Ligne, { key: cle, libelle: cle === "codex" ? T.poste.codex : T.poste.claude }, /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.lue), " ", /* @__PURE__ */ h(Donnee, { valeur: versions[cle]?.lue, mono: true }), /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.testee), " ", /* @__PURE__ */ h(Donnee, { valeur: versions[cle]?.testee, mono: true }), /* @__PURE__ */ h("span", { className: "acp-discret" }, T.poste.conformite), " ", /* @__PURE__ */ h(OuiNon, { valeur: versions[cle]?.conforme })))))), /* @__PURE__ */ h(Carte, { titre: T.poste.bacTitre, id: "acp-poste-bac" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.readiness }, /* @__PURE__ */ h(Donnee, { valeur: bac.readiness, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.modeLu }, /* @__PURE__ */ h(Donnee, { valeur: bac.mode_lu, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.origineMode }, /* @__PURE__ */ h(Donnee, { valeur: bac.origine_mode, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.palierLu }, /* @__PURE__ */ h(Donnee, { valeur: bac.palier_lu, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.stockage }, /* @__PURE__ */ h(Donnee, { valeur: bac.stockage_identifiants_lu, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.ecritureAdmise }, /* @__PURE__ */ h(OuiNon, { valeur: bac.ecriture_admise })), bac.raison ? /* @__PURE__ */ h(Ligne, { libelle: T.poste.raison }, /* @__PURE__ */ h(Donnee, { valeur: bac.raison })) : null)), /* @__PURE__ */ h(Carte, { titre: T.poste.connexionsTitre, id: "acp-poste-connexions" }, /* @__PURE__ */ h("dl", { className: "acp-liste" }, /* @__PURE__ */ h(Ligne, { libelle: T.poste.codex }, /* @__PURE__ */ h(Etiquette, { libelle: libelleConnexionCodex(c.connexions?.codex), brut: c.connexions?.codex })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.offre }, /* @__PURE__ */ h(Donnee, { valeur: c.connexions?.plan_codex, mono: true })), /* @__PURE__ */ h(Ligne, { libelle: T.poste.claude }, /* @__PURE__ */ h(Etiquette, { libelle: libelleConnexionClaude(c.connexions?.claude), brut: c.connexions?.claude })))), /* @__PURE__ */ h(Carte, { titre: T.poste.depotsTitre, id: "acp-poste-depots" }, depots.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucunDepot) : /* @__PURE__ */ h("ul", { className: "acp-liste" }, depots.map((d, i) => /* @__PURE__ */ h("li", { key: `${d.alias ?? i}` }, /* @__PURE__ */ h(Donnee, { valeur: d.alias, mono: true }))))));
  }
  function EtatPoste(props) {
    const lecture = useSondage(lirePostePage, props.jeton);
    const donnees = lecture.valeur;
    if (donnees === null) {
      return lecture.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : /* @__PURE__ */ h(BlocErreur, { erreur: lecture.erreur, message: T.poste.indisponible });
    }
    const etat = donnees.poste?.etat;
    const machine = donnees.machine?.machine ?? null;
    const alertes = Array.isArray(donnees.alertes) ? donnees.alertes : [];
    const ordres = Array.isArray(donnees.ordres) ? donnees.ordres : [];
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, lecture.erreur !== null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.poste.actualisationImpossible) : null, /* @__PURE__ */ h(Bandeau, { donnees }), etat === "non_configure" || etat === "revoque" || etat === "a_confirmer" ? /* @__PURE__ */ h(Carte, { titre: T.poste.enrolerTitre, id: "acp-poste-enroler" }, /* @__PURE__ */ h(Enrolement, { apres: props.apres })) : null, etat === "a_confirmer" && machine ? /* @__PURE__ */ h(Confirmation, { machine, apres: props.apres }) : null, machine && machine.etat !== "revoque" ? /* @__PURE__ */ h(Machine, { machine }) : null, machine && machine.etat === "actif" ? /* @__PURE__ */ h(Releve, { apres: props.apres }) : null, alertes.length > 0 ? /* @__PURE__ */ h(Carte, { titre: T.poste.alertesTitre, id: "acp-poste-alertes" }, /* @__PURE__ */ h("ul", { className: "acp-liste" }, alertes.map((a, i) => /* @__PURE__ */ h("li", { key: i }, /* @__PURE__ */ h(Donnee, { valeur: a }))))) : null, machine && machine.etat === "actif" ? /* @__PURE__ */ h(Carte, { titre: T.poste.ordresTitre, id: "acp-poste-ordres" }, ordres.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.aucunOrdre) : /* @__PURE__ */ h("ul", { className: "acp-liste" }, ordres.map((o) => /* @__PURE__ */ h("li", { key: o.id, className: "acp-etat" }, /* @__PURE__ */ h(Donnee, { valeur: libelleGenreOrdre(o.genre) ?? o.genre }), /* @__PURE__ */ h(Horodatage, { valeur: o.cree_le, relative: true }), /* @__PURE__ */ h("span", { className: "acp-discret" }, o.livre ? T.poste.livre : T.poste.nonLivre))))) : null, /* @__PURE__ */ h(Inventaire, { donnees }), machine && machine.etat !== "revoque" ? /* @__PURE__ */ h(Revocation, { machine, apres: props.apres }) : null);
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
    const lecture = useSondage(lireQuotas, props.jeton);
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
      props.voies.map((v) => /* @__PURE__ */ h("option", { key: v, value: v }, libelleVoie(v) ?? v))
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: `${id}-modele` }, T.poste.champModele), /* @__PURE__ */ h(
      "select",
      {
        id: `${id}-modele`,
        value: entree.modele ?? "",
        onChange: (e) => props.changer({ ...entree, modele: e.currentTarget.value || null, effort: null })
      },
      /* @__PURE__ */ h("option", { value: "" }, entree.voie === "hermes" ? T.poste.modeleDuProfil : T.poste.modeleParDefaut),
      modeles.map((m) => /* @__PURE__ */ h("option", { key: m.id, value: m.id }, m.id))
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: `${id}-effort` }, T.poste.champEffort), /* @__PURE__ */ h(
      "select",
      {
        id: `${id}-effort`,
        value: entree.effort ?? "",
        onChange: (e) => props.changer({ ...entree, effort: e.currentTarget.value || null })
      },
      /* @__PURE__ */ h("option", { value: "" }, T.poste.effortParDefaut),
      efforts.map((effort) => /* @__PURE__ */ h("option", { key: effort, value: effort }, effort))
    )), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: `${id}-palier` }, T.poste.champPalier), /* @__PURE__ */ h(
      "select",
      {
        id: `${id}-palier`,
        value: entree.palier ?? "",
        onChange: (e) => props.changer({ ...entree, palier: e.currentTarget.value || null })
      },
      /* @__PURE__ */ h("option", { value: "" }, T.poste.palierStandard),
      contexte.paliers.filter((p) => p !== "default").map((p) => /* @__PURE__ */ h("option", { key: p, value: p }, p))
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
    ) : null), suggestion.libelle ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.poste.suggestion), " ", /* @__PURE__ */ h(Donnee, { valeur: suggestion.libelle })) : null, (suggestion.remarques ?? []).map((r, i) => /* @__PURE__ */ h("p", { key: i, className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: r }))));
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
    ))))), /* @__PURE__ */ h(RetourEnvoi, { etat: desactivation.etat, reussite: T.poste.surchargeDesactivee }), /* @__PURE__ */ h("form", { className: "acp-formulaire", onSubmit: envoyer }, /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-classe" }, T.poste.classe), /* @__PURE__ */ h("select", { id: "acp-surcharge-classe", value: classe, onChange: (e) => fixerClasse(e.currentTarget.value) }, classes.map((c) => /* @__PURE__ */ h("option", { key: c, value: c }, libelleClasse(c) ?? c)))), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-voie" }, T.poste.champVoie), /* @__PURE__ */ h("select", { id: "acp-surcharge-voie", value: voieChoisie, onChange: (e) => fixerVoie(e.currentTarget.value) }, voies.map((v) => /* @__PURE__ */ h("option", { key: v, value: v }, libelleVoie(v) ?? v)))), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-modele" }, T.poste.champModele), /* @__PURE__ */ h("input", { id: "acp-surcharge-modele", value: modele, onChange: (e) => fixerModele(e.currentTarget.value) })), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-effort" }, T.poste.champEffort), /* @__PURE__ */ h("input", { id: "acp-surcharge-effort", value: effort, onChange: (e) => fixerEffort(e.currentTarget.value) })), /* @__PURE__ */ h("div", { className: "acp-champ" }, /* @__PURE__ */ h("label", { htmlFor: "acp-surcharge-motif" }, T.poste.champMotif), /* @__PURE__ */ h("input", { id: "acp-surcharge-motif", value: motif, maxLength: 200, onChange: (e) => fixerMotif(e.currentTarget.value) })), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
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
    return /* @__PURE__ */ h("section", { className: "acp-carte", "aria-labelledby": id }, /* @__PURE__ */ h("h3", { className: "acp-carte__titre", id }, libelleVoie(props.voie) ?? props.voie), /* @__PURE__ */ h("p", { className: "acp-etat" }, /* @__PURE__ */ h(Etiquette, { libelle: libelleBadge(c?.badge), brut: c?.badge }), c?.releve_le ? /* @__PURE__ */ h(Horodatage, { valeur: c.releve_le }) : null, c?.version_cli ? /* @__PURE__ */ h(Donnee, { valeur: c.version_cli, mono: true }) : null), c?.detail ? /* @__PURE__ */ h("p", null, /* @__PURE__ */ h(Donnee, { valeur: c.detail })) : null, c?.documentation_lue_le ? /* @__PURE__ */ h("p", { className: "acp-discret" }, /* @__PURE__ */ h(Donnee, { valeur: c.documentation_lue_le, mono: true })) : null, modeles.length === 0 ? /* @__PURE__ */ h("p", { className: "acp-discret" }, !c || c.badge === "inconnu" ? T.poste.aucunReleve : T.poste.aucunModele) : /* @__PURE__ */ h("ul", { className: "acp-liste" }, modeles.map((m) => /* @__PURE__ */ h("li", { key: m.id, className: "acp-groupe" }, /* @__PURE__ */ h("span", { className: "acp-etat" }, /* @__PURE__ */ h(Donnee, { valeur: m.id, mono: true }), m.isDefault === true ? /* @__PURE__ */ h("span", { className: "acp-pastille acp-pastille--actif" }, T.poste.parDefaut) : null), /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.poste.efforts), " ", Array.isArray(m.supportedReasoningEfforts) ? /* @__PURE__ */ h(Donnee, { valeur: m.supportedReasoningEfforts.join(", ") || null, mono: true }) : /* @__PURE__ */ h("span", null, T.poste.effortsInconnus)), m.resolution_documentee ? /* @__PURE__ */ h("span", { className: "acp-discret" }, /* @__PURE__ */ h("span", null, T.poste.resolution), " ", /* @__PURE__ */ h(Donnee, { valeur: m.resolution_documentee, mono: true })) : null))), c?.badge === "liste_de_secours_probable" && typeof c.releve_id === "number" ? /* @__PURE__ */ h("div", { className: "acp-groupe" }, /* @__PURE__ */ h("p", { className: "acp-discret", id: `${id}-accepter` }, T.poste.accepterAide), /* @__PURE__ */ h("div", { className: "acp-actions" }, /* @__PURE__ */ h(
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
  function Routage(props) {
    const lecture = useSondage(lireRoutage, props.jeton);
    const vue = lecture.valeur;
    if (vue === null) {
      return lecture.erreur === null ? /* @__PURE__ */ h(EnChargement, null) : /* @__PURE__ */ h(BlocErreur, { erreur: lecture.erreur, message: T.poste.indisponible });
    }
    const voies = vue.voies ?? {};
    const cleTable = JSON.stringify(vue.releves ?? {});
    return /* @__PURE__ */ h("div", { className: "acp-sections" }, lecture.erreur !== null ? /* @__PURE__ */ h("p", { className: "acp-alerte-texte", role: "status" }, T.poste.actualisationImpossible) : null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.routageIntro), /* @__PURE__ */ h(Carte, { titre: T.poste.listesTitre, id: "acp-poste-listes" }, /* @__PURE__ */ h("div", { className: "acp-grille" }, ["poste-codex", "poste-claude"].map((voie) => /* @__PURE__ */ h(Liste, { key: voie, voie, catalogue: voies[voie], apres: props.apres })))), /* @__PURE__ */ h(Table, { key: cleTable, vue, apres: props.apres }), /* @__PURE__ */ h(PolitiqueHermes, { vue, apres: props.apres }), /* @__PURE__ */ h(PolitiqueDuPoste, { politique: vue.politique_poste }), /* @__PURE__ */ h(Surcharges, { vue, apres: props.apres }));
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
    return /* @__PURE__ */ h("div", { className: "acp-page", "data-acp-racine": "poste", ref: racine }, /* @__PURE__ */ h("div", { className: "acp-entete" }, /* @__PURE__ */ h("h1", { className: "acp-titre" }, T.poste.titre), /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.intro)), /* @__PURE__ */ h("nav", { className: "acp-onglets", "aria-label": T.poste.navigation }, VUES.map((v) => /* @__PURE__ */ h(Onglet, { key: v, vue: v, courante: vue, naviguer }))), vue === "etat" ? /* @__PURE__ */ h(EtatPoste, { jeton, apres: rafraichir }) : null, vue === "routage" ? /* @__PURE__ */ h(Routage, { jeton, apres: rafraichir }) : null, vue === "quotas" ? /* @__PURE__ */ h(Quotas, { jeton, apres: rafraichir }) : null, /* @__PURE__ */ h("p", { className: "acp-discret" }, T.poste.actualisation));
  }

  // src/poste/index.ts
  installer({ nom: "acp-poste-vues", page: Poste });
})();
