"""Gardes de démarrage, managed scope et données du volume (acp_demarrage.py)."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

import acp_demarrage as ad

UID_HERMES = 10000


def _comme_hermes(*commande: str) -> subprocess.CompletedProcess:
    """Exécute une commande sous l'uid/gid de l'agent (10000), sans groupe supplémentaire."""
    def abandonner() -> None:
        os.setgroups([])
        os.setgid(UID_HERMES)
        os.setuid(UID_HERMES)

    return subprocess.run(list(commande), preexec_fn=abandonner, capture_output=True, text=True)


# ------------------------------------------------------------------------ environnement


def test_un_environnement_valide_est_accepte(env_valide):
    valeurs = ad.verifier_environnement(env_valide)
    assert valeurs.oidc_emetteur == "https://idp.acp.test:8443"
    assert valeurs.oidc_client == "acp-tableau"
    assert valeurs.oidc_portees == "openid profile email"
    assert valeurs.secret_client_fourni is False


@pytest.mark.parametrize("nom", [
    "API_SERVER_KEY", "API_SERVER_ENABLED", "HERMES_DASHBOARD_OAUTH_CLIENT_ID",
    "HERMES_DASHBOARD_PORTAL_URL", "HERMES_DASHBOARD_DRAIN_SECRET", "HERMES_BUNDLED_PLUGINS",
    "HERMES_ENABLE_PROJECT_PLUGINS", "HERMES_KANBAN_HOME", "HERMES_KANBAN_DB",
    "HERMES_ALLOW_ROOT_GATEWAY", "HERMES_DOCKER_EXEC_AS_ROOT", "HERMES_AUTH_JSON_BOOTSTRAP",
    "HERMES_UID", "PUID", "AUTO_UPDATE", "DASHBOARD_PASSWORD", "HTTPS_PROXY", "SSL_CERT_FILE",
    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME", "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
])
def test_une_variable_interdite_refuse_le_demarrage_meme_vide(env_valide, nom):
    env_valide[nom] = ""
    with pytest.raises(ad.Refus) as refus:
        ad.verifier_environnement(env_valide)
    assert f"la variable {nom} est interdite" in str(refus.value)
    assert "Retirez-la des variables Railway" in str(refus.value)


def test_hermes_managed_dir_est_refuse_en_premier(env_valide):
    env_valide["HERMES_MANAGED_DIR"] = "/tmp/ailleurs"
    env_valide["API_SERVER_KEY"] = "x"
    with pytest.raises(ad.Refus, match="HERMES_MANAGED_DIR est interdite"):
        ad.verifier_environnement(env_valide)


@pytest.mark.parametrize("emetteur, motif", [
    ("http://idp.acp.test", "doit être une URL en https"),
    ("https://127.0.0.1:8443", "adresse IP non publique"),
    ("https://localhost/realms/acp", "hôte local interdit"),
    ("https://10.0.0.4", "adresse IP non publique"),
    ("https://idp.acp.test/?a=b", "caractère refusé"),
    ("https://intrus@idp.acp.test", "caractère refusé"),
    ("https://idp.acp.test/../autre", "chemin ambigu"),
    (" https://idp.acp.test", "entourée d'espaces"),
    ("https://identite.railway.internal", "domaine privé de Railway interdit"),
    ("https://identite.railway.internal:9091", "domaine privé de Railway interdit"),
    ("https://<libellé-identite>.up.railway.app", "caractère refusé"),
])
def test_un_emetteur_oidc_invalide_est_refuse(env_valide, emetteur, motif):
    env_valide["HERMES_DASHBOARD_OIDC_ISSUER"] = emetteur
    with pytest.raises(ad.Refus, match=motif):
        ad.verifier_environnement(env_valide)


def test_une_url_publique_sur_le_domaine_prive_de_railway_est_refusee(env_valide):
    env_valide["HERMES_DASHBOARD_PUBLIC_URL"] = "https://hermes.railway.internal"
    with pytest.raises(ad.Refus, match="HERMES_DASHBOARD_PUBLIC_URL : domaine privé de Railway interdit"):
        ad.verifier_environnement(env_valide)


def test_les_variables_obligatoires_manquantes_sont_toutes_signalees(env_valide):
    for nom in ("HERMES_DASHBOARD_PUBLIC_URL", "HERMES_DASHBOARD_OIDC_ISSUER", "HERMES_DASHBOARD_OIDC_CLIENT_ID"):
        del env_valide[nom]
    with pytest.raises(ad.Refus) as refus:
        ad.verifier_environnement(env_valide)
    message = str(refus.value)
    for nom in ("HERMES_DASHBOARD_PUBLIC_URL", "HERMES_DASHBOARD_OIDC_ISSUER", "HERMES_DASHBOARD_OIDC_CLIENT_ID"):
        assert f"la variable {nom} est obligatoire et absente" in message


@pytest.mark.parametrize("nom, valeur", [
    ("S6_BEHAVIOUR_IF_STAGE2_FAILS", "0"),
    ("S6_STAGE2_HOOK", "true"),
    ("HERMES_HOME", "/tmp/ailleurs"),
    ("HERMES_WEB_DIST", "/opt/data/web"),
    ("HERMES_DASHBOARD_HOST", "127.0.0.1"),
    ("HERMES_DASHBOARD_PORT", "8080"),
    ("API_SERVER_HOST", "0.0.0.0"),
])
def test_une_valeur_imposee_par_l_image_ne_peut_pas_changer(env_valide, nom, valeur):
    env_valide[nom] = valeur
    with pytest.raises(ad.Refus, match=f"la variable {nom} vaut"):
        ad.verifier_environnement(env_valide)


@pytest.mark.parametrize("chemin", [
    "/opt/data/.local/bin:/usr/bin:/bin",
    "/usr/bin:/bin:/opt/data/.local/bin",
    "/usr/bin::/bin",
    "/tmp:/usr/bin",
])
def test_un_path_qui_sort_des_repertoires_systeme_est_refuse(env_valide, chemin):
    env_valide["PATH"] = chemin
    with pytest.raises(ad.Refus, match="la variable PATH contient"):
        ad.verifier_environnement(env_valide)


def test_le_path_de_l_image_est_admis(env_valide):
    env_valide["PATH"] = ("/command:/opt/hermes/bin:/opt/hermes/.venv/bin:/usr/local/sbin:"
                          "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    ad.verifier_environnement(env_valide)


def test_la_boucle_locale_explicite_est_admise_pour_l_api_server(env_valide):
    env_valide["API_SERVER_HOST"] = "127.0.0.1"
    ad.verifier_environnement(env_valide)


@pytest.mark.parametrize("portees, motif", [
    ("profile email", "openid"),
    ("openid  profile", "séparées par une espace"),
    ("openid openid", "en double"),
])
def test_des_portees_invalides_sont_refusees(env_valide, portees, motif):
    env_valide["HERMES_DASHBOARD_OIDC_SCOPES"] = portees
    with pytest.raises(ad.Refus, match=motif):
        ad.verifier_environnement(env_valide)


def test_un_secret_client_est_accepte_mais_jamais_recopie(env_valide):
    env_valide["HERMES_DASHBOARD_OIDC_CLIENT_SECRET"] = "s3cr3t-tres-long-0123456789"
    valeurs = ad.verifier_environnement(env_valide)
    assert valeurs.secret_client_fourni is True
    env = ad.valeurs_env_gere(valeurs)
    assert "HERMES_DASHBOARD_OIDC_CLIENT_SECRET" not in env
    assert "s3cr3t" not in ad.texte_env_gere(env)


def test_un_secret_client_mal_forme_est_refuse_sans_etre_affiche(env_valide):
    env_valide["HERMES_DASHBOARD_OIDC_CLIENT_SECRET"] = "avec espace"
    with pytest.raises(ad.Refus) as refus:
        ad.verifier_environnement(env_valide)
    assert "avec espace" not in str(refus.value)


# ------------------------------------------------------------------------ managed scope


def _modele() -> str:
    return Path("/opt/acp/gere/config.yaml").read_text(encoding="utf-8")


def test_le_modele_livre_produit_une_config_complete(valeurs):
    texte = ad.generer_config_geree(_modele(), valeurs)
    donnees = ad.charger_yaml(texte)
    assert donnees["kanban"]["auto_decompose"] is False
    assert donnees["kanban"]["dispatch_profiles"] == ["default"]
    assert donnees["approvals"]["mode"] == "manual"
    assert donnees["plugins"]["enabled"] == []
    assert donnees["plugins"]["disabled"] == ["dashboard_auth/basic", "dashboard_auth/nous", "dashboard_auth/drain",
                                              "hermes-achievements"]
    assert donnees["dashboard"]["theme"] == "acp" and donnees["dashboard"]["font"] == "theme"
    assert donnees["dashboard"]["hidden_plugins"] == []
    assert donnees["plugins"]["allow_deprecated_imports"] is False
    assert donnees["dashboard"]["oauth"]["self_hosted"]["issuer"] == "https://idp.acp.test:8443"
    assert donnees["dashboard"]["public_url"] == "https://hermes.acp.test"
    assert "@@ACP" not in texte


@pytest.mark.parametrize("remplacer, par, motif", [
    ("auto_decompose: false", "auto_decompose: true", "kanban.auto_decompose"),
    ("mode: manual", "mode: smart", "approvals.mode"),
    ("allow_deprecated_imports: false", "allow_deprecated_imports: \"false\"", "allow_deprecated_imports"),
    ("    - dashboard_auth/nous\n", "", "plugins.disabled"),
    ("    - hermes-achievements\n", "", "plugins.disabled"),
    ("  font: theme", "  font: inter", "dashboard.font"),
    ("  hidden_plugins: []", "  hidden_plugins: [acp-interface]", "dashboard.hidden_plugins"),
    ("  theme: acp", "  theme: default", "dashboard.theme"),
    ("  enabled: []", "  enabled: [acp-poste]", "plugins.enabled"),
    ('    secret: ""', '    secret: "fuite"', "aucun secret"),
])
def test_un_modele_altere_est_refuse(valeurs, remplacer, par, motif):
    modele = _modele()
    assert remplacer in modele
    with pytest.raises(ad.Refus, match=motif):
        ad.generer_config_geree(modele.replace(remplacer, par, 1), valeurs)


def test_un_modele_yaml_invalide_est_refuse(valeurs):
    with pytest.raises(ad.Refus, match="YAML"):
        ad.generer_config_geree(_modele() + "\n: : :\n  - [", valeurs)


def test_un_marqueur_manquant_ou_inconnu_est_refuse(valeurs):
    modele = _modele()
    with pytest.raises(ad.Refus, match="marqueurs"):
        ad.generer_config_geree(modele.replace('"@@ACP:HERMES_DASHBOARD_OIDC_SCOPES@@"', '"openid"'), valeurs)
    with pytest.raises(ad.Refus, match="marqueurs"):
        ad.generer_config_geree(modele + '\nextra: "@@ACP:INCONNU@@"\n', valeurs)


def test_le_modele_epingle_l_api_server_en_boucle_locale(valeurs):
    donnees = ad.charger_yaml(ad.generer_config_geree(_modele(), valeurs))
    assert donnees["platforms"]["api_server"]["extra"] == {"host": "127.0.0.1", "port": 8642}
    # Les deux clés font bien partie des épingles obligatoires vérifiées à chaque démarrage.
    epingles = dict(ad.EPINGLES_OBLIGATOIRES)
    assert epingles["platforms.api_server.extra.host"] == "127.0.0.1"
    assert epingles["platforms.api_server.extra.port"] == 8642


def test_la_managed_scope_est_installee_root_0644_et_relue(chemins, valeurs):
    resume = ad.installer_scope_geree(chemins, valeurs)
    for nom in ("config.yaml", ".env"):
        st = os.lstat(chemins.dossier_gere / nom)
        assert st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o644
    relu = ad.relire_env(chemins.dossier_gere / ".env")
    assert relu["HERMES_DASHBOARD_OIDC_ISSUER"] == "https://idp.acp.test:8443"
    assert relu["API_SERVER_HOST"] == "127.0.0.1"
    assert relu["HERMES_LANGUAGE"] == "fr"
    # Greffons de projet coupés, greffons groupés ramenés au chemin de l'image (valeur vide).
    assert relu["HERMES_ENABLE_PROJECT_PLUGINS"] == "0"
    assert relu["HERMES_BUNDLED_PLUGINS"] == ""
    for vide in ("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", "HERMES_DASHBOARD_OAUTH_CLIENT_ID", "HTTPS_PROXY",
                 "https_proxy", "HERMES_DASHBOARD_OIDC_CLIENT_SECRET"):
        assert relu[vide] == ""
    # Le magasin de certificats est épinglé sur celui du système, jamais vide.
    assert relu["SSL_CERT_FILE"] == relu["REQUESTS_CA_BUNDLE"] == "/etc/ssl/certs/ca-certificates.crt"
    assert relu["SSL_CERT_DIR"] == "/etc/ssl/certs"
    assert "kanban.auto_decompose" in resume["cles_config"]
    # Deux installations successives donnent des fichiers identiques (idempotence).
    avant = (chemins.dossier_gere / "config.yaml").read_bytes(), (chemins.dossier_gere / ".env").read_bytes()
    ad.installer_scope_geree(chemins, valeurs)
    assert avant == ((chemins.dossier_gere / "config.yaml").read_bytes(), (chemins.dossier_gere / ".env").read_bytes())


def test_une_managed_scope_modifiee_apres_coup_est_detectee(chemins, valeurs):
    ad.installer_scope_geree(chemins, valeurs)
    attendue = ad.preparer_scope_geree(chemins, valeurs)
    config = chemins.dossier_gere / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace("mode: manual", "mode: off"), encoding="utf-8")
    with pytest.raises(ad.Refus, match="ne correspond pas"):
        ad.verifier_scope_installee(chemins, attendue, valeurs)


def test_une_managed_scope_de_construction_ne_passe_pas_pour_celle_du_deploiement(chemins, valeurs):
    ad.installer_scope_geree(chemins, ad.VALEURS_VIDES, construction=True)
    with pytest.raises(ad.Refus, match="S6_STAGE2_HOOK"):
        ad.verifier_scope_installee(chemins, ad.preparer_scope_geree(chemins, valeurs), valeurs)


def test_l_uid_hermes_ne_peut_pas_ecrire_la_managed_scope(chemins, valeurs):
    ad.installer_scope_geree(chemins, valeurs)
    refus = _comme_hermes("sh", "-c", f"echo intrus >> {chemins.dossier_gere / '.env'}")
    assert refus.returncode != 0 and "Permission denied" in refus.stderr
    # Contrôle positif : l'uid hermes écrit bien là où il en a le droit.
    permis = _comme_hermes("touch", str(chemins.hermes_home / "controle"))
    assert permis.returncode == 0, permis.stderr


# ------------------------------------------------------------------------ /opt/data


def _ecrire(chemin: Path, texte: str) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")


@pytest.mark.parametrize("relatif, contenu", [
    ("nimportequoi/plugin.yaml", "name: acp-poste\n"),
    ("autre/plugin.yml", "name: ACP-Interface\n"),
    ("categorie/sous/plugin.yaml", "name: acp-poste\n"),
    ("portable/plugin.json", '{"name": "acp-poste"}'),
    ("ui/dashboard/manifest.json", '{"name": "acp-poste", "api": "plugin_api.py"}'),
])
def test_un_manifeste_qui_declare_un_nom_reserve_est_refuse(chemins, relatif, contenu):
    _ecrire(chemins.greffons_utilisateur / relatif, contenu)
    with pytest.raises(ad.Refus, match="nom réservé"):
        ad.inspecter(chemins.greffons_utilisateur)


def test_un_dossier_au_nom_reserve_est_refuse(chemins):
    _ecrire(chemins.greffons_utilisateur / "acp-poste" / "dashboard" / "manifest.json", '{"label": "x"}')
    with pytest.raises(ad.Refus, match="nom réservé"):
        ad.inspecter(chemins.greffons_utilisateur)


def test_un_dossier_de_categorie_au_nom_reserve_est_refuse_mais_pas_un_fichier_profond(chemins):
    _ecrire(chemins.greffons_utilisateur / "outil" / "src" / "acp-aide.py", "x = 1\n")
    ad.inspecter(chemins.greffons_utilisateur)
    _ecrire(chemins.greffons_utilisateur / "categorie" / "acp-poste" / "LISEZMOI", "x\n")
    with pytest.raises(ad.Refus, match="nom réservé"):
        ad.inspecter(chemins.greffons_utilisateur)


def test_un_lien_symbolique_est_refuse(chemins):
    chemins.greffons_utilisateur.mkdir()
    (chemins.greffons_utilisateur / "lien").symlink_to(chemins.hermes_home)
    with pytest.raises(ad.Refus, match="lien symbolique"):
        ad.inspecter(chemins.greffons_utilisateur)
    chemins.themes.symlink_to("/etc")
    with pytest.raises(ad.Refus, match="lien symbolique"):
        ad.inspecter(chemins.themes)


def test_un_theme_homonyme_est_refuse(chemins):
    _ecrire(chemins.themes / "maquillage.yaml", "name: acp\ncustomCSS: 'button{display:none}'\n")
    with pytest.raises(ad.Refus, match="thème"):
        ad.inspecter(chemins.themes, themes_livres=["acp.yaml"])


def test_un_greffon_utilisateur_ordinaire_est_signale_mais_admis(chemins):
    _ecrire(chemins.greffons_utilisateur / "outil" / "plugin.yaml", "name: outil\n")
    inspection = ad.inspecter(chemins.greffons_utilisateur)
    assert inspection.dossiers_premier_niveau == ["outil"]
    assert inspection.noms_declares == [("outil/plugin.yaml", "outil")]


def test_les_donnees_sont_verrouillees_et_le_theme_depose(chemins, valeurs):
    scope = ad.preparer_scope_geree(chemins, valeurs)
    _ecrire(chemins.greffons_utilisateur / "outil" / "plugin.yaml", "name: outil\n")
    for chemin in (chemins.greffons_utilisateur, chemins.greffons_utilisateur / "outil",
                   chemins.greffons_utilisateur / "outil" / "plugin.yaml"):
        os.chown(chemin, UID_HERMES, UID_HERMES)
    etat = ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)
    for racine in (chemins.greffons_utilisateur, chemins.themes, chemins.donnees_acp):
        for dossier, sous, fichiers in os.walk(racine):
            st = os.lstat(dossier)
            assert st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o755, dossier
            for nom in fichiers:
                st = os.lstat(Path(dossier) / nom)
                assert st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o644, nom
    assert (chemins.themes / "acp.yaml").read_bytes() == Path("/opt/acp/theme/acp.yaml").read_bytes()
    assert etat["themes_deposes"] == ["acp.yaml"]
    assert etat["greffons_utilisateur"]["dossiers"] == ["outil"]
    # L'uid hermes ne peut ni créer un greffon ni modifier le thème.
    assert _comme_hermes("mkdir", str(chemins.greffons_utilisateur / "nouveau")).returncode != 0
    assert _comme_hermes("sh", "-c", f"echo x >> {chemins.themes / 'acp.yaml'}").returncode != 0
    assert _comme_hermes("touch", str(chemins.greffons_utilisateur / "outil" / "intrus.py")).returncode != 0
    assert _comme_hermes("touch", str(chemins.hermes_home / "controle")).returncode == 0


def test_soul_absent_puis_amont_puis_divergent(chemins):
    os_livre = Path("/opt/acp/persona/SOUL.md").read_bytes()
    chemins.donnees_acp.mkdir(mode=0o755)
    cible = chemins.hermes_home / "SOUL.md"
    # 1. Absent : déposé.
    assert ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)["etat"] == "depose"
    assert cible.read_bytes() == os_livre and os.lstat(cible).st_uid == UID_HERMES
    # 2. Identique : à jour.
    assert ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)["etat"] == "a_jour"
    # 3. SOUL de l'image officielle (semé par stage2) : remplacé.
    cible.write_bytes(Path("/opt/hermes/docker/SOUL.md").read_bytes())
    assert ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)["etat"] == "depose"
    # 4. Une version déposée plus ancienne (empreinte du marqueur) : mise à jour.
    ancienne = b"Ancienne persona ACP.\n"
    cible.write_bytes(ancienne)
    (chemins.donnees_acp / "soul.sha256").write_text(ad.empreinte(ancienne) + "\n", encoding="ascii")
    assert ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)["etat"] == "depose"
    assert cible.read_bytes() == os_livre
    # 5. Modifié par le propriétaire : laissé tel quel, signalé divergent.
    cible.write_bytes(b"Persona du proprietaire.\n")
    etat = ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)
    assert etat["etat"] == "divergent"
    assert cible.read_bytes() == b"Persona du proprietaire.\n"
    # 6. Lien symbolique : jamais suivi.
    cible.unlink()
    cible.symlink_to("/etc/passwd")
    assert ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)["etat"] == "non_ordinaire"
    assert os.path.islink(cible)


def test_l_etat_du_demarrage_est_ecrit_par_root(chemins, valeurs):
    scope = ad.preparer_scope_geree(chemins, valeurs)
    etat = ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)
    cible = ad.ecrire_etat(chemins, etat)
    st = os.lstat(cible)
    assert st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o644
    relu = json.loads(cible.read_text(encoding="utf-8"))
    assert relu["soul"]["etat"] == "depose"
    assert relu["scope_geree"]["config_sha256"] == ad.empreinte(scope.config)


# ------------------------------------------- variables interdites injectées dans /opt/data


def test_une_variable_interdite_dans_le_env_du_volume_est_trouvee(chemins):
    (chemins.hermes_home / ".env").write_text(
        "OPENAI_API_KEY=legitime\nHERMES_MANAGED_DIR=/opt/data/faux-gere\n", encoding="utf-8")
    trouvees = ad.variables_interdites_dans_le_volume(chemins)
    assert [(f.name, n) for f, n, _ in trouvees] == [(".env", "HERMES_MANAGED_DIR")]
    with pytest.raises(ad.Refus, match="HERMES_MANAGED_DIR"):
        ad.refuser_variables_du_volume(chemins)


def test_les_env_de_profils_sont_aussi_inspectes(chemins):
    profil = chemins.hermes_home / "profiles" / "coder"
    profil.mkdir(parents=True)
    (profil / ".env").write_text("HERMES_BUNDLED_PLUGINS=/opt/data/greffons-intrus\n", encoding="utf-8")
    trouvees = ad.variables_interdites_dans_le_volume(chemins)
    assert [(str(f).endswith("profiles/coder/.env"), n) for f, n, _ in trouvees] == [
        (True, "HERMES_BUNDLED_PLUGINS")]


def test_un_env_sans_variable_interdite_ni_env_absent_est_accepte(chemins):
    # Absent : rien à signaler.
    assert ad.variables_interdites_dans_le_volume(chemins) == []
    (chemins.hermes_home / ".env").write_text(
        "OPENAI_API_KEY=legitime\nHERMES_CRON_AUTO_DELIVER_PLATFORM=telegram\n", encoding="utf-8")
    assert ad.variables_interdites_dans_le_volume(chemins) == []
    ad.refuser_variables_du_volume(chemins)  # ne lève pas


def test_les_trois_vecteurs_d_evasion_sont_couverts(chemins):
    (chemins.hermes_home / ".env").write_text(
        "HERMES_MANAGED_DIR=/opt/data/x\nHERMES_BUNDLED_PLUGINS=/opt/data/y\n"
        "HERMES_ENABLE_PROJECT_PLUGINS=1\n", encoding="utf-8")
    trouvees = ad.variables_interdites_dans_le_volume(chemins)
    assert sorted(n for _, n, _ in trouvees) == [
        "HERMES_BUNDLED_PLUGINS", "HERMES_ENABLE_PROJECT_PLUGINS", "HERMES_MANAGED_DIR"]


def test_la_cle_api_server_ecrite_par_l_image_n_est_pas_refusee(chemins):
    """API_SERVER_KEY est légitimement écrite dans /opt/data/.env par l'image
    (docker/stage2-hook.sh) : la garde étroite ne doit pas la confondre avec une injection."""
    (chemins.hermes_home / ".env").write_text(
        "API_SERVER_KEY=0123456789abcdef0123456789\nHERMES_DASHBOARD_BASIC_AUTH_USERNAME=x\n",
        encoding="utf-8")
    assert ad.variables_interdites_dans_le_volume(chemins) == []
    ad.refuser_variables_du_volume(chemins)  # ne lève pas


# ------------------------------------------------------------------ reprise des services s6


def _fausse_passerelle(scandir: Path, nom: str = "gateway-default") -> Path:
    """Reproduit l'emplacement de service d'une passerelle tel que le reconciler le crée :
    scripts et FIFO supervise/control propriété de l'agent (uid 10000)."""
    svc = scandir / nom
    (svc / "supervise").mkdir(parents=True)
    (svc / "event").mkdir()
    (svc / "log" / "supervise").mkdir(parents=True)
    (svc / "run").write_text("#!/command/with-contenv sh\nexec s6-setuidgid hermes hermes gateway run --replace\n",
                             encoding="utf-8")
    (svc / "finish").write_text("#!/command/with-contenv sh\nexit 0\n", encoding="utf-8")
    (svc / "type").write_text("longrun\n", encoding="utf-8")
    (svc / "log" / "run").write_text("#!/command/with-contenv sh\nexec s6-log /opt/data/logs\n", encoding="utf-8")
    os.mkfifo(svc / "supervise" / "control", 0o660)
    for chemin in (svc / "run", svc / "finish", svc / "log" / "run"):
        os.chmod(chemin, 0o755)
    for racine, sous, fichiers in os.walk(scandir):
        os.chown(racine, UID_HERMES, UID_HERMES)
        for f in fichiers:
            os.chown(Path(racine) / f, UID_HERMES, UID_HERMES)
    return svc


