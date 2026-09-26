"""Contrat de l'interface d'ACP (étape P3), sur le conteneur complet démarré par s6, avec une
session OIDC réelle émise par le faux fournisseur d'identité de l'image de test :

- le tableau de bord sert au navigateur acp-interface, acp-catalogue, acp-projets (étape P4),
  acp-poste et kanban, et JAMAIS hermes-achievements (décision D13) ;
- les bundles servis sont, octet pour octet, ceux du dépôt (construits depuis apps/interface) ;
- le thème « acp » est actif, sa définition est celle que Hermes normalise depuis le fichier déposé
  par 05-acp, et un autre thème ou une autre police choisis depuis le tableau de bord ne tiennent
  pas (managed scope) ;
- deux démarrages successifs du même volume laissent la managed scope, le thème, la persona et
  les greffons identiques.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from conftest import ENV_VALIDE, RACINE_HERMES, afficher, docker, lancer

NORMALISER = """
import json, yaml
from hermes_cli.web_server_dashboard import _normalise_theme_definition
brut = yaml.safe_load(open("/opt/data/dashboard-themes/acp.yaml", encoding="utf-8"))
print(json.dumps(_normalise_theme_definition(brut), ensure_ascii=False, sort_keys=True))
"""

EMPREINTES = (
    "sha256sum /etc/hermes/config.yaml /etc/hermes/.env /opt/data/dashboard-themes/acp.yaml /opt/data/SOUL.md "
    "/opt/data/acp/soul.sha256 && find /opt/hermes/plugins/acp-interface /opt/hermes/plugins/acp-catalogue "
    "/opt/hermes/plugins/acp-projets /opt/hermes/plugins/acp-poste /opt/acp -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum"
)


@pytest.fixture(scope="module")
def tableau(ressources, image_tests):
    """Faux fournisseur d'identité + Hermes (image de test) sur un réseau privé jetable."""
    reseau = ressources.reseau()
    idp = ressources.nom("idp")
    ressources.conteneurs.append(idp)
    docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
           "--entrypoint", "/opt/hermes/.venv/bin/python", image_tests,
           "/opt/acp-tests/outils/idp_factice.py", "--emetteur", "https://idp.acp.test:8443",
           "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem", "--cle", "/opt/acp-tests/ac/idp.key")
    volume = ressources.volume(image_tests)
    return lancer(ressources, image_tests, ENV_VALIDE, volume=volume, reseau=reseau)


def jeton(conteneur) -> str:
    sortie = conteneur.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                                 "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"],
                                verifier=True).stdout
    return json.loads(sortie)["id_token"]


def _octets_servis(conteneur, chemin: str, cle: str) -> bytes:
    commande = ["curl", "-s", "-o", "/tmp/acp-servi", "-w", "%{http_code}", "-H", f"Authorization: Bearer {cle}",
                f"http://127.0.0.1:9119{chemin}"]
    code = conteneur.executer(commande, verifier=True).stdout.strip()
    assert code == "200", (chemin, code)
    return conteneur.executer(["base64", "-w0", "/tmp/acp-servi"], verifier=True).stdout.encode("ascii")


def test_greffons_servis_au_navigateur(tableau):
    code, greffons = tableau.json("/api/dashboard/plugins", jeton=jeton(tableau))
    afficher("GET /api/dashboard/plugins", json.dumps(greffons, ensure_ascii=False, indent=1))
    assert code == 200
    par_nom = {g["name"]: g for g in greffons}
    assert {"acp-interface", "acp-catalogue", "acp-projets", "acp-poste", "kanban"} <= set(par_nom)
    assert "hermes-achievements" not in par_nom
    assert par_nom["acp-interface"]["tab"]["override"] == "/"
    assert par_nom["acp-interface"]["label"] == "Accueil" and par_nom["acp-interface"]["has_api"] is False
    assert par_nom["acp-catalogue"]["tab"] == {"path": "/catalogue", "position": "after:skills"}
    assert par_nom["acp-catalogue"]["label"] == "Catalogue" and par_nom["acp-catalogue"]["has_api"] is False
    assert par_nom["acp-projets"]["tab"] == {"path": "/projets", "position": "before:catalogue"}
    assert par_nom["acp-projets"]["label"] == "Projets" and par_nom["acp-projets"]["has_api"] is False
    assert all(par_nom[n]["source"] == "bundled" for n in ("acp-interface", "acp-catalogue", "acp-projets",
                                                            "acp-poste"))


def test_bundles_servis_identiques_au_depot(tableau):
    import base64

    cle = jeton(tableau)
    constats = []
    for nom in ("acp-interface", "acp-catalogue", "acp-projets"):
        for fichier in ("dist/index.js", "dist/style.css"):
            attendu = (RACINE_HERMES / "plugins" / nom / "dashboard" / fichier).read_bytes().replace(b"\r\n", b"\n")
            servi = base64.b64decode(_octets_servis(tableau, f"/dashboard-plugins/{nom}/{fichier}", cle))
            constats.append(f"{nom}/{fichier} : {hashlib.sha256(servi).hexdigest()[:16]} "
                            f"(dépôt {hashlib.sha256(attendu).hexdigest()[:16]})")
            assert servi == attendu, fichier
    afficher("bundles servis par le tableau de bord", "\n".join(constats))


def test_theme_acp_actif_et_epingle(tableau):
    cle = jeton(tableau)
    code, themes = tableau.json("/api/dashboard/themes", jeton=cle)
    assert code == 200 and themes["active"] == "acp"
    [acp] = [t for t in themes["themes"] if t["name"] == "acp"]
    normalise = json.loads(tableau.python(NORMALISER, verifier=True).stdout)
    assert acp["definition"] == normalise
    assert acp["label"] == "ACP"
    # Choisir un autre thème ou une police distante depuis le tableau de bord : Hermes répond « ok »
    # et l'écrit dans /opt/data/config.yaml, mais l'épingle de la managed scope l'emporte.
    code_put, reponse = tableau.json("/api/dashboard/theme", jeton=cle, methode="PUT", corps='{"name": "midnight"}')
    code_police, _ = tableau.json("/api/dashboard/font", jeton=cle, methode="PUT", corps='{"font": "inter"}')
    _, relus = tableau.json("/api/dashboard/themes", jeton=cle)
    _, police = tableau.json("/api/dashboard/font", jeton=cle)
    afficher("thème et police après PUT", f"PUT theme : {code_put} {reponse}\nPUT font : {code_police}\n"
             f"thème actif relu : {relus['active']}\npolice relue : {police}")
    assert code_put == 200 and relus["active"] == "acp"
    assert code_police == 200 and police == {"font": "theme"}


def test_deux_demarrages_identiques(tableau):
    avant = tableau.sh(EMPREINTES, verifier=True).stdout
    docker("restart", tableau.nom, delai=240)
    tableau.attendre_pret()
    apres = tableau.sh(EMPREINTES, verifier=True).stdout
    etat = tableau.executer(["cat", "/run/acp/etat-demarrage.json"], verifier=True).stdout
    afficher("empreintes avant et après redémarrage", f"{avant}\n{apres}\nétat : {etat[:600]}")
    assert avant == apres
    assert json.loads(etat)["soul"]["etat"] == "a_jour"
