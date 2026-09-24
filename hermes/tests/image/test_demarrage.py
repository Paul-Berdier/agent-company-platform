"""Gardes de démarrage, managed scope et données du volume (acp_demarrage.py)."""

from __future__ import annotations

import json
import os
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
])
def test_un_emetteur_oidc_invalide_est_refuse(env_valide, emetteur, motif):
    env_valide["HERMES_DASHBOARD_OIDC_ISSUER"] = emetteur
    with pytest.raises(ad.Refus, match=motif):
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
    assert donnees["plugins"]["disabled"] == ["dashboard_auth/basic", "dashboard_auth/nous", "dashboard_auth/drain"]
    assert donnees["plugins"]["allow_deprecated_imports"] is False
    assert donnees["dashboard"]["oauth"]["self_hosted"]["issuer"] == "https://idp.acp.test:8443"
    assert donnees["dashboard"]["public_url"] == "https://hermes.acp.test"
    assert "@@ACP" not in texte


@pytest.mark.parametrize("remplacer, par, motif", [
    ("auto_decompose: false", "auto_decompose: true", "kanban.auto_decompose"),
    ("mode: manual", "mode: smart", "approvals.mode"),
    ("allow_deprecated_imports: false", "allow_deprecated_imports: \"false\"", "allow_deprecated_imports"),
    ("    - dashboard_auth/nous\n", "", "plugins.disabled"),
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