def test_reprendre_services_s6_rend_root_le_repertoire_et_les_scripts(chemins):
    scandir = chemins.hermes_home / "run-service"
    scandir.mkdir()
    os.chown(scandir, UID_HERMES, UID_HERMES)
    svc = _fausse_passerelle(scandir)
    # Un service interne et un lien statique ne doivent pas être touchés/suivis.
    (scandir / ".s6-svscan").mkdir()
    (scandir / "dashboard").symlink_to("/run/s6-rc/servicedirs/dashboard")

    resume = ad.reprendre_services_s6(scandir)
    assert resume["present"] is True and resume["passerelles"] == ["gateway-default"]

    # Répertoire de services et scripts d'exécution repris par root.
    for chemin in (scandir, svc, svc / "run", svc / "finish", svc / "type",
                   svc / "supervise", svc / "log", svc / "log" / "run"):
        assert os.lstat(chemin).st_uid == 0, chemin
    assert stat.S_IMODE(os.lstat(scandir).st_mode) == 0o755
    # La FIFO supervise/control reste à l'agent : il peut encore relancer par s6-svc -r.
    ctrl = os.lstat(svc / "supervise" / "control")
    assert ctrl.st_uid == UID_HERMES and stat.S_ISFIFO(ctrl.st_mode)
    # Le lien statique n'a pas été suivi ni transformé.
    assert os.path.islink(scandir / "dashboard")
    # Le run est enveloppé par la garde de relance et l'amont est préservé.
    run_texte = (svc / "run").read_text(encoding="utf-8")
    assert run_texte.splitlines()[1].strip() == ad._MARQUEUR_RUN_ACP
    assert "verifier-relance" in run_texte
    assert "gateway run --replace" in (svc / ".acp-amont-run").read_text(encoding="utf-8")

    # L'agent ne peut plus créer de service ni réécrire le run repris.
    assert _comme_hermes("mkdir", str(scandir / "intrus")).returncode != 0
    assert _comme_hermes("sh", "-c", f"echo x >> {svc / 'run'}").returncode != 0
    assert _comme_hermes("sh", "-c", f"rm -f {svc / 'type'}").returncode != 0


