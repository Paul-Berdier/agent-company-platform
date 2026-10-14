"""État durable des connexions officielles ; défis temporaires uniquement en mémoire.

La table d’ordres existante réveille le relevé. Les opérations rattachées à cet ordre
ne transportent aucun jeton fournisseur ni code d’appareil dans SQLite.
"""
from __future__ import annotations

import threading
import json
from uuid import uuid4
from . import base, machines, ordres, distant
from .textes import refus
from acp_poste_contrat import comptes as C

ATTENTE_MAX = 900
PRESENCE_MAX = 45
_VERROU = threading.RLock()
_DEFIS = {}
MESSAGES = {
    "attente": "Demande enregistrée. En attente du serveur d’exécution.",
    "demarrage": "Le serveur démarre la connexion officielle Codex.",
    "code": "Ouvrez le lien officiel et saisissez ce code dans votre navigateur.",
    "verification": "Connexion terminée ; vérification du compte par Codex.",
    "connecte": "Compte ChatGPT reconnu par Codex. L’accès effectif aux modèles reste à vérifier par une tâche.",
    "annulation": "Annulation demandée au serveur.",
    "annulee": "Connexion annulée.",
    "expiree": "Le délai de connexion est dépassé. Vous pouvez recommencer.",
    "interrompue": "La connexion a été interrompue. Son état a été relu sans relancer l’authentification.",
    "indisponible": "Le moteur Codex est indisponible sur le serveur. Consultez ses diagnostics.",
    "occupe": "Le compte est utilisé par une tâche ou une sonde. Attendez sa fin avant de reconnecter.",
    "refuse": "Codex n’a pas confirmé un compte ChatGPT. Recommencez la procédure officielle.",
    "incompatible": "Le contrat de cette version de Codex est incompatible avec la connexion distante.",
}


