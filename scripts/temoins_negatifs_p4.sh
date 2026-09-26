#!/usr/bin/env bash
# Témoins négatifs de l'étape P4 (docs/refonte/projets.md § 9 et § 12) : chaque protection du cœur serveur est
# retirée, UNE à la fois, dans un conteneur jetable de l'image de TEST ; les tests qui la couvrent doivent
# alors échouer. Rien n'est modifié hors du conteneur, qui est détruit après chaque témoin.
#
#   IMAGE=acp-hermes-tests:p4 bash scripts/temoins_negatifs_p4.sh
#
# Sortie : pour chaque protection, la mutation appliquée (refus si son motif est introuvable : un témoin
# qui ne mute rien ne prouverait rien) et le résumé de pytest. Code 0 seulement si CHAQUE témoin a vu ses
# tests échouer ; code 1 sinon (protection non couverte ou mutation introuvable).
set -u

IMAGE=${IMAGE:-acp-hermes-tests:p4}
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
  commande+="PYTHONPATH=/opt/acp-tests/site $PY -m pytest -q -p no:cacheprovider $selection"
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

temoin "liste blanche de la garde : projet_etat retiré" \
  "$T/test_sans_shell.py -k 'garde_admet_exactement or garde_liste_blanche'" \
  $G/garde_execution.py '"projet_lancer", "projet_planifier", "projet_etat", "poste_etat",' \
  '"projet_lancer", "projet_planifier", "poste_etat",'
temoin "visibilité des outils par contexte (check_fn) retirée" \
  "$T/test_outils_greffon.py::test_visibilite_discussion_worker" \
  $G/noyau/outils.py 'if nom in DISCUSSION_SEULE:' 'if False:' \
  $G/noyau/outils.py 'if nom in WORKER_SEUL:' 'if False:'
temoin "known_plugin_toolsets retiré de la managed scope" \
  "$T/test_sans_shell.py::test_outils_acp_absents_d_api_server_et_cron" \
  /opt/acp/gere/config.yaml $'known_plugin_toolsets:\n  api_server: [acp_poste]\n  cron: [acp_poste]\n' ''
temoin "balayage des cartes poste-* étrangères coupé" \
  "$T/test_etrangeres.py::test_carte_poste_du_proprietaire_bloquee_avec_raison" \
  $G/noyau/etrangeres.py 'for meta in ka.list_boards(include_archived=False):' 'for meta in []:'
temoin "transaction kanban externe d'un tour retirée" \
  "$T/test_projets_planifier.py::test_atomique_rien_si_une_creation_leve" \
  $G/noyau/cartes.py 'with ka.write_txn(kconn):' 'with contextlib.nullcontext():' \
  $G/noyau/cartes.py $'\nimport json\n' $'\nimport contextlib\nimport json\n'
temoin "unicité des notifications par clé retirée" \
  "$T/test_emetteur.py::test_envoi_unique_par_cle_meme_rejoue" \
  $G/noyau/base.py 'cle TEXT NOT NULL UNIQUE,' 'cle TEXT NOT NULL,'
temoin "plafond des tours retiré" \
  "$T/test_projets_planifier.py::test_plafond_tours_carte_de_triage_unique" \
  $G/noyau/graphe.py 'if tour > int(fiche["plafond_tours"]):' 'if False:'
temoin "plafond des cartes retiré" \
  "$T/test_projets_planifier.py::test_plafond_cartes_sans_creation_partielle" \
  $G/noyau/graphe.py 'if int(fiche["cartes_creees"]) + len(demandes) > int(fiche["plafond_cartes"]):' 'if False:'
temoin "refus des crochets shell au démarrage retiré" \
  "$T/test_demarrage.py -k hooks_non_vide_refuse" \
  /opt/acp/bin/acp_demarrage.py '        if crochets:' '        if False:'
temoin "retrait des variables de notification de os.environ retiré" \
  "$T/test_emetteur.py::test_secrets_retires_de_os_environ" \
  $G/__init__.py 'variables = retirer_variables_de_notification()' \
  'variables = {k: v for k, v in os.environ.items() if k.startswith("ACP_")}'
temoin "ordre des corrections : liaisons vers la synthèse retirées" \
  "$T/test_corrections.py::test_ordre_correction_liaison_puis_fin" \
  $G/noyau/graphe.py 'ka.link_tasks(kc, ids[cle_corr], synthese["carte"])' 'pass' \
  $G/noyau/graphe.py 'ka.link_tasks(kc, ids[cle_rel], synthese["carte"])' 'pass'