def test_reprendre_services_s6_est_idempotent_et_ne_double_pas_l_enveloppe(chemins):
    scandir = chemins.hermes_home / "run-service"
    scandir.mkdir()
    os.chown(scandir, UID_HERMES, UID_HERMES)
    svc = _fausse_passerelle(scandir)
    ad.reprendre_services_s6(scandir)
    amont1 = (svc / ".acp-amont-run").read_bytes()
    run1 = (svc / "run").read_bytes()
    ad.reprendre_services_s6(scandir)
    assert (svc / ".acp-amont-run").read_bytes() == amont1  # l'amont n'est pas ré-écrasé
    assert (svc / "run").read_bytes() == run1


def test_reprendre_services_s6_hors_de_s6_ne_fait_rien(chemins):
    resume = ad.reprendre_services_s6(chemins.hermes_home / "absent")
    assert resume == {"present": False, "passerelles": []}


def test_main_refuse_en_francais_avec_le_code_1(capsys, monkeypatch):
    monkeypatch.setattr(ad.os, "geteuid", lambda: 1000)
    assert ad.main(["gardes"]) == 1
    erreur = capsys.readouterr().err
    assert "[acp] REFUS : ce script doit tourner en root" in erreur
    assert "Démarrage arrêté (échec fermé)" in erreur
    assert ad.main(["inconnue"]) == 2


