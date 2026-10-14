"""Événements publics distants dans le journal SQLite existant.

Les reçus sont atomiques avec les lignes du journal, jamais une nouvelle base.
L'identifiant moteur ne remplace ni le run ACP ni la tentative d'invocation.
"""
from __future__ import annotations

import hashlib
import json

from acp_poste_contrat.machine import secret_trouve

from . import base
from .textes import RefusACP


def enregistrer(conn, machine_id, demande, requete, *, parents=()):
    """Dans la transaction appelante, APRÈS vérification de la réclamation."""
    evenements = getattr(requete, "evenements", ())
    if not evenements:
        return []
    conn.execute("""CREATE TABLE IF NOT EXISTS evenements_execution_recus (
        id TEXT PRIMARY KEY, empreinte TEXT NOT NULL,
        machine_id TEXT NOT NULL, tableau TEXT NOT NULL, carte TEXT NOT NULL,
        run_id INTEGER NOT NULL, tentative_id TEXT NOT NULL, ordre INTEGER NOT NULL,
        journal_id INTEGER NOT NULL REFERENCES journal(id),
        UNIQUE(machine_id, tableau, carte, run_id, tentative_id, ordre))""")
    recus = []
    for modele in evenements:
        evenement = modele.model_dump(mode="json")
        if secret_trouve(evenement):
            raise RefusACP("secret_detecte", "Événement public refusé : secret détecté.")
        attendu = "codex" if demande["voie"] == "poste-codex" else "claude"
        if evenement["moteur"] != attendu:
            raise RefusACP("evenement_incoherent", "Le moteur de l’événement diffère de la carte réclamée.")
        source = dict(evenement, machine_id=machine_id, tableau=requete.tableau,
                      carte=requete.carte, run_id=requete.run_id)
        empreinte = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        connu = conn.execute("SELECT empreinte FROM evenements_execution_recus WHERE id = ?", (evenement["id"],)).fetchone()
        if connu is not None:
            if connu[0] != empreinte:
                raise RefusACP("evenement_conflit", "Cet identifiant d’événement a déjà un autre contenu.")
            recus.append(evenement["id"])
            continue
        place = conn.execute("SELECT id FROM evenements_execution_recus WHERE machine_id = ? AND tableau = ? "
            "AND carte = ? AND run_id = ? AND tentative_id = ? AND ordre = ?",
            (machine_id, requete.tableau, requete.carte, requete.run_id, evenement["tentative_id"], evenement["ordre"])).fetchone()
        if place:
            raise RefusACP("evenement_conflit", "Ce rang d’événement est déjà occupé dans la tentative.")
        source.update(projet_id=demande["projet_id"], agent=demande.get("role"),
                      parents=list(parents), modele_demande=demande.get("modele"))
        # JSON intact, sans troncature après sérialisation. Le contrat borne les champs en amont.
        ligne = conn.execute("INSERT INTO journal (quand, acteur, action, projet_id, cible, detail) "
            "VALUES (?, ?, 'execution_publique', ?, ?, ?)",
            (base.maintenant(), "executant:" + machine_id, demande["projet_id"], requete.carte,
             json.dumps(source, ensure_ascii=False)))
        conn.execute("INSERT INTO evenements_execution_recus VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (evenement["id"], empreinte, machine_id, requete.tableau, requete.carte, requete.run_id,
             evenement["tentative_id"], evenement["ordre"], ligne.lastrowid))
        recus.append(evenement["id"])
    return recus


def lire(conn, projet_id, *, apres=0, limite=100):
    """Lecture seule : le curseur est le rang global du journal, jamais un ordre de relance."""
    if type(apres) is not int or not 0 <= apres < 2**63 or type(limite) is not int or not 1 <= limite <= 200:
        raise RefusACP("arguments", "Curseur positif et limite de 1 à 200 attendus.")
    lignes = conn.execute("SELECT id, detail FROM journal WHERE projet_id = ? AND action = 'execution_publique' "
                         "AND id > ? ORDER BY id LIMIT ?", (projet_id, apres, limite + 1)).fetchall()
    evenements = [dict(json.loads(ligne[1]), curseur=ligne[0]) for ligne in lignes[:limite]]
    return {"projet_id": projet_id, "evenements": evenements,
            "prochain_curseur": evenements[-1]["curseur"] if evenements else apres,
            "encore": len(lignes) > limite}
