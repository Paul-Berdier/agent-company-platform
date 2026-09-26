"""Bout en bout LOCAL sous Windows (cahier P5 § 14.5) : l'image Hermes locale + le VRAI poste.

Jamais en CI (les runners Windows n'exécutent pas de conteneurs Linux) ; lancé par ``scripts/e2e-poste-windows.ps1``.

- **Pile** (Docker Desktop) : l'image de test (``ACP_IMAGE_TESTS``) avec le faux fournisseur d'identité, le faux ntfy,
  le modèle factice (comme ``hermes/tests/contrat/test_machine_contrat.py``), et le bord TLS factice publié sur
  ``127.0.0.1:<port>`` pour ``hermes-acp.test`` ; seuil « hors ligne » de 10 s, émetteur à 5 s.
- **Poste** : ``acp-poste`` réel lancé nativement sous Windows, sous le COMPTE COURANT (``compte = "proprietaire"``,
  pas de compte dédié), par ``lancer_poste.py`` : DPAPI réel, Job Object réel, verrous réels, sur une racine
  temporaire ; **vrai Codex** sur un ``CODEX_HOME`` jetable et vide (aucun compte : « Liste de secours »), **vrai
  Claude Code** sur un ``CLAUDE_CONFIG_DIR`` jetable, sans jeton au coffre (``auth status`` n'est pas lancé).
  L'environnement du poste pointe ``USERPROFILE``, ``APPDATA`` et ``LOCALAPPDATA`` vers la racine temporaire : les CLI
  ne voient pas le profil du propriétaire. Aucune connexion à un compte, aucun identifiant lu.
- **Gestes du propriétaire** : par ses routes (session OIDC du faux fournisseur, en bouclage local du conteneur),
  celles qu'appelle la page Poste : code d'enrôlement, confirmation de l'empreinte, « Relever maintenant »,
  révocation.

Étapes vérifiées : diagnostic réseau (HTTPS, autorité de test) ; enrôlement (empreinte identique) ; « À confirmer »
sans inventaire ; confirmation ; « En ligne » et premier inventaire (liste de secours) ; ordre « releve » → nouvel
inventaire ; poste tué → « Hors ligne » et UNE notification ; relance → en ligne ; révocation pendant l'attente →
jeton effacé, arrêt (code 0) ; aucun jeton ni code dans les journaux (poste, Hermes, bord) ; ports en écoute des
processus du poste et de leurs enfants échantillonnés chaque seconde (tout écouteur vu est consigné tel quel).

Sortie : un rapport JSON (``--preuves``), sans jeton ni chemin de profil.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ICI = Path(__file__).resolve()
RACINE_DEPOT = ICI.parents[4]
sys.path[:0] = [str(RACINE_DEPOT / "hermes" / "tests" / "contrat"), str(RACINE_DEPOT / "apps" / "poste" / "src"),
                str(RACINE_DEPOT / "hermes" / "plugins" / "acp-poste" / "contrat")]

import conftest as pile  # noqa: E402  (outillage Docker des tests de contrat de l'image)

from acp_poste.chemins import Emplacements  # noqa: E402
from acp_poste.sondes_codex import ecrire_config_toml  # noqa: E402

PYTHON_CONTENEUR = "/opt/hermes/.venv/bin/python"
P = "/api/plugins/acp-poste"
SEUIL_S = 10
MODELE = """\
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""
ECHANTILLONNEUR = r"""
param([int]$Racine, [string]$Journal, [string]$Arret)
while (-not (Test-Path -LiteralPath $Arret)) {
    $tous = @(Get-CimInstance -ClassName Win32_Process | Select-Object ProcessId, ParentProcessId)
    $pids = New-Object 'System.Collections.Generic.HashSet[int]'
    [void]$pids.Add($Racine)
    do {
        $avant = $pids.Count
        foreach ($p in $tous) { if ($pids.Contains([int]$p.ParentProcessId)) { [void]$pids.Add([int]$p.ProcessId) } }
    } while ($pids.Count -ne $avant)
    $tcp = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $pids.Contains([int]$_.OwningProcess) })
    $udp = @(Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object { $pids.Contains([int]$_.OwningProcess) })
    $ligne = [ordered]@{ t = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(); processus = $pids.Count;
        tcp_ecoute = @($tcp | ForEach-Object { '{0}:{1} pid={2}' -f $_.LocalAddress, $_.LocalPort, $_.OwningProcess });
        udp = @($udp | ForEach-Object { '{0}:{1} pid={2}' -f $_.LocalAddress, $_.LocalPort, $_.OwningProcess }) }
    Add-Content -LiteralPath $Journal -Value ($ligne | ConvertTo-Json -Compress) -Encoding UTF8
    Start-Sleep -Milliseconds 1000
}
"""


