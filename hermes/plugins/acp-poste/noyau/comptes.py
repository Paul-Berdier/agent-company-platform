"""Connexions officielles distantes : métadonnées durables, défis et codes uniquement en RAM."""
from __future__ import annotations

import threading
import hmac
import json
from uuid import uuid4
from . import base, machines, ordres, distant
from .textes import refus
from acp_poste_contrat import comptes as C

ATTENTE_MAX = 900
PRESENCE_MAX = 45
_VERROU = threading.RLock()
_DEFIS = {}
_CODES = {}
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
MESSAGES_CLAUDE = MESSAGES | {
    "demarrage": "Le serveur démarre la connexion officielle Claude Code.",
    "code": "Ouvrez le lien officiel, autorisez votre abonnement Claude puis collez ici le code de retour affiché.",
    "verification": "Code transmis ; vérification du compte par Claude Code.",
    "connecte": "Compte Claude reconnu sur le serveur. L’accès effectif aux modèles reste à vérifier par une tâche.",
    "indisponible": "Claude Code est indisponible sur le serveur. Consultez ses diagnostics.",
    "refuse": "Claude Code n’a pas confirmé le compte. Recommencez la procédure officielle.",
    "incompatible": "Le contrat de cette version de Claude Code est incompatible avec la connexion distante.",
}


