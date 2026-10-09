"""Bout en bout LOCAL de l'étape P6 (cahier § 14.3) : l'image Hermes de test + le VRAI exécutant (image
executant/Dockerfile, cible « factice » : Codex et Claude Code remplacés par deux programmes Python pilotés par
scénario), sur un réseau Docker jetable. Rien d'autre n'est simulé : enrôlement par code, jeton machine, long-poll
``reclamer``, worktree, commit local par le superviseur root, vérification sous l'UID ``acp-verif``, contrôles des
fichiers de pilotage et des secrets, file de sortie, routes machine de P6 et routes du propriétaire.

Pile : faux fournisseur d'identité (session OIDC du propriétaire), faux ntfy en HTTPS, modèle factice de Hermes,
bord TLS factice devant le tableau de bord (``https://hermes-acp.test``, comme le bord de Railway), dépôt git distant
factice en HTTPS (``https://git.acp.test/proprietaire/jetable.git``, lecture seule, jamais GitHub). L'exécutant tourne
sous le seccomp Docker par défaut : RÉGIME B mesuré par sa propre sonde (voie Codex fermée, Claude seul), comme sur Railway
si R0 le confirme. Son image de test ajoute seulement l'autorité de test au magasin du système et une politique de
test (origine ``hermes-acp.test``, dépôt factice, vérification admise sans bac à sable).

Scénarios (mot ``[scenario:…]`` dans l'objectif du projet, lu par le faux Claude) :
1. une carte réclamée, exécutée, COMMITTÉE localement (auteur « ACP exécutant », aucun push), vérifiée, terminée ; le
   faux agent tente de lire les secrets du superviseur et ``/proc/1/environ`` : tout est refusé ;
2. une question → réponse du propriétaire → carte resservie, fil repris (``--resume``) → terminée ;
3. un secret dans le diff → branche ``quarantaine/<carte>``, carte bloquée, rien du secret chez Hermes ;
4. un fichier de pilotage (``.github/workflows``) → revue → refus du propriétaire → carte resservie avec le motif →
   corrigée → terminée ;
5. (relecture de P6) planification par le modèle factice de Hermes, implémentation par l'exécutant, puis relecture de
   REPLI par la même voie avec un autre modèle (D91) : le relecteur, sous son UID, lit le diff ET le code relus.
Puis : références du dépôt distant inchangées et aucune requête d'écriture ; aucun jeton dans les journaux (Hermes,
exécutant) ni dans la base du greffon. Les faux CLI ne prouvent que la plomberie, jamais la qualité d'un modèle.
"""

from __future__ import annotations

import json

import pytest

from banc import JETON_CLAUDE, JOURNAL_DEPOT, PYTHON, SECRET_FACTICE, Banc, attendre
from conftest import afficher, docker

NOMS_ENV_CLAUDE = {"HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN",
                   "DISABLE_UPDATES", "DISABLE_AUTOUPDATER", "DISABLE_TELEMETRY"}


@pytest.fixture(scope="module")
def banc(ressources, image_tests):
    b = Banc(ressources, image_tests)
    try:
        b.monter()
        b.construire_executant()
        b.demarrer_executant()
        yield b
    finally:
        b.nettoyer_image()


# =========================================================================== 0. mise en service


def test_mise_en_service_jetons_enrolement_regime_b(banc):
    remote_avant = banc.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
    banc.remote_avant = remote_avant
    vue = banc.mettre_en_service()
    executant = vue["executant"]
    afficher("exécutant réel vu par /v1/poste", json.dumps(executant, ensure_ascii=False, indent=1)[:4000])
    assert executant["plateforme"] == "linux" and executant["isolement"]["regime"] == "B"
    assert executant["isolement"]["uid_separes"] is True
    assert "poste-codex" in executant["voies_fermees"]


# =========================================================================== 1. carte exécutée, committée, terminée