def initialiser(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS comptes_executants (machine_id TEXT PRIMARY KEY REFERENCES machines(id), instance_id TEXT NOT NULL, derniere_vue INTEGER NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS comptes_operations (id TEXT PRIMARY KEY, cle TEXT NOT NULL UNIQUE, machine_id TEXT NOT NULL REFERENCES machines(id), ordre_id INTEGER REFERENCES ordres(id), etat TEXT NOT NULL, motif TEXT NOT NULL, auteur TEXT NOT NULL, cree_le INTEGER NOT NULL, actualise_le INTEGER NOT NULL, limite_attente_le INTEGER NOT NULL, instance_id TEXT, numero INTEGER NOT NULL DEFAULT 0, compte_connecte INTEGER)")


def _cle_defi(conn, identifiant):
    return (str(conn.execute("PRAGMA database_list").fetchone()[2]), identifiant)


def _ligne(conn, identifiant):
    ligne = conn.execute("SELECT * FROM comptes_operations WHERE id=?", (identifiant,)).fetchone()
    if ligne is None:
        raise refus("connexion_inconnue", "Cette demande de connexion est introuvable.")
    return dict(ligne)


def _expirer(conn):
    conn.execute("UPDATE comptes_operations SET etat='expiree',motif='expiree',actualise_le=? WHERE limite_attente_le<=? AND etat NOT IN ('connecte','annulee','expiree','interrompue','erreur')", (base.maintenant(), base.maintenant()))
    for cle, valeur in list(_DEFIS.items()):
        if valeur[0] <= base.maintenant():
            _DEFIS.pop(cle, None)


def _vue(conn, ligne):
    defi = _DEFIS.get(_cle_defi(conn, ligne["id"])) if ligne["etat"] == "code_disponible" else None
    message = MESSAGES[ligne["motif"]]
    if ligne["etat"] == "code_disponible" and defi is None:
        message = ("Le code temporaire est indisponible après un redémarrage du serveur. "
                   "Si vous avez déjà autorisé la connexion dans le navigateur, attendez sa vérification. "
                   "Sinon, annulez cette demande puis relancez la connexion.")
    return {"id": ligne["id"], "moteur": "codex", "etat": ligne["etat"], "cree_le": ligne["cree_le"],
            "actualise_le": ligne["actualise_le"], "limite_attente_le": ligne["limite_attente_le"],
            "verification_url": defi[1] if defi else None, "code_utilisateur": defi[2] if defi else None,
            "message": message, "compte_connecte": None if ligne["compte_connecte"] is None else bool(ligne["compte_connecte"]), "inference_verifiee": False}


def lire(conn, identifiant):
    C.identifiant(identifiant)
    with _VERROU:
        initialiser(conn)
        _expirer(conn)
        return _vue(conn, _ligne(conn, identifiant))


def _serveur(conn):
    actif = machines.machine_active(conn)
    raison = distant.raison_refus(conn, actif["id"] if actif else None)
    canal = conn.execute("SELECT * FROM comptes_executants WHERE machine_id=?", (actif["id"],)).fetchone() if actif else None
    if not raison and (canal is None or base.maintenant() - canal["derniere_vue"] > PRESENCE_MAX):
        raison = "Le service de connexion distante est indisponible. Mettez à jour ou redémarrez le serveur d’exécution."
    return actif, {"disponible": raison is None, "nom": actif["nom"] if actif else None, "raison": raison}


def _inventaire_compte(conn, machine_id, connexion):
    """Projection du dernier inventaire validé, sans assimiler catalogue et droit d’inférence."""
    from acp_poste_contrat.inventaire import valider_inventaire
    observation = {"etat": "inconnu", "recu_le": None, "connexion": "inconnu", "origine_modeles": None, "quotas": []}
    ligne = conn.execute("SELECT contenu,recu_le,releve_le FROM inventaires WHERE machine_id=? ORDER BY id DESC LIMIT 1", (machine_id,)).fetchone() if machine_id else None
    if ligne is None:
        return None, None, [], observation
    try:
        # recevoir_dans() stocke les relevés séparément : le document interne porte
        # leurs ID par voie et ses alertes, pas le corps InventairePoste reçu.
        contenu = json.loads(ligne["contenu"])
        if not isinstance(contenu, dict):
            raise ValueError("Inventaire stocké invalide")
        references = contenu.get("releves")
        if not isinstance(references, dict) or not 1 <= len(references) <= 2:
            raise ValueError("Références de relevés invalides")
        releves = []
        for voie, identifiant in references.items():
            if voie not in ("poste-codex", "poste-claude") or type(identifiant) is not int or identifiant <= 0:
                raise ValueError("Référence de relevé invalide")
            releve = conn.execute("SELECT contenu FROM releves WHERE id=? AND machine_id=? AND voie=?",
                                  (identifiant, machine_id, voie)).fetchone()
            if releve is None:
                raise ValueError("Relevé manquant ou étranger")
            donnees = json.loads(releve["contenu"])
            if not isinstance(donnees, dict) or donnees.get("voie") != voie:
                raise ValueError("Contenu de relevé incohérent")
            # Le greffon a calculé ce résumé au stockage ; InventairePoste exige
            # sa forme d'entrée null. La vue utilise les compteurs source validés.
            donnees["quotas"] = None
            releves.append(donnees)
        contenu["releves"] = releves
        contenu.pop("alertes", None)
        inventaire = valider_inventaire(contenu)
    except (ValueError, TypeError):
        return None, None, [], observation
    observation["recu_le"] = ligne["recu_le"]
    version = inventaire.versions.get("codex")
    version = version.lue if version else None
    limite = int(base.reglage(conn, "releve_perime_s") or 7200)
    instant = min(ligne["recu_le"], ligne["releve_le"])
    if base.maintenant() - instant > limite:
        observation["etat"] = "perime"
        return None, version, [], observation
    # Un relevé commencé avant une connexion ne prouve pas l’état après celle-ci.
    if connexion and instant < connexion["actualise_le"]:
        observation["etat"] = "actualisation_en_attente"
        return None, version, [], observation
    observation.update(etat="a_jour", connexion=inventaire.connexions.codex)
    compte = {"compte_chatgpt": True, "non_connecte": False, "cle_api": False, "autre": False}.get(inventaire.connexions.codex)
    releve = next((r for r in inventaire.releves if r.voie == "poste-codex"), None)
    modeles = []
    if releve is not None:
        observation["origine_modeles"] = releve.origine_liste
        observation["quotas"] = [q.model_dump(mode="json") for q in releve.compteurs]
        if compte is True and releve.origine_liste == "compte" and releve.etat == "ok":
            modeles = [m.model_dump(mode="json") for m in releve.modeles]
    return compte, version, modeles, observation


def etat(conn):
    with _VERROU:
        initialiser(conn)
        _expirer(conn)
        actif, serveur = _serveur(conn)
        ligne = conn.execute("SELECT * FROM comptes_operations WHERE machine_id=? ORDER BY cree_le DESC,rowid DESC LIMIT 1", (actif["id"],)).fetchone() if actif else None
        connexion = _vue(conn, dict(ligne)) if ligne else None
        compte, version, modeles, observation = _inventaire_compte(conn, actif["id"] if actif else None, connexion)
        recent = connexion and base.maintenant() - connexion["actualise_le"] <= int(base.reglage(conn, "releve_perime_s") or 7200)
        if compte is None and recent and observation["etat"] != "a_jour":
            compte = connexion["compte_connecte"]
            observation["etat"] = "actualisation_en_attente"
        statut = "inconnu"
        message = "État du compte inconnu. En attente d’un relevé du serveur."
        if not serveur["disponible"]:
            statut, message = "moteur_indisponible", serveur["raison"]
        elif connexion and connexion["etat"] not in C.TERMINAUX:
            statut, message = "connexion_en_attente", connexion["message"]
        elif compte is True:
            statut, message = "connecte", MESSAGES["connecte"]
        elif compte is False:
            statut, message = "non_configure", "Aucun compte ChatGPT reconnu sur le serveur. Utilisez la connexion officielle."
        elif connexion and connexion["etat"] in ("erreur", "interrompue"):
            statut, message = "erreur", connexion["message"]
        comptes = [{"moteur": "codex", "nom": "Codex", "implementation": "disponible", "etat": statut,
                    "version": version, "compte_connecte": compte, "inference_verifiee": False, "modeles": modeles,
                    "connexion": connexion, "observation": observation, "message": message}]
        for moteur, nom in (("claude_code", "Claude Code"), ("mistral_vibe", "Mistral Vibe")):
            comptes.append({"moteur": moteur, "nom": nom, "implementation": "non_implemente", "etat": "non_configure", "version": None,
                            "compte_connecte": None, "inference_verifiee": False, "modeles": [], "connexion": None,
                            "message": "Connexion graphique distante non implémentée dans cette première tranche."})
        return {"protocole": C.PROTOCOLE, "serveur": serveur, "comptes": comptes}


def creer(conn, cle, auteur):
    C.identifiant(cle)
    with _VERROU:
        initialiser(conn)
        with base.transaction(conn):
            _expirer(conn)
            existante = conn.execute("SELECT * FROM comptes_operations WHERE cle=?", (cle,)).fetchone()
            if existante:
                return _vue(conn, dict(existante))
            actif, serveur = _serveur(conn)
            if not serveur["disponible"]:
                raise refus("serveur_indisponible", serveur["raison"])
            existante = conn.execute("SELECT * FROM comptes_operations WHERE machine_id=? AND etat NOT IN ('connecte','annulee','expiree','interrompue','erreur') ORDER BY cree_le DESC LIMIT 1", (actif["id"],)).fetchone()
            if existante:
                raise refus("connexion_en_cours", "Une connexion est déjà en cours. Reprenez-la dans Comptes et modèles.")
            maintenant, identifiant = base.maintenant(), str(uuid4())
            ordre = ordres.creer_dans(conn, actif["id"], "releve", auteur)
            conn.execute("INSERT INTO comptes_operations (id,cle,machine_id,ordre_id,etat,motif,auteur,cree_le,actualise_le,limite_attente_le) VALUES (?,?,?,?,'en_attente','attente',?,?,?,?)", (identifiant,cle,actif["id"],ordre,auteur,maintenant,maintenant,maintenant+ATTENTE_MAX))
            base.journaliser(conn, auteur, "connexion_codex_demandee", cible=identifiant)
            return _vue(conn, _ligne(conn, identifiant))


def annuler(conn, identifiant, auteur):
    C.identifiant(identifiant)
    with _VERROU:
        initialiser(conn)
        with base.transaction(conn):
            _expirer(conn)
            ligne = _ligne(conn, identifiant)
            if ligne["etat"] not in C.TERMINAUX and ligne["etat"] != "annulation_demandee":
                etat = "annulee" if ligne["instance_id"] is None else "annulation_demandee"
                motif = "annulee" if etat == "annulee" else "annulation"
                conn.execute("UPDATE comptes_operations SET etat=?,motif=?,actualise_le=? WHERE id=?", (etat,motif,base.maintenant(),identifiant))
                _DEFIS.pop(_cle_defi(conn, identifiant), None)
                base.journaliser(conn, auteur, "connexion_codex_annulation", cible=identifiant)
            return _vue(conn, _ligne(conn, identifiant))


def echanger(conn, machine_id, requete: C.Echange):
    with _VERROU:
        initialiser(conn)
        with base.transaction(conn):
            raison = distant.raison_refus(conn, machine_id)
            if raison:
                raise refus("executant_distant_requis", raison)
            now = base.maintenant()
            connu = conn.execute("SELECT * FROM comptes_executants WHERE machine_id=?", (machine_id,)).fetchone()
            if connu and connu["instance_id"] != requete.instance_id and now - connu["derniere_vue"] <= PRESENCE_MAX:
                raise refus("instance_deja_active", "Une autre instance du serveur utilise déjà ce compte. Attendez sa fin.")
            conn.execute("INSERT INTO comptes_executants VALUES (?,?,?) ON CONFLICT(machine_id) DO UPDATE SET instance_id=excluded.instance_id,derniere_vue=excluded.derniere_vue", (machine_id,requete.instance_id,now))
            _expirer(conn)
            observation = requete.observation
            if observation:
                ligne = _ligne(conn, observation.operation_id)
                if ligne["machine_id"] != machine_id or ligne["instance_id"] != requete.instance_id:
                    raise refus("connexion_etrangere", "Cette connexion appartient à un autre exécutant ou à une ancienne instance.")
                if ligne["etat"] not in C.TERMINAUX and observation.numero >= ligne["numero"]:
                    if observation.numero == ligne["numero"] and ligne["etat"] != "annulation_demandee":
                        if (ligne["etat"], ligne["motif"], ligne["compte_connecte"]) != (observation.etat, observation.motif, observation.compte_connecte):
                            raise refus("observation_contradictoire", "Une observation déjà reçue ne peut pas changer.")
                    progression = {"demarrage": 0, "code_disponible": 1, "verification": 2}
                    if observation.etat in progression and ligne["etat"] in progression and progression[observation.etat] < progression[ligne["etat"]]:
                        raise refus("observation_obsolete", "L’état de connexion ne peut pas revenir en arrière.")
                    # Une annulation demandée ne se perd pas devant une observation en retard.
                    if ligne["etat"] != "annulation_demandee" or observation.etat in C.TERMINAUX:
                        conn.execute("UPDATE comptes_operations SET etat=?,motif=?,numero=?,compte_connecte=?,actualise_le=? WHERE id=?", (observation.etat,observation.motif,observation.numero,observation.compte_connecte,now,ligne["id"]))
                        if observation.etat == "code_disponible":
                            _DEFIS[_cle_defi(conn,ligne["id"])] = (ligne["limite_attente_le"],observation.verification_url,observation.code_utilisateur)
                        else:
                            _DEFIS.pop(_cle_defi(conn,ligne["id"]),None)
                        if observation.etat in C.TERMINAUX:
                            ordres.acquitter_dans(conn,machine_id,[ligne["ordre_id"]])
                            base.journaliser(conn,"executant", "connexion_codex_terminee",cible=ligne["id"],detail={"etat":observation.etat})
            ligne = conn.execute("SELECT * FROM comptes_operations WHERE machine_id=? AND etat NOT IN ('connecte','annulee','expiree','interrompue','erreur') ORDER BY cree_le LIMIT 1", (machine_id,)).fetchone()
            if ligne is None:
                return {"protocole":C.PROTOCOLE,"operation":None}
            ligne = dict(ligne)
            action = "attendre"
            if ligne["etat"] == "annulation_demandee":
                action = "annuler"
            if ligne["instance_id"] != requete.instance_id:
                if not requete.libre:
                    return {"protocole":C.PROTOCOLE,"operation":None}
                if ligne["etat"] == "annulation_demandee":
                    action = "annuler"
                    conn.execute("UPDATE comptes_operations SET instance_id=?,numero=0,actualise_le=? WHERE id=?", (requete.instance_id,now,ligne["id"]))
                else:
                    action = "demarrer" if ligne["instance_id"] is None and ligne["etat"] == "en_attente" else "reconcilier"
                    conn.execute("UPDATE comptes_operations SET instance_id=?,numero=0,etat='demarrage',motif='demarrage',actualise_le=? WHERE id=?", (requete.instance_id,now,ligne["id"]))
            return {"protocole":C.PROTOCOLE,"operation":{"id":ligne["id"],"action":action,"limite_attente_le":ligne["limite_attente_le"]}}