# ======================================================================= étape P2


NOUVELLES_INTERDITES = (
    "HERMES_TUI_TOOLSETS", "HERMES_BIN", "HERMES_ACCEPT_HOOKS", "HERMES_SAFE_MODE", "HERMES_YOLO_MODE",
    "HERMES_COPILOT_ACP_COMMAND", "HERMES_COPILOT_ACP_ARGS", "COPILOT_CLI_PATH", "HERMES_ALLOW_PRIVATE_URLS",
    "HERMES_PORTAL_BASE_URL", "NOUS_PORTAL_BASE_URL", "NOUS_INFERENCE_BASE_URL", "HERMES_GATEWAY_BOOTSTRAP_STATE",
)


def test_la_managed_scope_compte_50_cles_et_38_variables(chemins, valeurs):
    # 40 clés en P2 ; P3 ajoute dashboard.font et dashboard.hidden_plugins, puis les huit épingles
    # du serveur MCP context7 (mcp_servers.context7.*).
    resume = ad.installer_scope_geree(chemins, valeurs)
    assert len(resume["cles_config"]) == 50, resume["cles_config"]
    assert len(resume["cles_env"]) == 38, resume["cles_env"]
    assert [c for c in resume["cles_config"] if c.startswith("mcp_servers.")] == [
        "mcp_servers.context7.elicitation.enabled", "mcp_servers.context7.enabled",
        "mcp_servers.context7.sampling.enabled", "mcp_servers.context7.ssl_verify",
        "mcp_servers.context7.tools.include", "mcp_servers.context7.tools.prompts",
        "mcp_servers.context7.tools.resources", "mcp_servers.context7.url"]
    # Jamais les listes de skills : Hermes les lit dans le volume, sans la managed scope (C1, C2).
    assert not [c for c in resume["cles_config"] if c.startswith("skills.external_dirs") or c.startswith("skills.disabled")]