def test_carte_executee_committee_verifiee_terminee(banc):
    projet = banc.lancer_projet("Bout en bout — simple", "simple")
    carte = banc.carte_exploration(projet["tableau"])
    banc.attendre_statut(projet["tableau"], carte["id"], "done")
    branche = f"hermes/{carte['id']}"
    journal = banc.depot_nu("log", "-1", "--format=%an%x09%ae%x09%s", branche)
    fichiers = banc.depot_nu("show", "--name-only", "--format=", branche)
    afficher("commit local de l'exécutant", journal + fichiers)
    auteur, courriel, sujet = journal.strip().split("\t")
    assert (auteur, courriel) == ("ACP exécutant", "executant@acp.invalid")
    assert sujet.startswith(f"exploration({carte['id']}):") and "Co-Authored-By" not in journal
    assert "NOTES-acp.md" in fichiers.split()
    appel = next(f for f in banc.faux() if f.get("scenario") == "simple")
    afficher("faux Claude : identité, environnement, lectures interdites",
             json.dumps({k: appel[k] for k in ("uid", "noms", "jeton", "lectures")}, ensure_ascii=False, indent=1))
    assert appel["uid"] == 10002 and appel["jeton"] is True
    assert set(appel["noms"]) <= NOMS_ENV_CLAUDE, set(appel["noms"]) - NOMS_ENV_CLAUDE
    assert appel["lectures"] and all(issue.startswith("refusé") for issue in appel["lectures"].values())
    assert "--restricted" in appel["argv"] and "--bare" not in appel["argv"]
    assert appel["cwd"] == f"/donnees/espaces/jetable/{carte['id']}"


# =========================================================================== 2. question, réponse, reprise


def test_question_reponse_puis_reprise_du_fil(banc):
    projet = banc.lancer_projet("Bout en bout — question", "question")
    carte = banc.carte_exploration(projet["tableau"])

    def question():
        code, liste = banc.api("GET", "/v1/questions")
        return next((q for q in liste["questions"] if q["carte"] == carte["id"]), None) if code == 200 else None

    posee = attendre(question, 240, f"question jamais posée ({banc.fin_journal()})")
    assert posee["texte"] == "Faut-il garder la compatibilité avec Python 3.10 ?"
    code, repondue = banc.api("POST", f"/v1/questions/{posee['id']}/reponse", {"reponse": "Oui, garde-la."})
    assert code == 200 and repondue["carte_debloquee"] is True, repondue
    banc.attendre_statut(projet["tableau"], carte["id"], "done")
    appels = [f for f in banc.faux() if f.get("scenario") == "question"]
    assert [a["phase"] for a in appels] == ["premiere", "reprise"]
    assert "--resume" in appels[1]["argv"] and appels[1]["argv"][appels[1]["argv"].index("--resume") + 1].startswith(
        "factice-question-")
    # La question n'avait rien écrit : aucun commit « wip » (rien à committer) ; la reprise committe le travail final.
    sujets = banc.depot_nu("log", "--format=%s", f"hermes/{carte['id']}").splitlines()
    assert sujets[0].startswith(f"exploration({carte['id']}):") and sujets[-1] == "initial"
    notes = banc.depot_nu("show", f"hermes/{carte['id']}:NOTES-acp.md")
    assert "Compatibilité Python 3.10 gardée" in notes


# =========================================================================== 3. secret : quarantaine et blocage


def test_secret_quarantaine_et_carte_bloquee(banc):
    projet = banc.lancer_projet("Bout en bout — secret", "secret")
    carte = banc.carte_exploration(projet["tableau"])
    banc.attendre_statut(projet["tableau"], carte["id"], "blocked")
    references = banc.depot_nu("for-each-ref", "--format=%(refname)", "refs/heads/")
    assert f"refs/heads/quarantaine/{carte['id']}" in references.split()
    assert f"refs/heads/hermes/{carte['id']}" not in references.split()
    code, liste = banc.api("GET", "/v1/questions")
    bloquee = next(b for b in liste["bloquees"] if b["carte"] == carte["id"])
    afficher("carte bloquée pour secret", json.dumps(bloquee, ensure_ascii=False, indent=1))
    assert SECRET_FACTICE not in json.dumps(liste)
    attendre(lambda: any("secret détecté" in n.get("corps", "") for n in banc.notifications()), 90,
             "notification « secret » jamais reçue")


