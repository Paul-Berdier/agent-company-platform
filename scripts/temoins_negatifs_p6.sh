#!/usr/bin/env bash
# Témoins négatifs de l'étape P6, côté Hermes (cahier P6 § 5, § 9, § 14.2) : chaque protection de l'exécution des
# cartes par le greffon acp-poste est retirée, UNE à la fois, dans un conteneur jetable de l'image de TEST ; les tests
# qui la couvrent doivent alors échouer. Rien n'est modifié hors du conteneur, qui est détruit après chaque témoin.
#
#   IMAGE=acp-hermes-tests:p6 bash scripts/temoins_negatifs_p6.sh
#
# Sortie : pour chaque protection, la mutation appliquée (refus si son motif est introuvable : un témoin qui ne
# mute rien ne prouverait rien) et le résumé de pytest. Code 0 seulement si CHAQUE témoin a vu ses tests échouer ;
# code 1 sinon (protection non couverte ou mutation introuvable). Les protections de l'exécutant lui-même (bac à sable,
# UID séparés, balayage du diff…) ont leurs témoins dans apps/poste et executant/.
set -u

IMAGE=${IMAGE:-acp-hermes-tests:p6}
G=/opt/hermes/plugins/acp-poste
T=/opt/acp-tests/image
PY=/opt/hermes/.venv/bin/python
MUTER='import sys
chemin, ancien, nouveau = sys.argv[1:4]
texte = open(chemin, encoding="utf-8").read()
if ancien not in texte:
    sys.exit("MUTATION INTROUVABLE dans " + chemin)
open(chemin, "w", encoding="utf-8").write(texte.replace(ancien, nouveau))
print("mutation appliquée : " + chemin)'
ECHECS=0
TEMOINS=0

temoin() {  # libellé ; sélection pytest ; puis triplets (fichier, ancien, nouveau)
  local libelle=$1 selection=$2 commande="" sortie code
  TEMOINS=$((TEMOINS + 1))
  shift 2
  while [ $# -gt 0 ]; do
    commande+="$PY -c $(printf %q "$MUTER") $(printf %q "$1") $(printf %q "$2") $(printf %q "$3") || exit 99; "
    shift 3
  done
  commande+="PYTHONPATH=/opt/acp-tests/site $PY -m pytest -q -p no:cacheprovider -W ignore::DeprecationWarning $selection"
  sortie=$(MSYS_NO_PATHCONV=1 docker run --rm --entrypoint bash "$IMAGE" -c "$commande" 2>&1)
  code=$?
  echo "=== $libelle"
  printf '%s\n' "$sortie" | grep -E "^mutation appliquée|MUTATION INTROUVABLE|^FAILED|^ERROR|passed|failed|error" | tail -8
  if [ "$code" -eq 1 ]; then
    echo "→ tests en échec, comme attendu"
  else
    echo "→ ANOMALIE : code $code (1 attendu)"
    ECHECS=$((ECHECS + 1))
  fi
}

X=$T/test_execution_p6.py
R=$T/test_routage_p6.py

temoin "carte servie sans que le poste l'ait demandée (peut_executer: false ; contrat et greffon)" \
  "$X::test_reclamer_peut_executer_faux_jamais_de_carte" \
  $G/contrat/acp_poste_contrat/machine.py '        if self.voies_disponibles and not self.peut_executer:' '        if False:' \
  $G/noyau/execution.py '    if not requete.peut_executer or not requete.voies_disponibles:
        return None
    if ka.get_state() is not None:' '    if ka.get_state() is not None:' \
  $G/dashboard/plugin_api.py '    if not requete.peut_executer or not requete.voies_disponibles:
        return None
    try:' '    try:'
temoin "carte forgée (non émise par le greffon) servie à l'exécutant" \
  "$X::test_reclamer_sert_seulement_les_cartes_emises" \
  $G/noyau/execution.py '        demande = etrangeres.demande_de_la_carte(conn, tableau, tache) if tache is not None else None
        if fiche is None or fiche["etat"] != "actif" or demande is None or demande["role"] not in ROLES_SERVIS:
            return None' '        demande = etrangeres.demande_de_la_carte(conn, tableau, tache) if tache is not None else None
        demande = demande or {"role": "exploration", "voie": tache.assignee, "modele": None, "effort": None,
                              "palier": None, "cle": "forgee"}
        if fiche is None or fiche["etat"] != "actif":
            return None'
temoin "réclamant autre que acp-poste:<machine>" \
  "$X::test_claim_ttl_2700_claimer_stable" \
  $G/noyau/execution.py '    return f"acp-poste:{machine_id}"' '    return None'
temoin "concurrence 1 levée (une autre carte servie pendant qu'une est en main)" \
  "$X::test_une_carte_a_la_fois" \
  $G/noyau/execution.py '        if en_cours is not None:
            demande = projets.demande_de_la_carte' '        if False:
            demande = projets.demande_de_la_carte'
temoin "preuve de propriété retirée (run d'une autre réclamation accepté)" \
  "$X::test_reclamation_perdue_409_sans_effet" \
  $G/noyau/execution.py '            and tache.current_run_id is not None and int(tache.current_run_id) == int(run_id))' \
  '            and tache.current_run_id is not None)' \
  $G/noyau/execution.py '            fait = ka.complete_task(kc, requete.carte, summary=texte[:8000], metadata=metadonnees,
                                    expected_run_id=requete.run_id)' '            fait = ka.complete_task(kc, requete.carte, summary=texte[:8000], metadata=metadonnees,
                                    force=True)'