temoin "memory admis dans un worker kanban (décision D40)" \
  "$T/test_sans_shell.py::test_memoire_refusee_dans_un_worker_kanban" \
  $G/garde_execution.py 'if tool_name in MOTIFS_DANS_UN_WORKER and _dans_un_worker_kanban():' 'if False:'

# Corrections de la relecture indépendante de P4 (docs/refonte/projets.md § 12).
temoin "isolation des projets dans un worker retirée (garde, D44)" \
  "$T/test_sans_shell.py::test_un_worker_ne_touche_que_son_tableau_et_sa_carte" \
  $G/garde_execution.py 'motif = _hors_de_sa_carte(tool_name, args)' 'motif = None'
temoin "redirection suivie par le transport des notifications" \
  "$T/test_emetteur.py::test_transport_ne_suit_aucune_redirection" \
  $G/noyau/notifications.py $'def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102, N802\n        return None' \
  $'def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102, N802\n        return super().redirect_request(req, fp, code, msg, headers, newurl)'
temoin "reprise générale admise malgré des crochets shell" \
  "$T/test_routes_projets.py::test_reprise_generale_refusee_tant_que_des_crochets_existent" \
  $G/dashboard/plugin_api.py '            if constats:' '            if False:'
temoin "filet de l'émetteur : planification finie sans plan" \
  "$T/test_emetteur.py::test_planification_finie_sans_plan_adresse_une_decision" \
  $G/noyau/emetteur.py '_pas(bilan, "sans_plan", planifications_sans_plan, conn)' 'pass'
temoin "filet de l'émetteur : question restée sans suite" \
  "$T/test_emetteur.py::test_question_sans_suite_escaladee" \
  $G/noyau/emetteur.py '_pas(bilan, "sans_suite", questions.questions_sans_suite, conn)' 'pass'
temoin "décision au plafond de cartes quand plus aucun plan ne tient" \
  "$T/test_projets_planifier.py::test_plafond_de_cartes_sans_plan_possible_adresse_une_decision" \
  $G/noyau/graphe.py 'if int(fiche["plafond_cartes"]) - int(fiche["cartes_creees"]) < 2:' 'if False:'
temoin "« Prolonger » : la carte de décision ne planifie plus (D41)" \
  "$T/test_projets_planifier.py::test_prolonger_au_plafond_de_tours_planifie_un_tour_de_plus" \
  $G/noyau/graphe.py 'decision = demande is not None and demande["role"] == "triage" and demande["ref"] in REFS_PLANIFICATRICES' \
  'decision = False'
temoin "plafond de projets actifs ignoré à la reprise" \
  "$T/test_pause.py::test_reprise_respecte_le_plafond_de_projets_actifs" \
  $G/noyau/projets.py 'raise refus("projets_actifs", T.PROJETS_ACTIFS_REPRISE' 'pass  # '
temoin "raison d'une carte bloquée lue dans last_failure_error seulement" \
  "$T/test_questions.py::test_raison_connue_des_cartes_bloquees_et_en_triage" \
  $G/noyau/questions.py '"raison": _raison(tache, evenements)}' '"raison": ka.masquer(tache.last_failure_error or "")[:300] or None}'
temoin "résumé coupé sans le dire" \
  "$T/test_routes_projets.py::test_resume_coupe_le_dit_et_se_lit_en_entier" \
  $G/noyau/projets.py '"resume_tronque": bool(resume) and len(resume) > LONGUEUR_RESUME,' '"resume_tronque": False,'
temoin "réponse pendant la pause : carte débloquée tout de suite" \
  "$T/test_pause.py::test_reponse_pendant_la_pause_reprend_a_la_reprise_du_projet" \
  $G/noyau/questions.py 'if fiche is not None and fiche["etat"] == "en_pause":' 'if False:'
temoin "surcharge de routage de portée « carte » admise" \
  "$T/test_routage.py::test_surcharge_d_une_carte_refusee_tant_qu_elle_ne_s_applique_pas" \
  $G/noyau/outils.py 'if portee == "carte":' 'if False:'

echo
if [ "$ECHECS" -eq 0 ]; then
  echo "Témoins négatifs : $TEMOINS sur $TEMOINS, chaque protection retirée fait échouer ses tests."
  exit 0
fi
echo "Témoins négatifs : $ECHECS anomalie(s)."
exit 1