@pytest.mark.parametrize("remplacer, par, motif", [
    ("[browser, terminal, file, code_execution, computer_use, connections, cronjob, delegation, setup]",
     "[browser, file, code_execution, computer_use, connections, cronjob, delegation, setup]",
     "agent.disabled_toolsets"),
    ('coding_context: "off"', "coding_context: focus", "agent.coding_context"),
    ('coding_context: "off"', "coding_context: off", "agent.coding_context"),  # booléen pour PyYAML
    ('service_tier: ""', "service_tier: fast", "agent.service_tier"),
    ("api_server: [web, vision, skills, todo, memory, session_search, no_mcp]",
     "api_server: [hermes-api-server]", "platform_toolsets.api_server"),
    ("cli: [web, vision, skills, todo, memory, session_search, clarify, context7]", "cli: []",
     "platform_toolsets.cli"),
    # Étape P3 : cli sans context7 (no_mcp) ou avec un serveur de plus.
    ("cli: [web, vision, skills, todo, memory, session_search, clarify, context7]",
     "cli: [web, vision, skills, todo, memory, session_search, clarify, no_mcp]", "platform_toolsets.cli"),
    ("cli: [web, vision, skills, todo, memory, session_search, clarify, context7]",
     "cli: [web, vision, skills, todo, memory, session_search, clarify, context7, autre]", "platform_toolsets.cli"),
    # Étape P3 : les huit épingles de context7.
    ("url: https://mcp.context7.com/mcp", "url: https://mcp.context7.test/mcp", "mcp_servers.context7.url"),
    ("    enabled: true\n    # Certificat", "    enabled: false\n    # Certificat", "mcp_servers.context7.enabled"),
    ("ssl_verify: true", "ssl_verify: false", "mcp_servers.context7.ssl_verify"),
    ("    sampling:\n      enabled: false", "    sampling:\n      enabled: true", "mcp_servers.context7.sampling.enabled"),
    ("    elicitation:\n      enabled: false", "    elicitation:\n      enabled: true",
     "mcp_servers.context7.elicitation.enabled"),
    ("include: [resolve-library-id, query-docs]", "include: [resolve-library-id, query-docs, piege]",
     "mcp_servers.context7.tools.include"),
    ("      resources: false", "      resources: true", "mcp_servers.context7.tools.resources"),
    ("      prompts: false", "      prompts: true", "mcp_servers.context7.tools.prompts"),
    ("cron: [web, vision, skills, todo, memory, session_search, no_mcp]",
     "cron: [web, vision, skills, todo, memory, session_search, terminal, no_mcp]", "platform_toolsets.cron"),
    ("inline_shell: false", "inline_shell: true", "skills.inline_shell"),
    ("  write_approval: true\n  # Analyse", "  write_approval: false\n  # Analyse", "skills.write_approval"),
    ("guard_agent_created: true", "guard_agent_created: false", "skills.guard_agent_created"),
    ("memory:\n  # Toute écriture en mémoire par l'agent attend la validation du propriétaire\n"
     "  # (config_defaults.py:1292-1295) : la mémoire est injectée dans toutes les sessions.\n"
     "  write_approval: true",
     "memory:\n  write_approval: false", "memory.write_approval"),
    ("hooks_auto_accept: false", "hooks_auto_accept: true", "hooks_auto_accept"),
    ("allow_private_urls: false", "allow_private_urls: true", "security.allow_private_urls"),
    ("allow_lazy_installs: false", "allow_lazy_installs: true", "security.allow_lazy_installs"),
])
def test_epingles_p2_obligatoires(valeurs, remplacer, par, motif):
    modele = _modele()
    assert remplacer in modele, remplacer
    with pytest.raises(ad.Refus, match=re.escape(motif)):
        ad.generer_config_geree(modele.replace(remplacer, par, 1), valeurs)


@pytest.mark.parametrize("nom", NOUVELLES_INTERDITES)
def test_variables_p2_interdites(env_valide, nom):
    env_valide[nom] = ""
    with pytest.raises(ad.Refus) as refus:
        ad.verifier_environnement(env_valide)
    assert f"la variable {nom} est interdite" in str(refus.value)
    assert "Retirez-la des variables Railway" in str(refus.value)


def test_les_variables_p2_sont_epinglees_dans_le_env_gere(chemins, valeurs):
    ad.installer_scope_geree(chemins, valeurs)
    relu = ad.relire_env(chemins.dossier_gere / ".env")
    for nom in ("HERMES_TUI_TOOLSETS", "HERMES_BIN", "HERMES_ACCEPT_HOOKS", "HERMES_SAFE_MODE", "HERMES_YOLO_MODE",
                "HERMES_COPILOT_ACP_COMMAND", "HERMES_COPILOT_ACP_ARGS", "COPILOT_CLI_PATH"):
        assert relu[nom] == "", nom
    assert relu["HERMES_ALLOW_PRIVATE_URLS"] == "false"
    assert relu["HERMES_DISABLE_LAZY_INSTALLS"] == "1"


@pytest.mark.parametrize("nom, autre", [
    ("HERMES_WRITE_SAFE_ROOT", "/"),
    ("HERMES_DISABLE_LAZY_INSTALLS", "0"),
    ("HERMES_LAZY_INSTALL_TARGET", "/opt/data/.local/lib"),
    ("HERMES_TUI_DIR", "/opt/data/ui-tui"),
    ("XDG_RUNTIME_DIR", "/opt/data/run"),
])
def test_valeurs_imposees_p2(env_valide, nom, autre):
    env_valide[nom] = autre
    with pytest.raises(ad.Refus, match=f"la variable {nom} vaut « {re.escape(autre)} »"):
        ad.verifier_environnement(env_valide)
    del env_valide[nom]
    with pytest.raises(ad.Refus, match=f"la variable {nom} manque"):
        ad.verifier_environnement(env_valide)


@pytest.mark.parametrize("valeur, admis", [(None, True), ("0", True), ("1000", False), ("", False), ("10000", False)])
def test_railway_run_uid(env_valide, valeur, admis):
    if valeur is not None:
        env_valide["RAILWAY_RUN_UID"] = valeur
    if admis:
        ad.verifier_environnement(env_valide)
    else:
        with pytest.raises(ad.Refus, match="RAILWAY_RUN_UID"):
            ad.verifier_environnement(env_valide)