# =========================================================================== 4. revue refusée, puis corrigée


def test_revue_de_pilotage_refusee_puis_corrigee(banc):
    projet = banc.lancer_projet("Bout en bout — pilotage", "pilotage")
    carte = banc.carte_exploration(projet["tableau"])
    banc.attendre_statut(projet["tableau"], carte["id"], "review")
    code, liste = banc.api("GET", "/v1/questions")
    revue = next(r for r in liste["revues"] if r["carte"] == carte["id"])
    assert revue["chemins"] == [".github/workflows/acp.yml"]
    code, refus = banc.api("POST", f"/v1/revues/{projet['tableau']}/{carte['id']}/refuser",
                           {"motif": "Ne touche pas aux workflows de CI."})
    assert code == 200, refus
    banc.attendre_statut(projet["tableau"], carte["id"], "done")
    appels = [f for f in banc.faux() if f.get("scenario") == "pilotage"]
    assert [a["phase"] for a in appels] == ["premiere", "reprise"]
    fichiers = banc.depot_nu("ls-tree", "-r", "--name-only", f"hermes/{carte['id']}").split()
    assert ".github/workflows/acp.yml" not in fichiers and "NOTES-acp.md" in fichiers


# =========================================================================== 4 bis. relecture (relecture de P6)


def test_relecture_lit_le_code_relu_et_son_diff(banc):
    """Haute (relecture de P6) : le greffon sert une relecture SANS branche de départ ; son worktree partait de la
    branche de base, et son diff, écrit root:root 0640, était illisible par l'agent : relecture à l'aveugle. Ici, de
    bout en bout : planification par le modèle factice de Hermes, implémentation par l'exécutant (voie Claude, régime
    B), puis relecture de REPLI par la même voie avec un autre modèle (D91) ; le faux Claude relecteur, sous l'UID
    10002, lit le diff et le code relus."""
    titre = "Bout en bout — relecture"
    # Modèles choisis par le plan (implémentation « sonnet », relecture « opus ») : la voie Codex étant fermée (régime
    # B), la relecture va à la même voie avec cet autre modèle (repli D91).
    plan = {"resume": "Écrire un fichier, puis le relire.", "decisions": ["Fichier texte"], "etapes": [
        {"ref": "e1", "titre": "Écrire relu.txt", "classe": "implementation", "voie": "poste-claude",
         "modele": "sonnet", "relecture_modele": "opus", "consigne": "Écrire le fichier relu.txt. [scenario:relu]",
         "effort": "low"}]}
    appel_plan = {"outil": "tool_call", "arguments": {"calls": [{"name": "projet_planifier", "arguments": plan}]}}
    appel_etat = {"outil": "tool_call", "arguments": {"calls": [{"name": "projet_etat", "arguments": {}}]}}
    scenarios = json.loads(banc.hermes.executer(["cat", "/tmp/acp-scenarios.json"], verifier=True).stdout or "{}")
    scenarios.update({
        f"rôle « planification » — projet « {titre} »": {"dans": "systeme", "etapes": [appel_plan],
                                                           "resume_final": "Plan posé."},
        f"rôle « synthese » — projet « {titre} »": {"dans": "systeme", "etapes": [appel_etat],
                                                      "resume_final": "Conclusion."}})
    banc.hermes.executer(["sh", "-c", "cat > /tmp/acp-scenarios.json"], utilisateur="hermes",
                         entree=json.dumps(scenarios, ensure_ascii=False), verifier=True)
    projet = banc.lancer_projet(titre, "relu-explo")

    def relecture():
        code, detail = banc.api("GET", f"/v1/projets/{projet['id']}")
        cartes = (detail or {}).get("projet", {}).get("cartes", []) if code == 200 else []
        # Carte CRÉÉE seulement : le détail sert aussi une carte réservée « à créer » (``carte`` nulle) entre la
        # réservation de sa demande et la création kanban ; la prendre faisait échouer la suite (StopIteration, CI
        # 37742327967 sur a16f00b, relecture finale de P7).
        return next((c for c in cartes if c.get("role") == "relecture" and c.get("carte")), None)

    try:
        carte = attendre(relecture, 300, "relecture jamais planifiée")
    except AssertionError as exc:
        _code, detail = banc.api("GET", f"/v1/projets/{projet['id']}")
        brut = banc.hermes.executer(["cat", "/tmp/modele-factice.jsonl"], verifier=False).stdout
        resultats = [r.get("resultats_outils") for r in (json.loads(l) for l in brut.splitlines() if l.strip())
                     if f"projet « {titre} »" in (r.get("section_acp") or "")]
        raise AssertionError(f"{exc} ; outils de la planification : {json.dumps(resultats, ensure_ascii=False)[:3000]}"
                             f" ; projet : {json.dumps(detail, ensure_ascii=False)[:1500]} ; journal : "
                             f"{banc.fin_journal()}") from None
    afficher("carte de relecture planifiée", json.dumps(carte, ensure_ascii=False, indent=1))
    banc.attendre_statut(projet["tableau"], carte["carte"], "done", delai=300)
    appel = next(f for f in banc.faux() if f.get("scenario") == "relecteur")
    afficher("faux Claude relecteur : identité, outils, textes lus",
             json.dumps({k: appel[k] for k in ("uid", "textes")}, ensure_ascii=False, indent=1))
    assert appel["uid"] == 10002 and "--add-dir" in appel["argv"]
    assert appel["argv"][appel["argv"].index("--tools") + 1] == "Read,Glob,Grep"
    assert appel["argv"][appel["argv"].index("--model") + 1] == "opus"  # repli D91 : autre modèle que « sonnet »
    assert "+contenu relu ACP-RELU-7C2B" in appel["textes"]["{add_dir}/diff.patch"], appel["textes"]
    assert appel["textes"]["relu.txt"] == "contenu relu ACP-RELU-7C2B\n", appel["textes"]