def attendre(predicat, delai: float, message: str, pas: float = 0.5):
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


class BoutEnBout:
    def __init__(self, options: argparse.Namespace) -> None:
        self.options = options
        self.ressources = pile.Ressources()
        self.temporaire = Path(tempfile.mkdtemp(prefix="acp-e2e-poste-"))
        self.racine = self.temporaire / "racine"
        self.emplacements = Emplacements.de_test(self.racine)
        self.preuves: Dict[str, Any] = {"etapes": []}
        self.processus: List[subprocess.Popen] = []
        self.hermes: Optional[pile.Conteneur] = None

    # ------------------------------------------------------------------ pile
    def monter_pile(self) -> None:
        image = self.options.image_tests
        reseau = self.ressources.reseau()
        idp = self.ressources.nom("idp")
        self.ressources.conteneurs.append(idp)
        pile.docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
                    "--entrypoint", PYTHON_CONTENEUR, image, "/opt/acp-tests/outils/idp_factice.py", "--emetteur",
                    "https://idp.acp.test:8443", "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem",
                    "--cle", "/opt/acp-tests/ac/idp.key")
        self.ntfy = self.ressources.nom("ntfy")
        self.ressources.conteneurs.append(self.ntfy)
        pile.docker("run", "-d", "--name", self.ntfy, "--network", reseau, "--network-alias", "ntfy.acp.test",
                    "--entrypoint", PYTHON_CONTENEUR, image, "/opt/acp-tests/outils/notif_factice.py", "--port", "443",
                    "--certificat", "/opt/acp-tests/ac/ntfy.pem", "--cle", "/opt/acp-tests/ac/ntfy.key",
                    "--journal", "/tmp/ntfy-e2e.jsonl")
        env = dict(pile.ENV_VALIDE, ACP_NOTIFICATIONS="ntfy", ACP_NTFY_SERVEUR="https://ntfy.acp.test",
                   ACP_NTFY_SUJET="acp_sujet_e2e_poste", ACP_NTFY_JETON="jeton-de-test-e2e")
        volume = self.ressources.volume(image, {"config.yaml": MODELE})
        self.hermes = pile.lancer(self.ressources, image, env, volume=volume, reseau=reseau)
        self.hermes.executer(["sh", "-c", "echo '{}' > /tmp/acp-scenarios.json"], utilisateur="hermes", verifier=True)
        pile.docker("exec", "-d", "-u", "hermes", self.hermes.nom, PYTHON_CONTENEUR,
                    "/opt/acp-tests/outils/modele_factice.py", "--port", "18080", "--journal",
                    "/tmp/modele-factice.jsonl", "--scenarios", "/tmp/acp-scenarios.json")
        pile.attendre_modele_factice(self.hermes, "/tmp/modele-factice.jsonl")
        for cle, valeur in (("emetteur_intervalle_s", "5"), ("seuil_hors_ligne_s", str(SEUIL_S))):
            sortie = self.hermes.executer([PYTHON_CONTENEUR, "/opt/acp-tests/outils/poste_simule.py", "reglage", cle,
                                           valeur], utilisateur="hermes", delai=120)
            assert sortie.returncode == 0, sortie.stderr[-2000:]
        self.bord = self.ressources.nom("bord")
        self.ressources.conteneurs.append(self.bord)
        pile.docker("run", "-d", "--name", self.bord, "--network", reseau, "-p", f"127.0.0.1:{self.options.port}:443",
                    "--entrypoint", PYTHON_CONTENEUR, image, "-u", "/opt/acp-tests/outils/bord_factice.py", "--port",
                    "443", "--certificat", "/opt/acp-tests/ac/bord.pem", "--cle", "/opt/acp-tests/ac/bord.key",
                    "--journal", "/tmp/bord.jsonl", "--route", f"hermes-acp.test={self.hermes.nom}:9119")
        attendre(lambda: "[bord-factice] port 443" in pile.docker("logs", self.bord, verifier=False).stdout, 60,
                 "bord factice non démarré")
        self.autorite = self.temporaire / "ac.pem"
        pile.docker("cp", f"{self.bord}:/opt/acp-tests/ac/ac.pem", str(self.autorite))

    def api(self, methode: str, chemin: str, corps: Optional[Any] = None):
        jeton = json.loads(self.hermes.executer(
            ["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
             "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"], verifier=True).stdout)["id_token"]
        commande = ["curl", "-s", "-o", "/tmp/acp-reponse-e2e", "-w", "%{http_code}", "-X", methode,
                    f"http://127.0.0.1:9119{P}{chemin}", "-H", f"Authorization: Bearer {jeton}"]
        if corps is not None:
            commande += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(corps, ensure_ascii=False)]
        code = int(self.hermes.executer(commande, verifier=True).stdout.strip())
        contenu = self.hermes.executer(["cat", "/tmp/acp-reponse-e2e"], verifier=True).stdout
        try:
            return code, json.loads(contenu)
        except ValueError:
            return code, contenu

    def vue(self) -> Dict[str, Any]:
        code, vue = self.api("GET", "/v1/poste")
        assert code == 200, vue
        return vue

    # ------------------------------------------------------------------ poste
    def environnement(self) -> Dict[str, str]:
        profil = self.temporaire / "profil"
        for sous in ("AppData/Roaming", "AppData/Local"):
            (profil / sous).mkdir(parents=True, exist_ok=True)
        garder = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "PATH",
                  "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS")
        env = {nom: os.environ[nom] for nom in garder if nom in os.environ}
        env.update({"USERPROFILE": str(profil), "HOME": str(profil), "APPDATA": str(profil / "AppData" / "Roaming"),
                    "LOCALAPPDATA": str(profil / "AppData" / "Local"), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        return env

    def version(self, argv: List[str], env: Dict[str, str]) -> str:
        sortie = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=60, cwd=self.temporaire)
        import re

        trouve = re.search(r"(\d+\.\d+\.\d+)", sortie.stdout)
        assert trouve, f"version illisible : {argv[0]}"
        return trouve.group(1)

    def ecrire_politique(self) -> None:
        env = self.environnement()
        codex_home = self.emplacements.acp_local / "codex-home"
        claude_config = self.emplacements.acp_local / "claude-config"
        codex_home.mkdir(parents=True, exist_ok=True)
        claude_config.mkdir(parents=True, exist_ok=True)
        version_codex = self.version([self.options.codex, "--version"], dict(env, CODEX_HOME=str(self.temporaire /
                                                                                                  "codex-version")))
        version_claude = self.version([self.options.claude, "--version"], dict(
            env, CLAUDE_CONFIG_DIR=str(self.temporaire / "claude-version"), DISABLE_UPDATES="1",
            DISABLE_AUTOUPDATER="1"))
        self.preuves["versions_locales"] = {"codex": version_codex, "claude": version_claude}
        # poste.toml exige une version testée de Claude Code d'au moins 2.1.248 (--restricted) : une installation plus
        # ancienne est déclarée avec ce minimum, et le poste doit alors publier un relevé « cli_hors_version ».
        from acp_poste.politique import VERSION_CLAUDE_MINIMALE, version_numerique

        if version_numerique(version_claude) < VERSION_CLAUDE_MINIMALE:
            self.preuves["claude_plus_ancien_que_le_minimum"] = True
            version_claude = ".".join(map(str, VERSION_CLAUDE_MINIMALE))
        texte = "\n".join([
            "# poste.toml du bout en bout local (compte du propriétaire, racine temporaire)",
            "version = 1",
            "[poste]", "nom = 'Poste de bout en bout'", "compte = 'proprietaire'",
            "[hermes]", f"origine = 'https://hermes-acp.test:{self.options.port}'", "attente_max_s = 5",
            "delai_connexion_s = 5",
            "[sondes]", "codex = true", "claude = true", "intervalle_s = 600", "delai_sonde_s = 60",
            "[codex]", f"executable = '{self.options.codex}'", f"home = '{codex_home}'",
            f"version_testee = '{version_codex}'",
            "[claude]", f"executable = '{self.options.claude}'", f"config_dir = '{claude_config}'",
            f"version_testee = '{version_claude}'",
            "[journal]", "niveau = 'detail'", ""])
        self.emplacements.politique.parent.mkdir(parents=True, exist_ok=True)
        self.emplacements.politique.write_text(texte, encoding="utf-8")
        ecrire_config_toml(codex_home)

    def poste(self, *argv: str, entree: Optional[str] = None, fond: bool = False):
        commande = [sys.executable, "-I", str(ICI.with_name("lancer_poste.py")), "--racine", str(self.racine),
                    "--autorite", str(self.autorite), "--", *argv]
        if fond:
            processus = subprocess.Popen(commande, env=self.environnement(), cwd=self.temporaire,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.processus.append(processus)
            return processus
        return subprocess.run(commande, env=self.environnement(), cwd=self.temporaire, input=entree,
                              capture_output=True, text=True, encoding="utf-8", timeout=180)

    def echantillonner(self, processus: subprocess.Popen, nom: str) -> tuple[Path, Path, subprocess.Popen]:
        script = self.temporaire / "echantillonneur.ps1"
        script.write_text(ECHANTILLONNEUR, encoding="utf-8-sig")
        journal = self.temporaire / f"ecoute-{nom}.jsonl"
        arret = self.temporaire / f"arret-{nom}"
        hote = shutil.which("pwsh") or shutil.which("powershell")
        echantillonneur = subprocess.Popen([hote, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                                            "-Racine", str(processus.pid), "-Journal", str(journal), "-Arret",
                                            str(arret)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return journal, arret, echantillonneur

    @staticmethod
    def lire_echantillons(journal: Path) -> Dict[str, Any]:
        lignes = []
        if journal.exists():
            for ligne in journal.read_text(encoding="utf-8-sig").splitlines():
                try:
                    lignes.append(json.loads(ligne))
                except ValueError:
                    continue
        vus = [l for l in lignes if l.get("tcp_ecoute") or l.get("udp")]
        return {"echantillons": len(lignes), "avec_ecouteur": len(vus),
                "ecouteurs": sorted({e for l in vus for e in (l.get("tcp_ecoute") or []) + (l.get("udp") or [])}),
                "processus_max": max((l.get("processus", 0) for l in lignes), default=0)}

    def etape(self, nom: str, **details: Any) -> None:
        entree = {"etape": nom, **details}
        self.preuves["etapes"].append(entree)
        print(json.dumps(entree, ensure_ascii=False), flush=True)

    # ------------------------------------------------------------------ parcours
    def parcourir(self) -> None:
        debut = time.monotonic()
        self.monter_pile()
        self.etape("pile_prete", duree_s=round(time.monotonic() - debut, 1), port=self.options.port)
        self.ecrire_politique()

        diagnostic = self.poste("diagnostic", "--reseau")
        assert diagnostic.returncode == 0, diagnostic.stderr
        rapport = json.loads(diagnostic.stdout)
        assert rapport["hermes"]["joignable"] is True, rapport["hermes"]
        assert rapport["politique"]["etat"] == "valide", rapport["politique"]
        self.etape("diagnostic_reseau", joignable=True, politique=rapport["politique"]["etat"],
                   codex=rapport["codex"]["version"], claude=rapport["claude"]["version"])

        code, cree = self.api("POST", "/v1/poste/enrolement", {})
        assert code == 201 and cree["code"].startswith("acpe_"), cree
        enrolement = self.poste("enroler", "--code-stdin", entree=cree["code"] + "\n")
        assert enrolement.returncode == 0, enrolement.stderr
        assert cree["code"] not in enrolement.stdout + enrolement.stderr
        vue = self.vue()
        empreinte = vue["machine"]["machine"]["empreinte"]
        machine_id = vue["machine"]["machine"]["id"]
        assert vue["poste"]["etat"] == "a_confirmer" and f"Empreinte : {empreinte}" in enrolement.stdout, vue
        assert (self.emplacements.secrets / "jeton-machine.dpapi").is_file()
        self.etape("enrole", etat="a_confirmer", empreinte_identique=True)

        servir = self.poste("servir", fond=True)
        journal_ecoute, arret_ecoute, echantillonneur = self.echantillonner(servir, "premier")
        time.sleep(8)
        assert self.vue()["inventaire"] is None, "aucun inventaire avant la confirmation"
        code, confirme = self.api("POST", "/v1/poste/confirmation", {"machine_id": machine_id, "empreinte": empreinte})
        assert code == 200, confirme
        confirme_a = time.monotonic()
        vue = attendre(lambda: (lambda v: v if v["poste"]["etat"] == "en_ligne" and v["inventaire"] else None)(
            self.vue()), 120, "poste en ligne avec un inventaire")
        premier_inventaire_s = round(time.monotonic() - confirme_a, 2)
        contenu = vue["inventaire"]["contenu"]
        code, routage = self.api("GET", "/v1/routage")
        badges = {voie: routage["voies"][voie]["badge"] for voie in routage["voies"]}
        self.etape("en_ligne", premier_inventaire_s=premier_inventaire_s, connexions=contenu["connexions"],
                   versions=contenu["versions"], bac_a_sable={k: contenu["bac_a_sable_codex"][k] for k in
                                                              ("readiness", "mode_lu", "origine_mode",
                                                               "ecriture_admise", "raison")},
                   badges=badges, alertes=vue["alertes"])
        assert badges.get("poste-codex") == "liste_de_secours", badges
        assert contenu["connexions"]["codex"] == "non_connecte" and contenu["connexions"]["claude"] == "jeton_absent"

        premier_id = vue["inventaire"]["id"]
        time.sleep(2)
        ordre_a = time.monotonic()
        code, ordre = self.api("POST", "/v1/poste/releve", {})
        assert code == 202, ordre
        attendre(lambda: self.vue()["inventaire"]["id"] != premier_id, 120, "inventaire après l'ordre « releve »")
        self.etape("ordre_releve", ordre_vers_inventaire_s=round(time.monotonic() - ordre_a, 2))
        (arret_ecoute).write_text("fin", encoding="ascii")
        echantillonneur.wait(30)
        self.preuves["ecoute_premier_service"] = self.lire_echantillons(journal_ecoute)

        subprocess.run(["taskkill", "/T", "/F", "/PID", str(servir.pid)], capture_output=True)
        servir.wait(30)
        tue_a = time.monotonic()
        attendre(lambda: self.vue()["poste"]["etat"] == "hors_ligne", 90, "poste hors ligne après l'arrêt forcé")
        hors_ligne_s = round(time.monotonic() - tue_a, 1)
        notifications = attendre(lambda: self.notifications(), 60, "notification « Poste hors ligne »")
        time.sleep(12)
        notifications = self.notifications()
        self.etape("hors_ligne", apres_s=hors_ligne_s, notifications=len(notifications))
        assert len(notifications) == 1, notifications

        relance = self.poste("servir", fond=True)
        attendre(lambda: self.vue()["poste"]["etat"] == "en_ligne", 60, "poste de nouveau en ligne")
        self.etape("relance", etat="en_ligne")
        time.sleep(3)
        revoque_a = time.monotonic()
        code, revoque = self.api("POST", "/v1/poste/revocation", {"machine_id": machine_id,
                                                                  "motif": "Fin du bout en bout local."})
        assert code == 200, revoque
        code_sortie = relance.wait(30)
        sortie, erreurs = relance.communicate(timeout=10)
        self.etape("revocation", code_sortie=code_sortie, arret_s=round(time.monotonic() - revoque_a, 2),
                   jeton_efface=not (self.emplacements.secrets / "jeton-machine.dpapi").exists())
        assert code_sortie == 0 and not (self.emplacements.secrets / "jeton-machine.dpapi").exists()

        self.balayer()

    def notifications(self) -> List[Dict[str, Any]]:
        brut = pile.docker("exec", self.ntfy, "sh", "-c", "cat /tmp/ntfy-e2e.jsonl 2>/dev/null", verifier=False).stdout
        return [n for n in (json.loads(l) for l in brut.splitlines() if l.strip()) if "Poste hors ligne" in
                n.get("corps", "")]

    def balayer(self) -> None:
        journal_poste = (self.emplacements.journal / "poste.jsonl").read_text(encoding="utf-8")
        journaux_hermes = self.hermes.journaux()
        bord = pile.docker("exec", self.bord, "cat", "/tmp/bord.jsonl", verifier=False).stdout
        base = self.hermes.executer([PYTHON_CONTENEUR, "-c", (
            "import glob\n"
            "d = b''.join(open(f, 'rb').read() for f in glob.glob('/opt/data/plugin-data/acp-poste/data.db*'))\n"
            "print(('acpm_' if b'acpm_' in d else '') + ' ' + ('acpe_' if b'acpe_' in d else ''), len(d))")],
            utilisateur="hermes", verifier=True).stdout
        trouve = {nom: [motif for motif in ("acpm_", "acpe_") if motif in texte]
                  for nom, texte in (("journal_poste", journal_poste), ("journaux_hermes", journaux_hermes),
                                     ("journal_bord", bord), ("base_greffon", base))}
        self.etape("balayage", **{nom: (motifs or "aucun") for nom, motifs in trouve.items()},
                   caracteres={"journal_poste": len(journal_poste), "journaux_hermes": len(journaux_hermes),
                               "journal_bord": len(bord)})
        assert not any(trouve.values()), trouve
        self.preuves["journal_poste_evenements"] = sorted({json.loads(l)["evenement"] for l in
                                                           journal_poste.splitlines()})

    def nettoyer(self) -> None:
        for processus in self.processus:
            if processus.poll() is None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(processus.pid)], capture_output=True)
        self.ressources.nettoyer()
        if not self.options.garder:
            shutil.rmtree(self.temporaire, ignore_errors=True)


def main(argv: List[str]) -> int:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--image-tests", default=os.environ.get("ACP_IMAGE_TESTS", "acp-hermes-tests:p5o"))
    analyseur.add_argument("--codex", required=True)
    analyseur.add_argument("--claude", required=True)
    analyseur.add_argument("--port", type=int, default=18443)
    analyseur.add_argument("--preuves", type=Path, required=True)
    analyseur.add_argument("--garder", action="store_true")
    options = analyseur.parse_args(argv)
    parcours = BoutEnBout(options)
    code = 1
    try:
        parcours.parcourir()
        parcours.preuves["resultat"] = "réussi"
        code = 0
    except AssertionError as exc:
        parcours.preuves["resultat"] = "échec"
        parcours.preuves["echec"] = str(exc)[:2000]
        print(f"ÉCHEC : {exc}", file=sys.stderr)
    finally:
        parcours.nettoyer()
        options.preuves.parent.mkdir(parents=True, exist_ok=True)
        options.preuves.write_text(json.dumps(parcours.preuves, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