MOUNTINFO_AVEC = (
    "1400 1300 0:120 / / rw,relatime - overlay overlay rw\n"
    "1401 1400 253:1 /var/lib/docker/volumes/v/_data /opt/data rw,relatime - ext4 /dev/vda1 rw\n")
MOUNTINFO_SANS = "1400 1300 0:120 / / rw,relatime - overlay overlay rw\n"
MOUNTINFO_ECHAPPE = "1401 1400 253:1 / /opt/data\\040autre rw - ext4 /dev/vda1 rw\n"


@pytest.mark.parametrize("marqueur", ["RAILWAY_ENVIRONMENT_ID", "RAILWAY_DEPLOYMENT_ID", "RAILWAY_SERVICE_ID"])
def test_volume_railway(env_valide, tmp_path, marqueur):
    env_valide[marqueur] = "0b3c-identifiant"
    # Sans RAILWAY_VOLUME_MOUNT_PATH, ou avec un autre chemin : refus.
    with pytest.raises(ad.Refus, match="le volume du service doit être monté sur /opt/data"):
        ad.verifier_environnement(env_valide)
    env_valide["RAILWAY_VOLUME_MOUNT_PATH"] = "/data"
    with pytest.raises(ad.Refus, match="reçu « /data »"):
        ad.verifier_environnement(env_valide)
    env_valide["RAILWAY_VOLUME_MOUNT_PATH"] = "/opt/data"
    ad.verifier_environnement(env_valide)
    # La variable ne suffit pas : /opt/data doit être un vrai point de montage.
    for contenu, present in ((MOUNTINFO_AVEC, True), (MOUNTINFO_SANS, False), (MOUNTINFO_ECHAPPE, False)):
        fichier = tmp_path / "mountinfo"
        fichier.write_text(contenu, encoding="utf-8")
        if present:
            ad.verifier_montage(env_valide, fichier)
        else:
            with pytest.raises(ad.Refus, match="n'est pas un point de montage"):
                ad.verifier_montage(env_valide, fichier)
    with pytest.raises(ad.Refus, match="illisible"):
        ad.verifier_montage(env_valide, tmp_path / "absent")


def test_hors_railway_ni_volume_ni_montage_ne_sont_exiges(env_valide, tmp_path):
    ad.verifier_environnement(env_valide)
    fichier = tmp_path / "mountinfo"
    fichier.write_text(MOUNTINFO_SANS, encoding="utf-8")
    ad.verifier_montage(env_valide, fichier)
    assert ad.point_de_montage_present(fichier) is False
    fichier.write_text("1 0 0:1 / /opt/data\\040x rw - x x rw\n1 0 0:1 / /opt/data rw - x x rw\n", encoding="utf-8")
    assert ad.point_de_montage_present(fichier) is True


@pytest.mark.parametrize("repertoire", ["hooks", "scripts"])
def test_hooks_et_scripts_du_volume(chemins, valeurs, repertoire):
    scope = ad.preparer_scope_geree(chemins, valeurs)
    racine = chemins.hermes_home / repertoire
    piege = racine / "intrus" / "handler.py" if repertoire == "hooks" else racine / "intrus.py"
    _ecrire(piege, "import os\nos.system('id')\n")
    os.chown(racine, UID_HERMES, UID_HERMES)
    avant = _empreinte_arbre(chemins.hermes_home)
    with pytest.raises(ad.Refus, match=f"{racine} n'est pas vide"):
        ad.refuser_repertoires_executes(chemins)
    with pytest.raises(ad.Refus, match="doit rester vide sur Railway"):
        ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)
    assert _empreinte_arbre(chemins.hermes_home) == avant  # refus AVANT toute écriture
    # Vide : repris par root, et l'agent ne peut plus y déposer de fichier.
    import shutil

    shutil.rmtree(racine)
    racine.mkdir()
    os.chown(racine, UID_HERMES, UID_HERMES)
    etat = ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES, commit="0123abc")
    for nom in ("hooks", "scripts"):
        st = os.lstat(chemins.hermes_home / nom)
        assert st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o755, nom
        assert _comme_hermes("touch", str(chemins.hermes_home / nom / "intrus")).returncode != 0
    # Schéma 2 en P2 ; 3 depuis P3 (bloc catalogue ajouté, rien de retiré).
    assert etat["schema"] == 3 and etat["deploiement"] == {"commit": "0123abc"}
    assert etat["repertoires_executes"]["hooks"]["vide"] is True
    # Un lien symbolique à la place du répertoire est refusé.
    shutil.rmtree(racine)
    racine.symlink_to("/tmp")
    with pytest.raises(ad.Refus, match="lien symbolique"):
        ad.refuser_repertoires_executes(chemins)


@pytest.mark.parametrize("relatif", ["hooks/intrus/handler.py", "scripts/tache.py"])
def test_hooks_et_scripts_des_profils(chemins, valeurs, relatif):
    """Correction de la relecture P2 : une seule passerelle sert tous les profils et exécute les
    scripts cron et les crochets PROPRES à chaque profil (cron/scheduler_script.py:257-298 ;
    gateway/hooks.py:28-35). hooks/ et scripts/ de chaque profil sont donc exigés vides, puis
    repris par root, comme ceux de la racine."""
    import shutil

    scope = ad.preparer_scope_geree(chemins, valeurs)
    profil = chemins.hermes_home / "profiles" / "intrus"
    _ecrire(profil / "SOUL.md", "profil secondaire\n")
    _ecrire(profil / relatif, "import os\nos.system('id')\n")
    _ecrire(chemins.hermes_home / "profiles" / "sain" / "SOUL.md", "profil sain\n")
    subprocess.run(["chown", "-R", f"{UID_HERMES}:{UID_HERMES}", str(chemins.hermes_home)], check=True)
    repertoire = profil / relatif.split("/")[0]
    avant = _empreinte_arbre(chemins.hermes_home)
    with pytest.raises(ad.Refus, match=re.escape(f"{repertoire} n'est pas vide")):
        ad.refuser_repertoires_executes(chemins)
    with pytest.raises(ad.Refus, match="doit rester vide sur Railway"):
        ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)
    assert _empreinte_arbre(chemins.hermes_home) == avant  # refus AVANT toute écriture
    # Vidé : les hooks/ et scripts/ de CHAQUE profil sont repris par root et l'agent n'y écrit plus.
    shutil.rmtree(repertoire)
    etat = ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)
    assert etat["repertoires_executes"]["profils"] == ["intrus", "sain"]
    for nom in ("intrus", "sain"):
        for sous in ("hooks", "scripts"):
            chemin = chemins.hermes_home / "profiles" / nom / sous
            st = os.lstat(chemin)
            assert st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o755, chemin
            assert _comme_hermes("touch", str(chemin / "intrus")).returncode != 0, chemin
    # Contrôle positif : le profil lui-même reste à l'agent.
    assert _comme_hermes("touch", str(profil / "controle")).returncode == 0


def test_un_lien_symbolique_sous_profiles_est_refuse(chemins, valeurs, tmp_path):
    """Hermes suit un lien sous profiles/ (hermes_cli/profiles.py:349-366, is_dir()) : il
    exécuterait les hooks/ et scripts/ de la cible. Refusé, sans rien écrire."""
    scope = ad.preparer_scope_geree(chemins, valeurs)
    cible = tmp_path / "ailleurs"
    _ecrire(cible / "scripts" / "tache.py", "print('cron')\n")
    (chemins.hermes_home / "profiles").mkdir()
    (chemins.hermes_home / "profiles" / "detour").symlink_to(cible)
    with pytest.raises(ad.Refus, match="profiles/detour est un lien symbolique"):
        ad.refuser_repertoires_executes(chemins)
    with pytest.raises(ad.Refus, match="lien symbolique"):
        ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)
    assert (cible / "scripts" / "tache.py").is_file()
    # profiles/ lui-même remplacé par un lien : refusé aussi.
    (chemins.hermes_home / "profiles" / "detour").unlink()
    (chemins.hermes_home / "profiles").rmdir()
    (chemins.hermes_home / "profiles").symlink_to(tmp_path)
    with pytest.raises(ad.Refus, match="profiles est un lien symbolique"):
        ad.refuser_repertoires_executes(chemins)