temoin "balayage des secrets retiré avant l'effet" \
  "$X::test_secret_detecte_422_rien_ecrit" \
  $G/dashboard/plugin_api.py '    motif = contrat.secret_trouve(corps)' '    motif = None'
temoin "envoi rejoué exécuté une seconde fois (idempotence retirée)" \
  "$X::test_terminer_idempotent" \
  $G/noyau/execution.py '    ligne = conn.execute("SELECT * FROM envois WHERE id_envoi = ?", (id_envoi,)).fetchone()
    if ligne is None:' '    ligne = None
    if ligne is None:'
temoin "battement qui ne prolonge pas la réclamation" \
  "$X::test_battement_prolonge" \
  $G/noyau/execution.py '            if not ka.heartbeat_claim(kc, requete.carte, ttl_seconds=ttl, claimer=claimer(machine_id)):' \
  '            if False:'
temoin "battement valide après la reprise de la carte (propriété et réclamation non vérifiées)" \
  "$X::test_battement_invalide_apres_reprise" \
  $G/noyau/execution.py '            if not _a_nous(tache, machine_id, requete.run_id):
                return {"valide": False, "pause": pause, "annuler": False}
            ttl =' '            ttl =' \
  $G/noyau/execution.py '            if not ka.heartbeat_claim(kc, requete.carte, ttl_seconds=ttl, claimer=claimer(machine_id)):
                return {"valide": False, "pause": pause, "annuler": False}' '            ka.heartbeat_claim(kc, requete.carte, ttl_seconds=ttl, claimer=claimer(machine_id))'
temoin "fichiers de pilotage touchés terminés sans revue" \
  "$X::test_terminer_pilotage_en_revue" \
  $G/noyau/execution.py '        if meta.pilotage.touche:' '        if False:'
temoin "refus d'une revue par block_task (sans effet) au lieu de reopen_review_task" \
  "$X::test_revue_refuser_rouvre_avec_le_motif" \
  $G/noyau/execution.py '            fait = ka.reopen_review_task(kc, carte)' \
  '            fait = ka.block_task(kc, carte, kind="needs_input", reason=motif)'
temoin "motif du refus jamais livré à l'exécutant" \
  "$X::test_revue_refuser_rouvre_avec_le_motif" \
  $G/noyau/execution.py '    if demande.get("revue_refusee_le") and not demande.get("refus_livre_le") and demande.get("motif_refus"):' \
  '    if False:'
temoin "correction créée sans la terminer dans l'ordre (relecture complétée seule)" \
  "$X::test_terminer_corrections_dans_l_ordre" \
  $G/noyau/execution.py '        if demande["role"] == "relecture" and requete.verdict == "corrections":' '        if False:'
temoin "question qui bloque la carte (triage à la seconde) au lieu de la planifier" \
  "$X::test_deux_questions_sans_triage" \
  $G/noyau/questions.py '        ka.schedule_task(kc, carte, reason=T.RAISON_QUESTION.format(q=identifiant), expected_run_id=run_id)' \
  '        ka.block_task(kc, carte, kind="needs_input", reason=T.RAISON_QUESTION.format(q=identifiant), expected_run_id=run_id)'
