#!/usr/bin/env bash
# Témoins négatifs de l'étape P5, côté Hermes (cahier P5 § 14.8 ; docs/refonte/poste.md) : chaque protection du
# greffon acp-poste est retirée, UNE à la fois, dans un conteneur jetable de l'image de TEST ; les tests qui la
# couvrent doivent alors échouer. Rien n'est modifié hors du conteneur, qui est détruit après chaque témoin.
#
#   IMAGE=acp-hermes-tests:p5 bash scripts/temoins_negatifs_p5.sh
#
# Sortie : pour chaque protection, la mutation appliquée (refus si son motif est introuvable : un témoin qui ne
# mute rien ne prouverait rien) et le résumé de pytest. Code 0 seulement si CHAQUE témoin a vu ses tests échouer ;
# code 1 sinon (protection non couverte ou mutation introuvable). Les protections du poste Windows (HTTPS exigé,
# DPAPI, second app-server…) ont leurs témoins dans apps/poste.
set -u

IMAGE=${IMAGE:-acp-hermes-tests:p5}
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

temoin "contrôle du fournisseur dans le gestionnaire retiré" \
  "$T/test_routes_machine.py::test_mauvais_fournisseur_403" \
  $G/dashboard/plugin_api.py 'if getattr(principal, "provider", None) != FOURNISSEUR_MACHINE:' 'if False:'
temoin "contrôle de la portée retiré (code d'enrôlement sur une route machine)" \
  "$T/test_routes_machine.py -k portee_croisee" \
  $G/dashboard/plugin_api.py 'if portee == "machine" and "machine" not in portees:' 'if False:'
temoin "comparaison arrêtée à la première empreinte égale" \
  "$T/test_jeton_machine.py::test_comparaison_a_temps_constant" \
  $G/noyau/jeton_machine.py $'if hmac.compare_digest(calcule, str(empreinte)) and trouve is None:\n                trouve = identifiant' \
  $'if hmac.compare_digest(calcule, str(empreinte)):\n                trouve = identifiant\n                break'
temoin "exception interne de verify_token laissée à la couture (401 au lieu de 503)" \
  "$T/test_jeton_machine.py::test_exception_interne_devient_provider_error" \
  $G/noyau/jeton_machine.py 'raise aa.ProviderError(f"acp-poste : base du greffon illisible ({type(exc).__name__})") from None' \
  'raise'
temoin "état du poste non relu dans la transaction de la route" \
  "$T/test_longpoll.py -k 'revocation'" \
  $G/dashboard/plugin_api.py $'            if ligne is None or ligne["etat"] == "revoque":\n                return {"revoque": ligne}\n            maintenant' \
  $'            if False:\n                return {"revoque": ligne}\n            maintenant' \
  $G/dashboard/plugin_api.py $'            if ligne is None or ligne["etat"] == "revoque":\n                return {"revoque": ligne}\n            pause' \
  $'            if False:\n                return {"revoque": ligne}\n            pause'
temoin "réveil de l'attente depuis un fil retiré (call_soon_threadsafe)" \
  "$T/test_longpoll.py::test_reveil_par_ordre" \
  $G/dashboard/plugin_api.py 'self.boucle.call_soon_threadsafe(self.evenement.set)' 'pass'
temoin "déconnexion du poste non détectée (lecture bornée retirée)" \
  "$T/test_longpoll.py::test_deconnexion_libere" \
  $G/dashboard/plugin_api.py $'            if await _deconnecte(request):\n' $'            if False:\n'
temoin "code d'enrôlement accepté déjà utilisé ou expiré" \
  "$T/test_routes_machine.py -k 'code_usage_unique or code_expire'" \
  $G/noyau/jeton_machine.py 'WHERE utilise_le IS NULL "' 'WHERE 1 = 1 OR utilise_le IS NULL "'
temoin "un second poste enrôlé malgré un poste actif" \
  "$T/test_routes_machine.py::test_un_seul_poste_actif" \
  $G/noyau/machines.py $'    actif = machine_active(conn)\n    if actif is not None:\n        raise RefusACP("poste_deja_enrole", T.POSTE_DEJA_ENROLE.format(nom=actif["nom"]))\n    maintenant' \
  $'    maintenant'
temoin "inventaire accepté avant la confirmation de l'empreinte" \
  "$T/test_routes_machine.py::test_inventaire_avant_confirmation_403" \
  $G/dashboard/plugin_api.py '                if ligne["etat"] == "a_confirmer":' '                if False:'
temoin "inventaire reçu sans validation par le contrat" \
  "$T/test_routes_machine.py::test_inventaire_hors_contrat_422" \
  $G/noyau/inventaire.py '        return valider_inventaire(corps)' '        return InventairePoste.model_construct(**corps)'
temoin "garde « aucun identifiant » retirée à la réception" \
  "$T/test_machines_base.py::test_inventaire_avec_un_identifiant_refuse" \
  $G/noyau/inventaire.py '    trouve = identifiant_trouve(corps)' '    trouve = None'