def initialiser(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS comptes_executants (machine_id TEXT PRIMARY KEY REFERENCES machines(id), instance_id TEXT NOT NULL, derniere_vue INTEGER NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS comptes_operations (id TEXT PRIMARY KEY, cle TEXT NOT NULL UNIQUE, machine_id TEXT NOT NULL REFERENCES machines(id), ordre_id INTEGER REFERENCES ordres(id), etat TEXT NOT NULL, motif TEXT NOT NULL, auteur TEXT NOT NULL, cree_le INTEGER NOT NULL, actualise_le INTEGER NOT NULL, limite_attente_le INTEGER NOT NULL, instance_id TEXT, numero INTEGER NOT NULL DEFAULT 0, compte_connecte INTEGER)")
    # Migration additive : les opérations /1 sont toutes Codex, leurs clés et leur
    # historique restent intacts. Ni URL complète ni code ne sont jamais persistés.
    colonnes = {r[1] for r in conn.execute("PRAGMA table_info(comptes_operations)")}
    for nom, type_sql in (("moteur", "TEXT NOT NULL DEFAULT 'codex'"), ("defi_id", "TEXT"),
                          ("defi_type", "TEXT"), ("soumission_id", "TEXT"),
                          ("code_transmis", "INTEGER NOT NULL DEFAULT 0")):
        if nom not in colonnes:
            conn.execute(f"ALTER TABLE comptes_operations ADD COLUMN {nom} {type_sql}")


def _cle_defi(conn, identifiant):
    return (str(conn.execute("PRAGMA database_list").fetchone()[2]), identifiant)


def _cle_code(conn, ligne):
    return (*_cle_defi(conn, ligne["id"]), ligne["instance_id"], ligne["defi_id"])


def _purger(conn, identifiant):
    cle = _cle_defi(conn, identifiant)
    _DEFIS.pop(cle, None)
    for k in list(_CODES):
        if k[:2] == cle:
            _CODES.pop(k, None)


def _ligne(conn, identifiant):
    ligne = conn.execute("SELECT * FROM comptes_operations WHERE id=?", (identifiant,)).fetchone()
    if ligne is None:
        raise refus("connexion_inconnue", "Cette demande de connexion est introuvable.")
    return dict(ligne)


def _expirer(conn):
    maintenant = base.maintenant()
    conn.execute("UPDATE comptes_operations SET etat='expiree',motif='expiree',actualise_le=? WHERE limite_attente_le<=? AND etat NOT IN ('connecte','annulee','expiree','interrompue','erreur')", (maintenant, maintenant))
    for memoire in (_DEFIS, _CODES):
        for cle, valeur in list(memoire.items()):
            if valeur["limite"] <= maintenant:
                memoire.pop(cle, None)


def _reception(conn, ligne, defi_id=None, soumission_id=None):
    if (defi_id is None) != (soumission_id is None):
        raise ValueError("Une paire défi et soumission est requise.")
    if defi_id is None:
        defi_id, soumission_id = ligne["defi_id"], ligne["soumission_id"]
        if soumission_id is None:
            return None
    C.identifiant(defi_id)
    C.identifiant(soumission_id)
    etat = "non_recue"
    if (defi_id, soumission_id) == (ligne["defi_id"], ligne["soumission_id"]):
        if ligne["code_transmis"]:
            etat = "transmis"
        else:
            code = _CODES.get(_cle_code(conn, ligne))
            etat = "en_attente" if code and code["soumission_id"] == soumission_id else "perdu"
    return {"defi_id": defi_id, "soumission_id": soumission_id, "etat": etat}


def _vue(conn, ligne, defi_id=None, soumission_id=None):
    defi = _DEFIS.get(_cle_defi(conn, ligne["id"])) if ligne["etat"] == "code_disponible" else None
    message = (MESSAGES if ligne["moteur"] == "codex" else MESSAGES_CLAUDE)[ligne["motif"]]
    reception = _reception(conn, ligne, defi_id, soumission_id)
    if ligne["etat"] == "code_disponible" and defi is None:
        message = ("Le code temporaire est indisponible après un redémarrage du serveur. "
                   "Si vous avez déjà autorisé la connexion dans le navigateur, attendez sa vérification. "
                   "Sinon, annulez cette demande puis relancez la connexion.")
    if reception and reception["etat"] == "perdu":
        message = ("La remise du code n’est plus confirmable après une interruption. "
                   "Attendez la vérification du compte ; sinon annulez cette demande puis relancez la connexion.")
    elif reception and reception["etat"] == "en_attente":
        message = "Code reçu temporairement. En attente de sa transmission au CLI officiel du serveur."
    elif reception and reception["etat"] == "transmis" and ligne["etat"] not in C.TERMINAUX:
        message = "Code transmis au CLI officiel. En attente de sa vérification du compte."
    return {"id": ligne["id"], "moteur": ligne["moteur"], "etat": ligne["etat"], "cree_le": ligne["cree_le"],
            "actualise_le": ligne["actualise_le"], "limite_attente_le": ligne["limite_attente_le"],
            "defi_id": ligne["defi_id"] if defi else None, "defi_type": ligne["defi_type"] if defi else None,
            "verification_url": defi["url"] if defi else None, "code_utilisateur": defi["code"] if defi else None,
            "reception_code": reception, "message": message,
            "compte_connecte": None if ligne["compte_connecte"] is None else bool(ligne["compte_connecte"]),
            "inference_verifiee": False}


def lire(conn, identifiant, defi_id=None, soumission_id=None):
    C.identifiant(identifiant)
    with _VERROU:
        initialiser(conn)
        _expirer(conn)
        return _vue(conn, _ligne(conn, identifiant), defi_id, soumission_id)


def _serveur(conn):
    actif = machines.machine_active(conn)
    raison = distant.raison_refus(conn, actif["id"] if actif else None)
    canal = conn.execute("SELECT * FROM comptes_executants WHERE machine_id=?", (actif["id"],)).fetchone() if actif else None
    if not raison and (canal is None or base.maintenant() - canal["derniere_vue"] > PRESENCE_MAX):
        raison = "Le service de connexion distante est indisponible. Mettez à jour ou redémarrez le serveur d’exécution."
    return actif, {"disponible": raison is None, "nom": actif["nom"] if actif else None, "raison": raison}


def _inventaire_compte(conn, machine_id, connexion, moteur="codex"):
    """Projection du dernier inventaire validé, sans assimiler catalogue et droit d’inférence."""
    from acp_poste_contrat.inventaire import valider_inventaire
    observation = {"etat": "inconnu", "recu_le": None, "connexion": "inconnu", "origine_modeles": None, "quotas": []}
    ligne = conn.execute("SELECT contenu,recu_le,releve_le FROM inventaires WHERE machine_id=? ORDER BY id DESC LIMIT 1", (machine_id,)).fetchone() if machine_id else None
    if ligne is None:
        return None, None, [], [], observation
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
        return None, None, [], [], observation
    observation["recu_le"] = ligne["recu_le"]
    cle_moteur = "codex" if moteur == "codex" else "claude"
    version = inventaire.versions.get(cle_moteur)
    version = version.lue if version else None
    limite = int(base.reglage(conn, "releve_perime_s") or 7200)
    instant = min(ligne["recu_le"], ligne["releve_le"])
    if base.maintenant() - instant > limite:
        observation["etat"] = "perime"
        return None, version, [], [], observation
    # Un relevé commencé avant une connexion ne prouve pas l’état après celle-ci.
    if connexion and instant < connexion["actualise_le"]:
        observation["etat"] = "actualisation_en_attente"
        return None, version, [], [], observation
    statut_connexion = getattr(inventaire.connexions, cle_moteur)
    observation.update(etat="a_jour", connexion=statut_connexion)
    compte = ({"compte_chatgpt": True, "non_connecte": False, "cle_api": False, "autre": False}
              if moteur == "codex" else {"compte_claude": True, "jeton_absent": False, "refuse": False}).get(statut_connexion)
    voie = "poste-codex" if moteur == "codex" else "poste-claude"
    releve = next((r for r in inventaire.releves if r.voie == voie), None)
    modeles, alias = [], []
    if releve is not None:
        observation["origine_modeles"] = releve.origine_liste
        observation["quotas"] = [q.model_dump(mode="json") for q in releve.compteurs]
        if compte is True and releve.origine_liste == "compte" and releve.etat == "ok":
            modeles = [m.model_dump(mode="json") for m in releve.modeles if m.nature == "catalogue_compte"]
        if moteur == "claude_code" and releve.origine_liste == "alias_documentes" and releve.etat == "ok":
            alias = [m.model_dump(mode="json") for m in releve.modeles if m.nature == "alias_documente"]
    return compte, version, modeles, alias, observation


def etat(conn):
    with _VERROU:
        initialiser(conn)
        _expirer(conn)
        actif, serveur = _serveur(conn)
        comptes = []
        for moteur, nom in (("codex", "Codex"), ("claude_code", "Claude Code")):
            ligne = conn.execute("SELECT * FROM comptes_operations WHERE machine_id=? AND moteur=? ORDER BY cree_le DESC,rowid DESC LIMIT 1", (actif["id"], moteur)).fetchone() if actif else None
            connexion = _vue(conn, dict(ligne)) if ligne else None
            compte, version, modeles, alias, observation = _inventaire_compte(conn, actif["id"] if actif else None, connexion, moteur)
            recent = connexion and base.maintenant() - connexion["actualise_le"] <= int(base.reglage(conn, "releve_perime_s") or 7200)
            if compte is None and recent and observation["etat"] != "a_jour":
                compte = connexion["compte_connecte"]
                observation["etat"] = "actualisation_en_attente"
            statut, message = "inconnu", "État du compte inconnu. En attente d’un relevé du serveur."
            if not serveur["disponible"]:
                statut, message = "moteur_indisponible", serveur["raison"]
            elif connexion and connexion["etat"] not in C.TERMINAUX:
                statut, message = "connexion_en_attente", connexion["message"]
            elif compte is True:
                statut, message = "connecte", (MESSAGES if moteur == "codex" else MESSAGES_CLAUDE)["connecte"]
            elif compte is False:
                statut, message = "non_configure", "Aucun compte fournisseur reconnu sur le serveur. Utilisez la connexion officielle."
            elif connexion and connexion["etat"] in ("erreur", "interrompue"):
                statut, message = "erreur", connexion["message"]
            comptes.append({"moteur": moteur, "nom": nom, "implementation": "disponible", "etat": statut,
                            "version": version, "compte_connecte": compte, "inference_verifiee": False,
                            "modeles": modeles, "alias_documentes": alias, "connexion": connexion,
                            "observation": observation, "message": message})
        comptes.append({"moteur": "mistral_vibe", "nom": "Mistral Vibe", "implementation": "non_implemente",
                        "etat": "non_configure", "version": None, "compte_connecte": None,
                        "inference_verifiee": False, "modeles": [], "alias_documentes": [], "connexion": None,
                        "message": "Connexion graphique distante non implémentée dans cette version."})
        return {"protocole": C.PROTOCOLE, "serveur": serveur, "comptes": comptes}


def creer(conn, cle, auteur, moteur="codex"):
    C.identifiant(cle)
    if moteur not in ("codex", "claude_code"):
        raise ValueError("Moteur inconnu.")
    with _VERROU:
        initialiser(conn)
        with base.transaction(conn):
            _expirer(conn)
            existante = conn.execute("SELECT * FROM comptes_operations WHERE cle=?", (cle,)).fetchone()
            if existante:
                if existante["moteur"] != moteur:
                    raise refus("cle_autre_moteur", "Cette clé appartient à une connexion d’un autre moteur.")
                return _vue(conn, dict(existante))
            actif, serveur = _serveur(conn)
            if not serveur["disponible"]:
                raise refus("serveur_indisponible", serveur["raison"])
            existante = conn.execute("SELECT * FROM comptes_operations WHERE machine_id=? AND etat NOT IN ('connecte','annulee','expiree','interrompue','erreur') ORDER BY cree_le DESC LIMIT 1", (actif["id"],)).fetchone()
            if existante:
                raise refus("connexion_en_cours", "Une connexion est déjà en cours. Reprenez-la dans Comptes et modèles.")
            maintenant, identifiant = base.maintenant(), str(uuid4())
            ordre = ordres.creer_dans(conn, actif["id"], "releve", auteur)
            conn.execute("INSERT INTO comptes_operations (id,cle,machine_id,ordre_id,etat,motif,auteur,cree_le,actualise_le,limite_attente_le,moteur) VALUES (?,?,?,?,'en_attente','attente',?,?,?,?,?)", (identifiant, cle, actif["id"], ordre, auteur, maintenant, maintenant, maintenant + ATTENTE_MAX, moteur))
            base.journaliser(conn, auteur, f"connexion_{moteur}_demandee", cible=identifiant)
            return _vue(conn, _ligne(conn, identifiant))


def soumettre_code(conn, identifiant, defi_id, soumission_id, code, auteur):
    C.identifiant(identifiant)
    retour = C.RetourCode(defi_id=defi_id, soumission_id=soumission_id, code=code)
    with _VERROU:
        initialiser(conn)
        with base.transaction(conn):
            _expirer(conn)
            ligne = _ligne(conn, identifiant)
            if ligne["moteur"] != "claude_code" or ligne["defi_id"] != retour.defi_id:
                raise refus("defi_inactif", "Ce défi n’appartient pas à cette connexion Claude.")
            # Un retry perdu reçoit son état durable, jamais une seconde remise. Si
            # la RAM a disparu, même un code identique ne réarme pas l’ancien envoi.
            if ligne["soumission_id"] == retour.soumission_id:
                precedente = _CODES.get(_cle_code(conn, ligne))
                if precedente and not hmac.compare_digest(precedente["code"].encode("utf-8"), retour.code.encode("utf-8")):
                    raise refus("soumission_contradictoire", "Une remise déjà reçue ne peut pas changer de contenu.")
                return _vue(conn, ligne, retour.defi_id, retour.soumission_id)
            if ligne["soumission_id"] is not None:
                raise refus("code_deja_soumis", "Un code a déjà été soumis pour ce défi. Consultez son état avant de recommencer.")
            defi = _DEFIS.get(_cle_defi(conn, identifiant))
            actif, serveur = _serveur(conn)
            if not serveur["disponible"] or actif["id"] != ligne["machine_id"]:
                raise refus("serveur_indisponible", "Le serveur de cette connexion est indisponible.")
            if (ligne["etat"] != "code_disponible" or not defi
                    or defi["instance_id"] != ligne["instance_id"] or defi["defi_id"] != retour.defi_id):
                raise refus("defi_inactif", "Ce défi n’attend plus de code. Annulez puis recommencez si nécessaire.")
            conn.execute("UPDATE comptes_operations SET soumission_id=?,code_transmis=0 WHERE id=?", (retour.soumission_id, identifiant))
            _CODES[_cle_code(conn, ligne)] = {"limite": ligne["limite_attente_le"],
                                            "soumission_id": retour.soumission_id, "code": retour.code}
            base.journaliser(conn, auteur, "connexion_claude_code_soumise", cible=identifiant)
            return _vue(conn, _ligne(conn, identifiant), retour.defi_id, retour.soumission_id)


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
                conn.execute("UPDATE comptes_operations SET etat=?,motif=?,actualise_le=? WHERE id=?", (etat, motif, base.maintenant(), identifiant))
                _purger(conn, identifiant)
                base.journaliser(conn, auteur, f"connexion_{ligne['moteur']}_annulation", cible=identifiant)
            return _vue(conn, _ligne(conn, identifiant))


def _observer(conn, machine_id, instance_id, observation, maintenant):
    ligne = _ligne(conn, observation.operation_id)
    if (ligne["machine_id"] != machine_id or ligne["instance_id"] != instance_id
            or ligne["moteur"] != observation.moteur):
        raise refus("connexion_etrangere", "Cette connexion appartient à un autre moteur, exécutant ou à une ancienne instance.")
    ack = observation.code_transmis
    if ack is not None and (ack.defi_id, ack.soumission_id) != (ligne["defi_id"], ligne["soumission_id"]):
        raise refus("accuse_etranger", "Cet accusé ne correspond pas à la remise attendue.")
    ignorer = (ligne["etat"] in C.TERMINAUX or observation.numero < ligne["numero"]
               or ligne["etat"] == "annulation_demandee" and observation.etat not in C.TERMINAUX)
    if not ignorer:
        if observation.numero == ligne["numero"] and ligne["etat"] != "annulation_demandee":
            if (ligne["etat"], ligne["motif"], ligne["compte_connecte"]) != (observation.etat, observation.motif, observation.compte_connecte):
                raise refus("observation_contradictoire", "Une observation déjà reçue ne peut pas changer.")
        progression = {"demarrage": 0, "code_disponible": 1, "verification": 2}
        if observation.etat in progression and ligne["etat"] in progression and progression[observation.etat] < progression[ligne["etat"]]:
            raise refus("observation_obsolete", "L’état de connexion ne peut pas revenir en arrière.")
        if observation.etat == "code_disponible":
            if ligne["defi_id"] is not None and (ligne["defi_id"], ligne["defi_type"]) != (observation.defi_id, observation.defi_type):
                raise refus("defi_modifie", "Le défi d’une connexion déjà reçue ne peut pas changer.")
            precedent = _DEFIS.get(_cle_defi(conn, ligne["id"]))
            if precedent and (precedent["url"], precedent["code"]) != (observation.verification_url, observation.code_utilisateur):
                raise refus("defi_modifie", "Le défi d’une connexion déjà reçue ne peut pas changer.")
    # Ne détruit jamais la RAM avant une validation qui pourrait faire annuler
    # l’ACK SQL. Un ACK tardif reste recevable même après expiration/annulation.
    if ack is not None:
        conn.execute("UPDATE comptes_operations SET code_transmis=1 WHERE id=?", (ligne["id"],))
        _CODES.pop(_cle_code(conn, ligne), None)
    if ignorer:
        return
    if observation.etat == "code_disponible":
        conn.execute("UPDATE comptes_operations SET defi_id=?,defi_type=? WHERE id=?", (observation.defi_id, observation.defi_type, ligne["id"]))
        _DEFIS[_cle_defi(conn, ligne["id"])] = {"limite": ligne["limite_attente_le"], "url": observation.verification_url,
                                              "code": observation.code_utilisateur, "instance_id": instance_id,
                                              "defi_id": observation.defi_id}
    else:
        _DEFIS.pop(_cle_defi(conn, ligne["id"]), None)
    # L’annulation reçue par Hermes garde priorité sur un succès déjà constitué
    # dans le contrôleur. L’ancien compte peut toutefois être encore connecté.
    etat, motif = observation.etat, observation.motif
    if ligne["etat"] == "annulation_demandee" and etat == "connecte":
        etat, motif = "annulee", "annulee"
    conn.execute("UPDATE comptes_operations SET etat=?,motif=?,numero=?,compte_connecte=?,actualise_le=? WHERE id=?", (etat, motif, observation.numero, observation.compte_connecte, maintenant, ligne["id"]))
    if etat in C.TERMINAUX:
        _purger(conn, ligne["id"])
        ordres.acquitter_dans(conn, machine_id, [ligne["ordre_id"]])
        base.journaliser(conn, "executant", f"connexion_{ligne['moteur']}_terminee", cible=ligne["id"], detail={"etat": etat})


def echanger(conn, machine_id, requete: C.Echange):
    with _VERROU:
        initialiser(conn)
        with base.transaction(conn):
            raison = distant.raison_refus(conn, machine_id)
            if raison:
                raise refus("executant_distant_requis", raison)
            maintenant = base.maintenant()
            connu = conn.execute("SELECT * FROM comptes_executants WHERE machine_id=?", (machine_id,)).fetchone()
            if connu and connu["instance_id"] != requete.instance_id and maintenant - connu["derniere_vue"] <= PRESENCE_MAX:
                raise refus("instance_deja_active", "Une autre instance du serveur utilise déjà ce compte. Attendez sa fin.")
            if connu and connu["instance_id"] != requete.instance_id:
                for operation in conn.execute("SELECT id FROM comptes_operations WHERE machine_id=?", (machine_id,)):
                    _purger(conn, operation["id"])
            conn.execute("INSERT INTO comptes_executants VALUES (?,?,?) ON CONFLICT(machine_id) DO UPDATE SET instance_id=excluded.instance_id,derniere_vue=excluded.derniere_vue", (machine_id, requete.instance_id, maintenant))
            _expirer(conn)
            if requete.observation:
                _observer(conn, machine_id, requete.instance_id, requete.observation, maintenant)
            ligne = conn.execute("SELECT * FROM comptes_operations WHERE machine_id=? AND etat NOT IN ('connecte','annulee','expiree','interrompue','erreur') ORDER BY cree_le LIMIT 1", (machine_id,)).fetchone()
            if ligne is None:
                return {"protocole": C.PROTOCOLE, "operation": None}
            ligne = dict(ligne)
            action = "annuler" if ligne["etat"] == "annulation_demandee" else "attendre"
            if ligne["instance_id"] != requete.instance_id:
                if not requete.libre:
                    return {"protocole": C.PROTOCOLE, "operation": None}
                _purger(conn, ligne["id"])
                if ligne["etat"] == "annulation_demandee":
                    conn.execute("UPDATE comptes_operations SET instance_id=?,numero=0,actualise_le=? WHERE id=?", (requete.instance_id, maintenant, ligne["id"]))
                else:
                    action = "demarrer" if ligne["instance_id"] is None and ligne["etat"] == "en_attente" else "reconcilier"
                    conn.execute("UPDATE comptes_operations SET instance_id=?,numero=0,etat='demarrage',motif='demarrage',actualise_le=? WHERE id=?", (requete.instance_id, maintenant, ligne["id"]))
            operation = {"id": ligne["id"], "moteur": ligne["moteur"], "action": action,
                         "limite_attente_le": ligne["limite_attente_le"], "retour_code": None}
            code = _CODES.get(_cle_code(conn, ligne))
            if (action == "attendre" and ligne["etat"] == "code_disponible" and code
                    and not ligne["code_transmis"] and code["soumission_id"] == ligne["soumission_id"]):
                operation.update(action="fournir_code", retour_code={"defi_id": ligne["defi_id"],
                                 "soumission_id": code["soumission_id"], "code": code["code"]})
            return C.Reponse(operation=operation).model_dump(mode="json")