def test_journal_des_gardes_nomme_les_profils(chemins, env_valide, capsys):
    _ecrire(chemins.hermes_home / "profiles" / "coder" / "SOUL.md", "x\n")
    ad.commande_gardes(chemins, env_valide)
    assert ("inspectés : vides, ainsi que hooks/ et scripts/ de 1 profil(s) (coder)."
            in capsys.readouterr().out)


def test_lazy_packages_non_vide_est_signale(chemins, valeurs):
    scope = ad.preparer_scope_geree(chemins, valeurs)
    paresseux = chemins.hermes_home / "lazy-packages"
    paresseux.mkdir()
    (paresseux / ".python-abi").write_text("3.12\n", encoding="utf-8")
    (paresseux / ".lock").write_text("", encoding="utf-8")
    assert ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)["lazy_packages"] == {"entrees": []}
    (paresseux / "edge_tts").mkdir()
    assert ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)["lazy_packages"] == {
        "entrees": ["edge_tts"]}


@pytest.mark.parametrize("sha, affiche", [
    ("0123456789abcdef0123456789abcdef01234567", "0123456789abcdef0123456789abcdef01234567"),
    (None, "inconnu"),
    ("pas-un-sha; rm -rf /", "inconnu"),
    ("0123456789abcdef\n[acp] faux message", "inconnu"),
    ("0123456789abcdef\n", "inconnu"),
])
def test_journal_commit_deploye(chemins, env_valide, capsys, sha, affiche):
    if sha is not None:
        env_valide["RAILWAY_GIT_COMMIT_SHA"] = sha
    ad.commande_gardes(chemins, env_valide)
    sortie = capsys.readouterr().out
    assert f"[acp] commit déployé : {affiche}\n" in sortie
    assert "managed scope régénérée : 50 clés de configuration et 38 variables" in sortie
    assert "hooks et " in sortie and "inspectés : vides." in sortie


# ------------------------------------------------------------------ diagnostiquer


def _empreinte_arbre(racine: Path) -> str:
    """Empreinte d'une arborescence (chemins, types, modes, propriétaires, tailles, dates,
    contenus), sans suivre de lien : prouve qu'une commande n'a RIEN écrit."""
    import hashlib

    h = hashlib.sha256()
    for dossier, sous, fichiers in sorted(os.walk(racine)):
        sous.sort()
        for nom in sorted(sous + fichiers):
            chemin = Path(dossier) / nom
            st = os.lstat(chemin)
            h.update(f"{chemin}|{st.st_mode}|{st.st_uid}|{st.st_gid}|{st.st_size}|{st.st_mtime_ns}\n".encode())
            if stat.S_ISREG(st.st_mode):
                h.update(chemin.read_bytes())
            elif stat.S_ISLNK(st.st_mode):
                h.update(os.readlink(chemin).encode())
    return h.hexdigest()


def _faux_pid1(racine: Path, env: dict, programme: str = "sleep") -> Path:
    """Faux /proc/1 : cmdline et environ séparés par des octets nuls, comme le noyau."""
    proc = racine / "proc1"
    proc.mkdir()
    (proc / "cmdline").write_bytes(programme.encode() + b"\0infinity\0")
    (proc / "environ").write_bytes(b"".join(f"{k}={v}".encode() + b"\0" for k, v in env.items()))
    return proc


def _chemins_diagnostic(chemins, tmp_path: Path, env: dict, *, programme: str = "sleep") -> "ad.Chemins":
    montages = tmp_path / "mountinfo"
    montages.write_text(MOUNTINFO_AVEC, encoding="utf-8")
    import dataclasses

    return dataclasses.replace(chemins, proc_pid1=_faux_pid1(tmp_path, env, programme), montages=montages,
                               env_s6=tmp_path / "s6-env-absent")


# Contenus INERTES : jamais exécutés, seulement lus par le diagnostic (qui doit les signaler).
VOLUME_PIEGE = {
    ".env": "OPENAI_API_KEY=legitime\nHERMES_MANAGED_DIR=/opt/data/faux-gere\n",
    "hooks/intrus/handler.py": "def handle(*a):\n    import os; os.system('id')\n",
    "hooks/intrus/HOOK.yaml": "name: intrus\nevents: [agent:start]\n",
    "scripts/tache.py": "print('cron')\n",
    "config.yaml": (
        "mcp_servers:\n  intrus:\n    command: /opt/data/bin/serveur\n    args: []\n"
        "hooks:\n  pre_tool_call:\n    - command: /opt/data/crochet.sh\n"
        "quick_commands:\n  shell:\n    type: exec\n    command: id\n  alias:\n    type: alias\n    target: /help\n"
        "tts:\n  provider: voix\n  providers:\n    voix:\n      type: command\n      command: /opt/data/tts.sh\n"),
    "profiles/coder/config.yaml": "stt:\n  maison:\n    type: command\n    command: /opt/data/stt.sh\n",
    # Correction de la relecture P2 : scripts/ d'un profil et tâches cron à script.
    "profiles/coder/scripts/tache.py": "print('cron du profil')\n",
    "profiles/coder/cron/jobs.json": json.dumps({"jobs": [
        {"id": "nettoyage", "schedule": "1m", "script": "nettoyage.sh", "no_agent": True},
        {"id": "resume", "schedule": "1d", "prompt": "Résume la journée."}]}),
    "cron/jobs.json": "\ufeff" + json.dumps({"jobs": {"veille": {"schedule": "5m", "monitor_script": "veille.py",
                                                               "prompt": "x"}}}),
    "lazy-packages/edge_tts/__init__.py": "x = 1\n",
    "lazy-packages/.python-abi": "3.12\n",
}


def test_diagnostiquer_rassemble_sans_ecrire(chemins, valeurs, tmp_path, env_valide, capsys):
    ad.installer_scope_geree(chemins, valeurs)
    env = dict(env_valide, RAILWAY_ENVIRONMENT_ID="env", RAILWAY_VOLUME_MOUNT_PATH="/opt/data", API_SERVER_KEY="x")
    diag = _chemins_diagnostic(chemins, tmp_path, env)
    for relatif, contenu in VOLUME_PIEGE.items():
        _ecrire(chemins.hermes_home / relatif, contenu)
    avant = (_empreinte_arbre(chemins.hermes_home), _empreinte_arbre(chemins.dossier_gere),
             _empreinte_arbre(tmp_path / "proc1"))
    code = ad.commande_diagnostiquer(diag)
    apres = (_empreinte_arbre(chemins.hermes_home), _empreinte_arbre(chemins.dossier_gere),
             _empreinte_arbre(tmp_path / "proc1"))
    sortie = capsys.readouterr().out
    print(sortie)
    assert code == 1
    assert avant == apres, "diagnostiquer a modifié quelque chose"
    assert not chemins.dossier_etat.exists()
    constats = [l for l in sortie.splitlines() if l.startswith("[acp] DIAGNOSTIC : ")]
    for motif in ("la variable API_SERVER_KEY est interdite",                 # environnement du PID 1
                  "définit la variable interdite HERMES_MANAGED_DIR",         # .env du volume
                  "/hooks n'est pas vide (« intrus »)",
                  "/scripts n'est pas vide (« tache.py »)",
                  "mcp_servers.intrus.command = « /opt/data/bin/serveur »",
                  "hooks non vide (pre_tool_call)",
                  "quick_commands.shell de type exec = « id »",
                  "tts.providers.voix.command (fournisseur de type command)",
                  "profiles/coder/config.yaml : stt.maison.command (fournisseur de type command)",
                  "lazy-packages contient des paquets (edge_tts)",
                  "profiles/coder/scripts n'est pas vide (« tache.py »)",
                  "profiles/coder/cron/jobs.json : la tâche cron « nettoyage » exécute un script "
                  "(script = « nettoyage.sh »)",
                  "/cron/jobs.json : la tâche cron « veille » exécute un script (monitor_script = « veille.py »)"):
        assert any(motif in l for l in constats), motif
    assert not any("quick_commands.alias" in l for l in constats)
    assert not any("« resume »" in l for l in constats)  # tâche sans script : non signalée
    assert not any(".python-abi" in l for l in constats)
    assert "[acp] diagnostic : source de l'environnement de référence : " in sortie
    assert "constat(s) ; code 1." in sortie