temoin "réponse à une question jamais livrée à la carte resservie" \
  "$X::test_deux_questions_sans_triage" \
  $G/noyau/execution.py "AND livree_le IS NULL AND reponse IS NOT NULL ORDER BY repondue_le, id\"" \
  "AND livree_le IS NULL AND reponse IS NOT NULL AND 0 ORDER BY repondue_le, id\""
temoin "attente de quota jamais levée" \
  "$X::test_bloquer_quota_debloque_a_l_heure" \
  $G/noyau/attentes.py '                    fait = bool(ka.unblock_task(kc, ligne["carte"]))' '                    fait = False'
temoin "secret bloqué avec la raison de l'exécutant (jamais la raison fixe)" \
  "$X::test_bloquer_secret_reste_bloquee" \
  $G/noyau/execution.py 'reason=T.RAISON_SECRET_EXECUTANT,' 'reason=raison,'
temoin "reprendre qui ne remet pas la carte en jeu" \
  "$X::test_reprendre_avant_ttl_compteur_zero" \
  $G/noyau/execution.py '            fait = ka.reclaim_task(kc, requete.carte, reason=f"acp-poste : {motif}")' '            fait = False'
temoin "arrêt propre sans grâce de la notification « hors ligne »" \
  "$X::test_arret_grace_hors_ligne" \
  $G/noyau/presence.py '        if en_redeploiement(conn, ligne):
            continue' '        pass'
temoin "résumés des parents jamais réduits (carte de plus de 60 Kio bloquée au lieu d'être servie)" \
  "$X::test_carte_resumes_des_parents_reduits_sous_60_kio" \
  $G/noyau/execution.py '    for borne in (1000, 500, 200, 0):' '    for borne in ():'
temoin "consigne démesurée jamais tronquée (ni la mention)" \
  "$X::test_carte_consigne_tronquee_et_dite_sous_60_kio" \
  $G/noyau/execution.py '    while taille_json(carte) > TAILLE_MAX_CARTE and len(consigne) > 200:' '    while False:'
temoin "intégration créée sans branche rapportée (cartes terminées hors de l'exécutant)" \
  "$X::test_projet_simule_sans_branche_rapportee_termine_sans_integration" \
  $G/noyau/execution.py '"AND branche IS NOT NULL ORDER BY tour, cree_le, rowid"' '"ORDER BY tour, cree_le, rowid"' \
  $G/noyau/execution.py $'                branche = ligne["branche"]\n                if branche' \
  $'                branche = ligne["branche"] or "hermes/" + ligne["carte"]\n                if branche'
temoin "projet terminé sans attendre son intégration" \
  "$X::test_integration_servie_sur_poste_integration" \
  $G/noyau/emetteur.py '            continue  # intégration créée à l'"'"'instant' '            pass  # intégration créée à l'"'"'instant'
temoin "voie fermée ignorée par le routage" \
  "$R::test_voies_fermees_d_apres_l_inventaire" \
  $G/noyau/routage.py '    if fermee:
        raise refus("voie_fermee"' '    if False:
        raise refus("voie_fermee"'
temoin "relecture de repli par le MÊME modèle que l'implémentation" \
  "$R::test_relecture_repli_sans_autre_modele_refusee" \
  $G/noyau/routage.py '        if not modele_rel or modele_rel == modele_relu:' '        if not modele_rel:'
temoin "repli de la relecture appliqué malgré le réglage levé (D27 contourné)" \
  "$R::test_relecture_repli_refusee_sans_d88" \
  $G/noyau/routage.py '    if fermee and base.reglage(conn, "relecture_repli_meme_voie"):' '    if fermee:'
temoin "carte d'une voie fermée jamais bloquée (attend en silence)" \
  "$R::test_carte_voie_fermee_apres_composition_signalee" \
  $G/noyau/execution.py '                        elif maintenant - int(depuis) >= delai:' '                        elif False:'

echo
echo "$TEMOINS témoins, $ECHECS anomalie(s)."
[ "$ECHECS" -eq 0 ]