# =========================================================================== 5. aucun push, aucun jeton


def test_aucun_push_et_aucun_jeton_dans_les_journaux(banc):
    remote_apres = banc.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
    assert remote_apres == banc.remote_avant
    requetes = [json.loads(l) for l in docker("exec", banc.depot, "cat", JOURNAL_DEPOT).stdout.splitlines() if l]
    assert requetes and {r["methode"] for r in requetes} <= {"GET", "HEAD"}
    assert not any("receive-pack" in r["chemin"] for r in requetes)
    jeton_machine = banc.executant_sh("cat /donnees/acp/secrets/jeton-machine").strip()
    assert jeton_machine.startswith("acpm_")
    journaux_executant = docker("logs", banc.executant, verifier=False)
    textes = {
        "docker logs hermes": banc.hermes.journaux(),
        "base du greffon": banc.hermes.executer([PYTHON, "-c", (
            "import sqlite3, json\n"
            "c = sqlite3.connect('file:/opt/data/plugin-data/acp-poste/data.db?mode=ro', uri=True)\n"
            "t = [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]\n"
            "print(json.dumps({x: [list(map(str, l)) for l in c.execute(f'SELECT * FROM {x}')] for x in t}))\n")],
            utilisateur="hermes", verifier=True).stdout,
        "docker logs executant": journaux_executant.stdout + journaux_executant.stderr,
        "journal de l'exécutant": banc.executant_sh("cat /donnees/acp/journal/* 2>/dev/null || true"),
        "file de sortie": banc.executant_sh("cat /donnees/acp/sortie/* 2>/dev/null || true"),
    }
    for nom, texte in textes.items():
        for valeur in (jeton_machine, JETON_CLAUDE, SECRET_FACTICE):
            assert valeur not in texte, nom
        assert "acpe_" not in texte, nom
    etat = banc.acp_poste("cartes")
    afficher("état local de l'exécutant à la fin", etat.stdout[-2000:])
    afficher("bilan", json.dumps({"requetes_depot": len(requetes), "references_distantes": remote_apres.strip(),
                                  "tailles": {n: len(t) for n, t in textes.items()}}, ensure_ascii=False, indent=1))