temoin "cadence des inventaires retirée" \
  "$T/test_routes_machine.py::test_inventaire_trop_frequent_429" \
  $G/dashboard/plugin_api.py '                if delai > 0:' '                if False:'
temoin "chemins machine non enregistrés comme chemins à jeton" \
  "$T/test_jeton_machine.py::test_register_enregistre_le_fournisseur_et_les_chemins_exacts" \
  $G/noyau/jeton_machine.py '        aa.register_token_route(chemin)' '        pass'
temoin "purge des relevés sans épargner les relevés cités" \
  "$T/test_migration_v2.py::test_purge_epargne_les_releves_cites" \
  $G/noyau/routage.py $'        "AND id NOT IN (SELECT releve_id FROM demandes WHERE releve_id IS NOT NULL)",' $'        "",'
temoin "champ P5 obligatoire : un relevé de P4 en base ne se relit plus" \
  "$T/test_migration_v2.py::test_releves_p4_en_base_restent_lisibles" \
  $G/contrat/acp_poste_contrat/inventaire.py $'                                    "alias_documentes", "aucune"]] = None' \
  $'                                    "alias_documentes", "aucune"]]'
temoin "migration v1 → v2 : colonne ajoutée sans lire PRAGMA table_info" \
  "$T/test_migration_v2.py -k 'idempotente or concurrents'" \
  $G/noyau/base.py '            if colonne not in _colonnes(conn, table):' '            if True:'
temoin "suppression de la présence ET filtre des postes actifs retirés (poste révoqué notifié)" \
  "$T/test_presence_p5.py::test_revocation_sans_notification_hors_ligne" \
  $G/noyau/machines.py $'        conn.execute("DELETE FROM presence WHERE machine_id = ?", (ligne["id"],))\n        conn.execute("UPDATE ordres' \
  $'        conn.execute("UPDATE ordres' \
  $G/noyau/presence.py $'        "WHERE (m.etat = \'actif\') OR (m.id IS NULL AND p.source = \'simule\')").fetchall()' \
  $'        ).fetchall()' \
  $G/noyau/presence.py $'p.machine_id = ? AND p.hors_ligne_notifie = 0 AND ((m.etat = \'actif\') OR (m.id IS NULL AND "\n                "p.source = \'simule\'))"' \
  $'p.machine_id = ? AND p.hors_ligne_notifie = 0"'
temoin "grâce de redémarrage retirée" \
  "$T/test_presence_p5.py -k 'redemarrage or passerelle_relancee'" \
  $G/noyau/presence.py '    grace = reference_de_grace(conn)' '    grace = 0'
temoin "liste de secours routée comme celle du compte" \
  "$T/test_routage_p5.py::test_liste_de_secours_refusee" \
  $G/noyau/routage.py '    if voie == "poste-codex" and releve.origine_liste in LISTES_DE_SECOURS and not (' \
  '    if False and not ('
temoin "politique du poste (poste.toml) ignorée par la résolution" \
  "$T/test_routage_p5.py -k 'interdit_par_le_poste or executant_refuse'" \
  $G/noyau/routage.py '    verifier_politique_du_poste(contexte, voie, modele, effort, palier)' '    pass'
temoin "relevé en échec : l'ancien relevé reste routable" \
  "$T/test_routage_p5.py::test_voie_indisponible" \
  $G/noyau/routage.py '    if releve.etat not in (None, "ok"):' '    if False:'
temoin "connexion au compte de l'abonnement non vérifiée" \
  "$T/test_routage_p5.py -k 'voie_non_connectee or catalogue_embarque_sans_compte'" \
  $G/noyau/routage.py '    if etat_connexion not in CONNEXIONS_ADMISES[voie]:' '    if False:'
temoin "version de la CLI non vérifiée" \
  "$T/test_routage_p5.py::test_cli_hors_version" \
  $G/noyau/routage.py '    if not version.get("conforme"):' '    if False:'
temoin "efforts inconnus non refusés avant usage" \
  "$T/test_routage_p5.py::test_efforts_inconnus_sans_typeerror" \
  $G/noyau/routage.py '    if fiche.supportedReasoningEfforts is None:' '    if False:'
temoin "interdit hors enveloppe levé sans la phrase de confirmation" \
  "$T/test_routage_p5.py::test_levee_d_interdit_exige_confirmation" \
  $G/noyau/routage.py '    if (leves or nouveaux_paliers) and confirmation != T.CONFIRMATION_DEPENSE:' '    if False:'
temoin "table de routage enregistrée malgré une entrée refusée" \
  "$T/test_routage_p5.py::test_validation_tout_ou_rien" \
  $G/noyau/routage.py '    if refus_par_entree:' '    if False:'
temoin "relevé accepté d'une autre origine" \
  "$T/test_routage_p5.py::test_releve_accepte" \
  $G/noyau/routage.py '        if ligne["voie"] != "poste-codex" or origine != "identique_au_catalogue_embarque":' '        if False:'

echo
echo "$TEMOINS témoins, $ECHECS anomalie(s)."
[ "$ECHECS" -eq 0 ]