def test_diagnostiquer_un_volume_sain_rend_0(chemins, valeurs, tmp_path, env_valide, capsys):
    ad.installer_scope_geree(chemins, valeurs)
    env = dict(env_valide, RAILWAY_ENVIRONMENT_ID="env", RAILWAY_VOLUME_MOUNT_PATH="/opt/data",
               RAILWAY_GIT_COMMIT_SHA="0123456789abcdef0123456789abcdef01234567")
    diag = _chemins_diagnostic(chemins, tmp_path, env)
    _ecrire(chemins.hermes_home / "config.yaml", "model:\n  provider: custom\n")
    (chemins.hermes_home / "hooks").mkdir()
    (chemins.hermes_home / "lazy-packages").mkdir()
    (chemins.hermes_home / "lazy-packages" / ".python-abi").write_text("3.12\n", encoding="utf-8")
    assert ad.commande_diagnostiquer(diag) == 0
    sortie = capsys.readouterr().out
    assert "aucun constat ; code 0." in sortie
    assert "managed scope installée : déploiement." in sortie
    assert "commit déployé : 0123456789abcdef0123456789abcdef01234567." in sortie


def test_diagnostiquer_en_maintenance_accepte_la_scope_de_construction(chemins, tmp_path, env_valide, capsys):
    """En maintenance (Start Command), acp-gardes n'a pas tourné : /etc/hermes porte la scope de
    construction ; ce n'est pas un constat."""
    ad.installer_scope_geree(chemins, ad.VALEURS_VIDES, construction=True)
    diag = _chemins_diagnostic(chemins, tmp_path, env_valide)
    assert ad.commande_diagnostiquer(diag) == 0
    assert "managed scope installée : construction (valeurs de déploiement vides)." in capsys.readouterr().out


SCRIPT_DIAGNOSTIC = r"""
import dataclasses, sys
from pathlib import Path
sys.path.insert(0, "/opt/acp/bin")
import acp_demarrage as ad
c = ad.Chemins(dossier_gere=Path(sys.argv[1]), hermes_home=Path(sys.argv[2]), proc_pid1=Path(sys.argv[3]),
               env_s6=Path(sys.argv[4]), montages=Path(sys.argv[5]), dossier_etat=Path(sys.argv[6]))
raise SystemExit(ad.commande_diagnostiquer(c))
"""


def _diagnostiquer_sans_environnement(chemins, tmp_path: Path, proc1: Path, env_s6: Path):
    """``env -i`` : la session qui lance le diagnostic n'a AUCUNE variable (comme une session
    `railway ssh` dont la doc ne dit rien) ; seul l'environnement de référence compte."""
    montages = tmp_path / "mountinfo"
    montages.write_text(MOUNTINFO_AVEC, encoding="utf-8")
    return subprocess.run(
        ["env", "-i", "/opt/hermes/.venv/bin/python", "-I", "-B", "-c", SCRIPT_DIAGNOSTIC,
         str(chemins.dossier_gere), str(chemins.hermes_home), str(proc1), str(env_s6), str(montages),
         str(chemins.dossier_etat)], capture_output=True, text=True, timeout=120)


def test_diagnostiquer_source_environnement(chemins, valeurs, tmp_path, env_valide):
    ad.installer_scope_geree(chemins, valeurs)
    # 1. Maintenance : PID 1 = sleep infinity ; /proc/1/environ porte l'environnement Railway valide.
    proc1 = _faux_pid1(tmp_path, dict(env_valide, RAILWAY_SERVICE_ID="s", RAILWAY_VOLUME_MOUNT_PATH="/opt/data"))
    resultat = _diagnostiquer_sans_environnement(chemins, tmp_path, proc1, tmp_path / "s6-absent")
    print(resultat.stdout, resultat.stderr)
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert f"source de l'environnement de référence : {proc1 / 'environ'} (PID 1 hors de s6 : sleep infinity)" \
        in resultat.stdout
    assert "REFUS" not in resultat.stdout + resultat.stderr
    # 2. Sous s6 : PID 1 = s6-svscan ; l'environnement vient de /run/s6/container_environment.
    s6 = tmp_path / "s6-env"
    s6.mkdir()
    for nom, valeur in env_valide.items():
        # Comme s6-overlay : chaque fichier se termine par un saut de ligne (mesuré dans l'image,
        # « /opt/data\n ») ; with-contenv le retire. Sans ce « \n », le test passait sur un code
        # qui produisait 29 faux constats sur un vrai conteneur sain (relecture P2).
        (s6 / nom).write_text(valeur + "\n", encoding="utf-8")
    proc_s6 = tmp_path / "proc-s6"
    proc_s6.mkdir()
    (proc_s6 / "cmdline").write_bytes(b"/package/admin/s6/command/s6-svscan\0-d4\0--\0/run/service\0")
    resultat = _diagnostiquer_sans_environnement(chemins, tmp_path, proc_s6, s6)
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert f"source de l'environnement de référence : {s6} (PID 1 : " in resultat.stdout
    # 3. Aucune source lisible : « inconnue », code 1.
    proc_vide = tmp_path / "proc-vide"
    proc_vide.mkdir()
    resultat = _diagnostiquer_sans_environnement(chemins, tmp_path, proc_vide, tmp_path / "s6-absent")
    assert resultat.returncode == 1
    assert "source de l'environnement de référence : inconnue" in resultat.stdout
    assert "[acp] DIAGNOSTIC : source de l'environnement inconnue" in resultat.stdout


def test_lire_env_s6_retire_un_seul_saut_de_ligne_final(tmp_path):
    """Comme with-contenv (s6-envdir sans -n) : exactement UN « \n » final est retiré."""
    dossier = tmp_path / "env"
    dossier.mkdir()
    for nom, contenu in {"A": "/opt/data\n", "B": "deux\n\n", "C": "", "D": "\n", "E": "sans"}.items():
        (dossier / nom).write_text(contenu, encoding="utf-8")
    (dossier / "LIEN").symlink_to(dossier / "A")
    assert ad.lire_env_s6(dossier) == {"A": "/opt/data", "B": "deux\n", "C": "", "D": "", "E": "sans"}


def test_diagnostiquer_exige_root(capsys, monkeypatch):
    monkeypatch.setattr(ad.os, "geteuid", lambda: 10000)
    assert ad.main(["diagnostiquer"]) == 1
    assert "[acp] DIAGNOSTIC : ce script doit tourner en root" in capsys.readouterr().err
