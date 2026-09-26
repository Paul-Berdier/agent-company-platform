"""Tous les textes français du noyau d'acp-poste : refus, corps de cartes, notifications.

Un refus porte un CODE stable (lu par l'interface et les tests) et un message français exact.
Aucun texte n'invente une donnée : ce qui manque se dit « Inconnu », « Non configuré », « Non
observé ».
"""

from __future__ import annotations

from typing import Iterable

PREFIXE_REFUS = "Refusé par ACP : "


class RefusACP(Exception):
    """Refus explicite, en français, avec un code stable. Rien n'a été écrit quand il est levé,
    sauf mention contraire dans le message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def refus(code: str, texte: str) -> RefusACP:
    """Refus dont le message commence par « Refusé par ACP : »."""
    return RefusACP(code, PREFIXE_REFUS + texte)


def liste(noms: Iterable[str]) -> str:
    valeurs = [str(n) for n in noms]
    return ", ".join(valeurs) if valeurs else "aucun"


def cartes(n: int, participe: str = "") -> str:
    """« 0 carte », « 1 carte faite », « 4 cartes faites » : accord français (singulier sous 2)."""
    pluriel = abs(int(n)) >= 2
    texte = f"{n} carte{'s' if pluriel else ''}"
    return f"{texte} {participe}{'s' if pluriel else ''}" if participe else texte


# ------------------------------------------------------------------ projet_lancer (§ 8.1)
CONTEXTE_LANCER = "projet_lancer ne s'appelle que depuis la discussion, jamais depuis une carte."
PAUSE_GENERALE_LANCER = ("Hermes est en pause générale ; reprenez-la depuis la page Projets avant de lancer "
                         "un projet.")
TITRE = "le titre doit compter de 1 à 120 caractères."
OBJECTIF = "l'objectif doit compter de 1 à 4000 caractères."
PROFIL = "type de projet « {x} » inconnu (base, web, recherche ou donnees)."
REPONSES = "politique de réponse « {x} » inconnue (hermes_d_abord ou proprietaire)."
AUCUN_INVENTAIRE = ("aucun dépôt autorisé n'est connu : le poste n'a encore publié aucun inventaire. Lancez le "
                    "projet sans dépôt, ou enrôlez le poste depuis la page Poste.")
DEPOT_INCONNU = "le dépôt « {x} » ne figure pas parmi les dépôts autorisés du poste ({liste})."
EXPLORATION = "aucun exécutant disponible pour l'exploration : {raison}"
EXPLORATION_SANS_DEPOT = "une exploration n'a de sens que sur un dépôt ; ce projet n'en a pas."
PROJETS_ACTIFS = "{n} projets sont déjà en cours (plafond {n}) ; terminez-en un ou mettez-le en pause."
PROJETS_ACTIFS_REPRISE = ("{n} projets sont déjà en cours (plafond {n}) ; terminez-en un ou mettez-en un en pause "
                          "avant de reprendre « {titre} ».")
LANCEMENTS_JOUR = ("{n} projets ont déjà été lancés depuis la discussion aujourd'hui (plafond) ; lancez celui-ci "
                   "depuis la page Projets.")
SECRET_OBJECTIF = "l'objectif contient ce qui ressemble à un secret ({motif}) ; retirez-le."
SECRET_TITRE = "le titre contient ce qui ressemble à un secret ({motif}) ; retirez-le."
ARGUMENTS = "arguments invalides pour {outil} : {detail}."

DESCRIPTION_TABLEAU = "Projet ACP — les cartes sont créées par acp-poste ; n'en créez pas à la main."

# ------------------------------------------------------------------ projet_planifier (§ 8.2)
CONTEXTE_PLANIFIER = ("projet_planifier ne s'appelle que depuis la carte de planification ou de synthèse d'un "
                      "projet ACP.")
CARTE_NON_COURANTE = "cette carte n'est pas la planification ou la synthèse en cours du projet « {titre} »."
DEJA_PLANIFIE_AUTREMENT = ("le tour {r} est déjà planifié par cette carte avec un autre plan ; terminez-la par "
                           "kanban_complete.")
PLAFOND_TOURS = ("plafond de {n} tours atteint pour le projet « {titre} » ; une carte de triage vous est "
                 "adressée.")
PLAFOND_CARTES = ("ce plan créerait {k} cartes, et le projet en compte déjà {m} sur {n} (plafond). Réduisez le "
                  "plan.")
PLAFOND_CARTES_ATTEINT = ("le projet « {titre} » compte déjà {m} cartes sur {n} (plafond) : aucun plan ne tient plus "
                          "(une étape et sa synthèse en demandent deux) ; une carte de triage vous est adressée.")
CONTEXTE_PLANIFIER_TRIAGE = ("cette carte de triage n'a pas été prolongée ou relancée par le propriétaire : "
                             "projet_planifier n'y est pas admis.")
PLAN_INVALIDE = "{detail}"
CLASSE_VOIE = "la classe « {c} » n'admet pas la voie « {v} » (voies admises : {admises})."
INTEGRATION_P6 = "la classe « integration » (fusion locale des branches) est prévue à l'étape P6."
SANS_DEPOT = ("le projet « {titre} » n'a pas de dépôt ; l'étape « {ref} » exige le poste et un dépôt "
              "autorisé.")
MODELE_ABSENT = "le modèle « {m} » ne figure pas dans le relevé de la voie {v} (relevé du {date})."
MODELE_HERMES_ABSENT = ("le modèle « {m} » ne figure pas dans le dernier relevé poste-codex ({date}) : Hermes "
                        "garde le modèle de son profil.")
EFFORT_NON_PRIS = "l'effort « {e} » n'est pas pris en charge par « {m} » (efforts relevés : {efforts})."
EFFORT_INTERDIT = "l'effort « {e} » est interdit par défaut ; seul le propriétaire peut le lever (page Routage)."
PALIER_INTERDIT = "le palier « {p} » est interdit par défaut (dépense hors enveloppe)."
AUCUN_MODELE = "Aucun modèle disponible pour la classe « {c} » : {raison}."
RAISON_AUCUN_RELEVE = "catalogue du poste inconnu (aucun relevé)"
RAISON_TABLE = "table de routage non validée et aucun choix explicite"
RAISON_QUOTA = "quota à {x} %"
RELECTURE_IMPOSSIBLE = "la relecture croisée de l'étape « {ref} » exige l'autre exécutant : {raison}."
SECRET_CONSIGNE = "la consigne de l'étape « {ref} » contient ce qui ressemble à un secret ({motif})."
SECRET_TEXTE = "le texte contient ce qui ressemble à un secret ({motif})."
ECHEC_CREATION = "Échec d'ACP : aucune carte n'a été créée ({type}) ; le plan peut être rappelé tel quel."
PROJET_INTROUVABLE = "le tableau « {t} » n'appartient à aucun projet ACP."

# ------------------------------------------------------------------ autres outils (§ 8.3 à 8.8)
ETAT_AUTRE_PROJET = "une carte ne lit que l'état de son propre projet."
CARTE_DU_PROJET_INCONNUE = "la carte « {carte} » n'appartient pas au projet « {titre} »."
PROJET_INCONNU = "projet « {x} » inconnu."
CONTEXTE_QUESTION = "{outil} ne s'appelle que depuis la carte « répondre » de cette question."
QUESTION_FERMEE = "la question {q} n'est plus ouverte ({etat})."
CONTEXTE_SURCHARGER = "routage_surcharger ne s'appelle que depuis la discussion."
SURCHARGE_GLOBALE = "une surcharge globale se fait depuis la page Routage."
SURCHARGE_CARTE = ("une carte existante garde son exécutant et son modèle : la surcharge d'une carte est prévue à "
                   "l'étape P6 ; surchargez le projet (portée « projet »), ce qui vaut pour ses prochaines cartes.")
ECHEC_OUTIL = "Échec d'ACP : {action} n'a pas abouti ({type}) ; rien n'a été modifié."
ECHEC_OUTIL_PARTIEL = "Échec d'ACP : {action} n'a pas abouti ({type}) ; état partiel : {detail}."
ECHEC_OUTIL_INCERTAIN = ("Échec d'ACP : {action} n'a pas abouti ({type}) ; l'état n'est pas connu avec "
                         "certitude : consultez projet_etat avant de réessayer.")

POSTE_JAMAIS_VU = "Le poste n'a jamais été vu : enrôlez-le depuis la page Poste."
POSTE_JAMAIS_VU_DEPUIS = "Poste confirmé mais jamais vu depuis : démarrez son service (tâche planifiée)."
CATALOGUE_INCONNU = ("Catalogue du poste inconnu : aucun relevé (le poste publie son inventaire une fois enrôlé et "
                     "confirmé).")
MODELE_DU_PROFIL = "modèle par défaut du profil"
NON_OBSERVE = "Non observé"
INCONNU = "Inconnu"
QUOTA_INCONNU = "quota inconnu"

# ------------------------------------------------------------------ questions, pause, étrangères
RAISON_PAUSE_PROJET = "Pause du projet (ACP)"
RAISON_QUESTION = "Question ouverte (ACP) : {q}"
PROJET_DEJA_EN_PAUSE = "le projet « {titre} » est déjà en pause."
PROJET_PAS_EN_PAUSE = "le projet « {titre} » n'est pas en pause."
PROJET_FINI = "le projet « {titre} » est {etat} : aucune action possible."
QUESTION_INCONNUE = "question « {q} » inconnue."
QUESTION_CARTE = "la carte {carte} n'est pas une carte du poste émise par le greffon pour ce projet."
QUESTION_CARTE_ETAT = "la carte {carte} n'est pas en cours ({statut}) : une question se pose pendant l'exécution."
TRIAGE_INCONNU = "la carte {carte} du tableau « {t} » n'est pas en triage."
RAISON_ETRANGERE = ("Refusé par ACP : carte poste-* non émise par le greffon acp-poste ; seul le greffon crée les "
                    "cartes du poste.")
CORRECTIONS_PLAFOND = ("plafond de {n} corrections atteint pour l'étape « {ref} » ; une carte de triage vous est "
                       "adressée.")
CORRECTION_CARTE = "la carte {carte} n'est pas une relecture en cours d'un projet ACP."

TITRE_TRIAGE_PLAFOND = "Plafond atteint : {genre} — votre décision est attendue"
CORPS_TRIAGE_PLAFOND = (
    "Le projet « {titre} » a atteint son plafond de {genre} ({detail}).\n\n"
    "{prolonger}« Conclure » arrête le projet ici. Sans décision de votre part, le projet reste arrêté ici.")
# Ce que « Prolonger » fait, par genre de plafond (décision D41).
PROLONGER_PAR_GENRE = {
    "tours": ("« Prolonger » accorde un tour de plus (plafond de tours relevé de 1) et fait exécuter cette carte par "
              "Hermes avec votre consigne : il planifie ce tour par projet_planifier. "),
    "cartes": ("« Prolonger » relève le plafond de cartes de {n} et fait exécuter cette carte par Hermes avec votre "
               "consigne : il planifie la suite par projet_planifier. "),
    "corrections": "« Prolonger » n'est pas disponible avant l'étape P6 (corrections câblées). ",
}
TITRE_TRIAGE_SANS_PLAN = "Planification sans plan — votre décision est attendue"
CORPS_TRIAGE_SANS_PLAN = (
    "La planification du projet « {titre} » s'est terminée sans plan ({detail}).\n\n"
    "« Relancer la planification » fait exécuter cette carte par Hermes avec votre consigne : il planifie le "
    "tour 1 par projet_planifier. « Conclure » arrête le projet ici. Sans décision de votre part, le projet reste "
    "arrêté ici.")
DETAIL_SANS_PLAN = "carte {carte} finie sans appel réussi à projet_planifier"
PROLONGATION_P6 = ("prolonger le plafond de corrections est prévu à l'étape P6 (corrections câblées) ; concluez le "
                   "projet, ou attendez P6.")
TRIAGE_PROJET_EN_PAUSE = "le projet « {titre} » est en pause : reprenez-le avant de décider de cette carte."
TRIAGE_ACP_SEULEMENT = "la carte {carte} n'est pas une carte de décision émise par acp-poste : « Conclure » ne s'y applique pas."
CONCLURE_CARTES_OUVERTES = ("{n} autre(s) carte(s) du projet « {titre} » sont encore ouvertes : concluez quand elles "
                            "sont finies, ou mettez le projet en pause.")
MOTIF_SANS_SUITE = ("Hermes n'a ni répondu ni escaladé : sa carte « répondre » s'est terminée sans suite ({statut}) ; "
                    "votre réponse est attendue.")
TITRE_REPONDRE = "Répondre à la question {q}"
CORPS_REPONDRE = (
    "Une carte du poste pose une question dans le projet « {titre} ».\n\n"
    "## Question\n{texte}\n\n"
    "## Règles\n"
    "Répondez par question_repondre SEULEMENT si les décisions du projet ou son objectif couvrent la question, "
    "en citant le fondement ; sinon question_escalader avec un motif. Une question de périmètre, de dépense ou "
    "de push s'escalade toujours. Terminez ensuite par kanban_complete.")

# ------------------------------------------------------------------ corps des cartes (§ 6)
CONSIGNE_EXPLORATION = (
    "Exploration en LECTURE SEULE du dépôt « {depot} » pour le projet « {titre} ».\n\n"
    "Objectif du projet :\n{objectif}\n\n"
    "Rendez une « carte du dépôt » avec ces sections, dans cet ordre :\n"
    "## Structure\n## Fichiers clés\n## Commandes de vérification\n## Conventions\n## Risques\n\n"
    "Ne modifiez rien : ni fichier, ni branche, ni configuration (CLAUDE.md et AGENTS.md sont lus, jamais "
    "modifiés).")
SECTIONS_EXPLORATION = ("## Structure", "## Fichiers clés", "## Commandes de vérification", "## Conventions",
                        "## Risques")
CORPS_PLANIFICATION = (
    "Projet ACP « {titre} » — planification (tour 1)\n"
    "Type de projet : {profil} · Dépôt : {depot} · Réponses aux questions : {reponses}\n"
    "## Objectif\n{objectif}\n"
    "## Règles\n"
    "Appelez projet_planifier UNE fois avec les étapes du tour, puis terminez par kanban_complete avec un "
    "résumé. Le greffon crée lui-même les cartes, la relecture croisée et la synthèse ; ne créez jamais de "
    "carte autrement. Plafonds : {tours} tours, {cartes} cartes, {corrections} corrections par étape. Si aucun "
    "plan n'est possible, terminez par kanban_complete en disant pourquoi : une carte de décision est alors "
    "adressée au propriétaire.")
CORPS_SYNTHESE = (
    "Projet ACP « {titre} » — synthèse du tour {r}\n"
    "## Objectif\n{objectif}\n"
    "## Règles\n"
    "Lisez projet_etat et les résultats des cartes du tour (kanban_show). S'il reste un écart concret et que "
    "les plafonds le permettent, appelez projet_planifier pour le tour {suivant} ; sinon concluez. Terminez "
    "toujours par kanban_complete : ce qui est fait, vérifié, reste à faire. N'annoncez jamais un push ni une "
    "fusion.")
CORPS_CARTE_POSTE = (
    "Projet ACP « {titre} » — tour {r}, étape {ref} ({classe})\n"
    "Exécutant : {voie} · Modèle : {modele} · Effort : {effort} · Palier : {palier}\n"
    "Dépôt : {depot}\n"
    "## Consigne\n{consigne}\n"
    "## Décisions du projet\n{decisions}\n"
    "## Règles\n"
    "Carte émise par acp-poste : la demande enregistrée par le greffon fait foi, pas ce texte.")
CORPS_RELECTURE = (
    "Projet ACP « {titre} » — tour {r}, relecture croisée de l'étape {ref} ({classe})\n"
    "Exécutant : {voie} · Modèle : {modele} · Effort : {effort} · Palier : {palier}\n"
    "Dépôt : {depot}\n"
    "## Consigne\nRelisez le travail de la carte {relue} (voie {voie_relue}) contre sa consigne et les décisions "
    "du projet ; dites ce qui est juste, ce qui manque et ce qui doit être corrigé.\n"
    "## Consigne de l'étape\n{consigne}\n"
    "## Règles\n"
    "Carte émise par acp-poste : la demande enregistrée par le greffon fait foi, pas ce texte.")
CORPS_CARTE_HERMES = (
    "Projet ACP « {titre} » — tour {r}, étape {ref} ({classe}), exécutée par Hermes\n"
    "## Consigne\n{consigne}\n"
    "## Décisions du projet\n{decisions}\n"
    "## Règles\n"
    "Aucun outil d'exécution : recherche, lecture du web et rédaction seulement. Terminez par kanban_complete "
    "avec le résultat ; kanban_block seulement pour un manque réel, avec sa raison.")
CORPS_CORRECTION = (
    "Projet ACP « {titre} » — tour {r}, correction {n} de l'étape {ref} ({classe})\n"
    "Exécutant : {voie} · Modèle : {modele} · Effort : {effort} · Palier : {palier}\n"
    "Dépôt : {depot}\n"
    "## Consigne\n{consigne}\n"
    "## Règles\n"
    "Carte émise par acp-poste : la demande enregistrée par le greffon fait foi, pas ce texte.")

LIBELLES_ROLE = {
    "exploration": "Exploration", "planification": "Planification", "implementation": "Implémentation",
    "relecture": "Relecture", "correction": "Correction", "hermes": "Hermes", "synthese": "Synthèse",
    "repondre": "Répondre", "triage": "Triage",
}

# ------------------------------------------------------------------ notifications (§ 12.5)
NOTIF_QUESTION = "ACP — Projet « {titre} » : une question attend votre réponse. {lien}"
NOTIF_BLOQUEE = "ACP — Projet « {titre} » : la carte « {carte} » est bloquée. {lien}"
NOTIF_BLOQUEE_HORS_PROJET = "ACP — Tableau « {tableau} » : la carte « {carte} » est bloquée. {lien}"
NOTIF_TRIAGE = "ACP — Projet « {titre} » : la carte « {carte} » attend votre décision (triage). {lien}"
NOTIF_ABANDON = "ACP — Projet « {titre} » : la carte « {carte} » a été abandonnée après plusieurs échecs. {lien}"
NOTIF_TERMINE = "ACP — Projet « {titre} » terminé : {cartes}. {lien}"
NOTIF_HORS_LIGNE = "ACP — Poste hors ligne depuis {heure} (Europe/Paris), {cartes} en attente. {lien}"
NOTIF_PLAFOND = "ACP — Projet « {titre} » : plafond de {genre} atteint, votre décision est attendue. {lien}"
NOTIF_SANS_PLAN = ("ACP — Projet « {titre} » : la planification s'est terminée sans plan, votre décision est "
                   "attendue. {lien}")
NOTIF_TEST = "ACP — Notification de test envoyée depuis la page Projets. {lien}"
NOTIF_CROCHETS = "ACP — Crochets shell détectés : pause générale engagée. {lien}"
RAISON_PAUSE_CROCHETS = "ACP : crochets shell détectés en cours de route"
RAISON_PAUSE_PROPRIETAIRE = "ACP : pause du propriétaire"
NOTIFICATIONS_NON_CONFIGUREES = "Notifications non configurées."
NOTIFICATIONS_ETAT_INCONNU = "État du canal de notification inconnu : la passerelle ne l'a pas encore publié."
REPRISE_CROCHETS = ("Refusé par ACP : des crochets shell sont toujours déclarés ({constats}) ; retirez-les du volume "
                    "avant de reprendre Hermes (la veille de l'émetteur rengagerait la pause).")

# ------------------------------------------------------------------ alertes de /v1/meta
ALERTE_EMETTEUR = "L'émetteur de notifications ne tourne plus dans la passerelle (dernière passe il y a {n} min)."
ALERTE_ECHECS = "{n} notifications en échec."
ALERTE_RELEVE_FACTICE = ("Un relevé factice est enregistré : le catalogue affiché n'est pas celui du poste.")
ALERTE_CROCHETS = "Crochets shell détectés en cours de route : pause générale engagée."
ALERTE_BASE = "Base du greffon acp-poste illisible ({type}) : projets, questions et notifications inconnus."

# ------------------------------------------------------------------ poste connecté (étape P5, cahier P5 § 4.4)
# Routes machine : refus du GREFFON (les 401 et 503 de la couture de Hermes sont en anglais, traduits par le poste).
MACHINE_NON_AUTHENTIFIE = "Jeton machine requis : cette route n'accepte que le poste ACP."
MAUVAIS_FOURNISSEUR = "Jeton refusé : ce chemin n'accepte que le jeton machine d'acp-poste."
CODE_ENROLEMENT_SEULEMENT = "Code d'enrôlement refusé ici : il ne sert qu'à la route d'enrôlement."
JETON_MACHINE_ICI = "Le jeton machine ne sert pas à l'enrôlement : générez un code depuis la page Poste."
CODE_REFUSE = ("Code d'enrôlement refusé : inconnu, expiré ou déjà utilisé. Générez-en un nouveau depuis la page "
               "Poste.")
POSTE_A_CONFIRMER = "Poste en attente de confirmation : confirmez l'empreinte {empreinte} sur la page Poste."
POSTE_DEJA_ENROLE = ("Un poste est déjà enrôlé (« {nom} ») : révoquez-le depuis la page Poste avant d'en enrôler un "
                     "autre.")
PROTOCOLE_INCOMPATIBLE = ("Protocole du poste « {p} » incompatible avec le greffon (acp-machine/1 attendu) : mettez "
                          "le poste à jour.")
TROP_VOLUMINEUX = "Requête du poste refusée : corps de plus de {n} Kio."
JSON_ATTENDU = "Requête du poste refusée : corps JSON attendu."
REQUETE_REFUSEE = "Requête du poste refusée par le contrat : {detail} Rien n'a été enregistré."
TROP_FREQUENT = "Inventaire trop fréquent : prochain envoi possible dans {n} s."
POSTE_REVOQUE = "Poste révoqué par le propriétaire le {date} : jeton local effacé."
POSTE_INCONNU_MACHINE = "Poste inconnu : jeton machine sans poste enregistré."
MOTIF_REMPLACE = "remplacé par un nouvel enrôlement"
ECHEC_MACHINE = "Échec d'ACP ({type}) : rien n'a été enregistré ; nouvel essai du poste plus tard."

# Routes du propriétaire (page Poste).
EMPREINTE_DIFFERENTE = ("L'empreinte saisie ne correspond pas à celle du poste enrôlé : n'activez pas ce poste ; "
                        "révoquez-le et recommencez.")
EMPREINTE_ILLISIBLE = "l'empreinte saisie doit compter 8 caractères hexadécimaux (forme 3F9A-0C1B)."
MACHINE_INCONNUE = "poste « {m} » inconnu."
MACHINE_PAS_A_CONFIRMER = "le poste « {nom} » n'attend pas de confirmation (état : {etat})."
MACHINE_DEJA_REVOQUEE = "le poste « {nom} » est déjà révoqué."
MOTIF_REVOCATION = "le motif de la révocation compte de 1 à 200 caractères."
AUCUN_POSTE_ACTIF = "aucun poste actif : enrôlez puis confirmez un poste depuis la page Poste."
ORDRE_RELEVE_EN_FILE = "Ordre de relevé mis en file : le poste le reçoit à sa prochaine attente."
ORDRE_RELEVE_HORS_LIGNE = ("Ordre de relevé mis en file : le poste est hors ligne ; il le recevra à son retour "
                           "(abandonné après {n} min).")

# États du poste (outil poste_etat, route /v1/poste).
POSTE_ETAT_A_CONFIRMER = "Poste enrôlé, en attente de la confirmation de son empreinte {empreinte} sur la page Poste."
POSTE_ETAT_REVOQUE = "Poste révoqué le {date} ({motif}) : enrôlez-en un nouveau depuis la page Poste."
POSTE_ETAT_POLITIQUE_INVALIDE = "Politique locale invalide : le poste reste joignable mais ne publie plus rien."

# Alertes de l'inventaire et de /v1/meta (bloc « machine »).
ALERTE_LISTE_SECOURS_PROBABLE = ("Relevé Codex identique au catalogue embarqué de Codex {v} : liste de secours "
                                 "probable.")
ALERTE_LISTE_SECOURS = "Relevé Codex sans compte ChatGPT : liste de secours (catalogue embarqué de Codex {v})."
ALERTE_VERSION_CLI = "{cli} {lue} n'est pas la version testée par le poste ({testee})."
ALERTE_BAC_A_SABLE = "Écriture Codex non admise (étape P6) : {raison}"
ALERTE_VOIE_EN_ECHEC = "Relevé {voie} en échec ({etat}) : {detail}"
ALERTE_FOURNISSEUR_ABSENT = "Le fournisseur de jeton machine n'est pas enregistré dans le tableau de bord."
ALERTE_CHEMINS_ABSENTS = "Chemins machine non enregistrés comme chemins à jeton : {chemins}."
ALERTE_DEUX_PROCESSUS = "Deux processus semblent utiliser le même jeton machine."
ALERTE_HOTE_ACP_POSTE = ("Le nom d'hôte du conteneur vaut « acp-poste » : un réclamant du poste serait pris pour un "
                         "worker local.")
ALERTE_AUCUNE_SESSION = "Aucun fournisseur de connexion interactive : personne ne peut se connecter."

# ------------------------------------------------------------------ routage de l'étape P5 (cahier P5 § 12.4)
VOIE_INDISPONIBLE = "la voie {v} est indisponible sur le poste depuis le {date} ({detail})."
VOIE_NON_CONNECTEE = "{cli} n'est pas connecté au compte de l'abonnement sur le poste ({etat})."
LISTE_DE_SECOURS = ("le relevé Codex du {date} est une liste de secours ({raison}), pas celle de votre compte. "
                    "Reconnectez Codex, ou acceptez ce relevé depuis la page Routage.")
RAISON_IDENTIQUE_EMBARQUE = "identique au catalogue embarqué de Codex {v}"
RAISON_SANS_COMPTE = "Codex sans compte ChatGPT : catalogue embarqué"
CLI_HORS_VERSION = "{cli} {lue} n'est pas la version testée par le poste ({testee})."
INTERDIT_PAR_LE_POSTE = ("le poste refuse {objet} (poste.toml, [politique] {cle}) ; seule une modification locale sur "
                         "le PC peut le lever.")
EFFORTS_INCONNUS = "efforts de « {alias} » inconnus pour Claude Code {version} (documentation relevée le {date})."
SUGGESTION_SANS_DEFAUT_CLAUDE = "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
SUGGESTION_SANS_DEFAUT = "Aucune suggestion : le relevé de {v} ne désigne pas de modèle par défaut."
SUGGESTION_DATEE = "Suggestion calculée depuis le relevé du {date}."
RELEVE_CHANGE = "Le relevé a changé depuis l'ouverture de la page : rechargez."
TABLE_REFUSEE = "Table de routage refusée : {n} entrée(s) refusée(s) ; rien n'a été enregistré."
TABLE_INVALIDE = "table de routage invalide : {detail}."
CLASSE_INCONNUE = "classe « {c} » inconnue."
CONFIRMATION_DEPENSE = "J'accepte une dépense hors enveloppe"
CONFIRMATION_REQUISE = ("{objet} : dépense hors enveloppe ; recopiez exactement la phrase « J'accepte une dépense hors "
                        "enveloppe » pour confirmer.")
POLITIQUE_INVALIDE = "politique invalide : {detail}."
MOTIF_REQUIS = "le motif compte de 1 à 200 caractères."
SURCHARGE_INCONNUE = "surcharge {i} inconnue ou déjà désactivée."
RELEVE_INCONNU = "relevé {i} inconnu."
RELEVE_NON_ACCEPTABLE = ("seul un relevé Codex identique au catalogue embarqué peut être accepté comme celui de votre "
                         "compte (celui-ci : {origine}).")
RELEVE_PLUS_LE_DERNIER = "le relevé {i} n'est plus le dernier de sa voie : rechargez la page Routage."
BADGES = {
    "releve_du_compte": "Relevé du compte", "liste_de_secours": "Liste de secours",
    "liste_de_secours_probable": "Liste de secours probable", "liste_acceptee": "Relevé accepté par vous",
    "alias_documentes": "Alias documentés", "perime": "Périmé", "inconnu": "Inconnu",
    "releve_factice": "Relevé factice", "indisponible": "Indisponible",
}

# ------------------------------------------------------------------ quotas (cahier P5 § 12.5)
QUOTAS_SOURCE_CLAUDE = "Ligne d'état de vos sessions Claude Code sur ce PC (même abonnement déclaré)"
QUOTAS_HERMES_MEME_ENVELOPPE = "Même enveloppe que Codex (déclaré dans poste.toml)"
