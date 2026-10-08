"""Gestes du propriétaire sur l'exécutant Linux, dans une session ``railway ssh`` (cahier P6 § 11, § 12.2, § 16).

- ``acp-poste connexion claude --stdin`` / ``connexion github --stdin`` : jeton lu sur l'entrée standard (ou en
  saisie masquée sans ``--stdin``), jamais en argument ; écrit de façon atomique en 0600 root sous
  ``/donnees/acp/secrets/`` (D92) ; seule son empreinte courte (SHA-256, 12 caractères) est affichée ; aucun
  redémarrage ;
- ``acp-poste connexion codex`` : écrit le ``config.toml`` du profil (stockage ``file``) s'il manque, puis lance
  ``codex -c cli_auth_credentials_store="file" login --device-auth`` sous l'UID ``acp-codex``, ``CODEX_HOME``
  imposé, en héritant de la console : le code d'appareil ne transite JAMAIS par Hermes ni par le journal ;
- ``acp-poste bundle <alias> <branche>`` : ``git bundle`` de la branche (``hermes/projet-<slug>`` ou
  ``hermes/<carte>``), 0600, avec son SHA-256 et sa tête, à rapatrier par ``scp`` (§ 12.2) ;
- ``acp-poste pause`` / ``reprise`` : pause locale (aucune nouvelle carte, aucune sonde ; une carte en cours
  s'arrête proprement, ``arret(pause_locale)``) ; à poser avant ``connexion codex`` ;
- ``acp-poste cartes`` : état local (carte en main, file de sortie, sessions), sans contenu ni secret.
"""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import json
import os
import sys
from typing import Callable

from .coffre import CoffreErreur, ecrire_atomiquement
from .contexte import Contexte
from .politique import Politique

JETON_MAX = 4096
LIBELLES = {"jeton-claude": "Jeton Claude (claude setup-token)", "jeton-github": "Jeton GitHub de lecture"}


def _lire_secret(invite: str, stdin: bool, lire: Callable[[str], str] | None) -> str:
    if stdin:
        return sys.stdin.readline().strip()
    return (lire or getpass.getpass)(invite).strip()


def deposer_jeton(contexte: Contexte, usage: str, *, stdin: bool,
                  lire: Callable[[str], str] | None = None) -> int:
    libelle = LIBELLES[usage]
    valeur = _lire_secret(f"{libelle} (collé, saisie masquée) : ", stdin, lire)
    if not valeur or len(valeur) > JETON_MAX or any(c.isspace() for c in valeur):
        print(f"{libelle} refusé : non vide, sans espace, {JETON_MAX} caractères au plus ; rien n'a été écrit.",
              file=sys.stderr)
        return 2
    try:
        contexte.coffre.ecrire(usage, valeur)
    except CoffreErreur as exc:
        print(str(exc), file=sys.stderr)
        return 2
    empreinte = hashlib.sha256(valeur.encode("utf-8")).hexdigest()[:12]
    print(f"{libelle} déposé sur le volume (root, 0600). Empreinte : {empreinte}. Aucun redémarrage nécessaire.")
    print("Effacez maintenant le presse-papiers de votre PC (et son historique, Win+V, s'il est actif).")
    return 0


def connexion_codex_linux(contexte: Contexte, politique: Politique) -> int:
    from .connexions import _console
    from .plateforme.linux import environnement_agent
    from .sondes_codex import ecrire_config_toml
    from .verrou import Verrou, VerrouOccupe

    if politique.codex is None:
        print("Section [codex] absente de executant.toml : connexion Codex impossible.", file=sys.stderr)
        return 2
    if not contexte.emplacements.pause_locale.exists():
        print("Posez d'abord « acp-poste pause » : aucune sonde ni carte ne doit lire CODEX_HOME pendant que codex "
              "login l'écrit.", file=sys.stderr)
        return 2
    try:
        verrou = Verrou(contexte.emplacements.verrou_codex).prendre()
    except VerrouOccupe:
        print("Codex est en cours d'utilisation sur l'exécutant : réessayez dans une minute.", file=sys.stderr)
        return 2
    try:
        try:
            etat = ecrire_config_toml(politique.codex.home, "linux")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        identite = contexte.identites.get("codex")
        if identite is not None and hasattr(os, "chown"):
            for chemin in (politique.codex.home, politique.codex.home / "config.toml"):
                os.chown(chemin, identite.uid, identite.gid)
            os.chmod(politique.codex.home, 0o700)
        print("config.toml du profil Codex " + ("écrit." if etat == "cree" else "déjà conforme."))
        lanceur = contexte.lanceurs_pour(politique).get("codex")
        if not lanceur:
            print("Codex CLI introuvable dans l'image : connexion non lancée.", file=sys.stderr)
            return 2
        env = (environnement_agent(identite, CODEX_HOME=politique.codex.home.as_posix()) if identite is not None
               else {"CODEX_HOME": str(politique.codex.home), "PATH": os.environ.get("PATH", "")})
        print("Ouvrez le lien affiché sur votre téléphone ou votre PC et saisissez le code (connexion par code "
              "d'appareil activée dans les réglages de sécurité ChatGPT). Le code ne passe pas par Hermes.")
        argv = [*lanceur, "-c", 'cli_auth_credentials_store="file"', "login", "--device-auth"]
        return asyncio.run(_console(argv, env, str(politique.codex.home)))
    finally:
        verrou.rendre()


def bundle(contexte: Contexte, politique: Politique, alias: str, branche: str) -> int:
    from .depots import Depots, ErreurDepot

    if politique.depot(alias) is None:
        print(f"Dépôt « {alias} » absent de la politique de l'exécutant.", file=sys.stderr)
        return 2
    from .balayage import valeurs_exactes

    e = contexte.emplacements
    depots = Depots(racine_depots=e.depots, racine_espaces=e.espaces, racine_bundles=e.bundles)
    try:
        # Relecture finale de P7 : l'historique emballé est balayé (motifs et valeurs exactes du coffre) ; un secret,
        # même retiré depuis, fait refuser le bundle.
        valeurs = valeurs_exactes(contexte.coffre, getattr(politique.codex, "home", None))
        fichier, empreinte, tete = depots.bundle(alias, branche, valeurs_exactes=valeurs)
    except ErreurDepot as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Bundle écrit : {fichier.name} (dossier des bundles de l'exécutant).")
    print(f"SHA-256 : {empreinte}")
    print(f"Tête de {branche} : {tete}")
    print("Rapatriez-le par scp avec la même clé SSH, puis « git bundle verify » et « git fetch » sur votre PC ; "
          "comparez la tête avec celle de l'onglet Poste.")
    return 0


def pause(contexte: Contexte, active: bool) -> int:
    marque = contexte.emplacements.pause_locale
    if active:
        ecrire_atomiquement(marque, b"pause locale\n")
        print("Pause locale posée : aucune nouvelle carte ni sonde ; une carte en cours s'arrête proprement.")
    else:
        try:
            marque.unlink()
        except FileNotFoundError:
            pass
        print("Pause locale levée : l'exécutant reprend ses réclamations.")
    return 0


def cartes(contexte: Contexte) -> int:
    from .sortie import FileSortie

    e = contexte.emplacements
    try:
        en_main = json.loads(e.carte.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        en_main = None
    file = []
    for fichier in FileSortie(e.sortie, e.sortie_refusees).en_attente():
        lu = FileSortie.lire(fichier)
        if lu:
            file.append({"route": lu[0], "carte": lu[1].get("carte"), "id_envoi": lu[1].get("id_envoi")})
    try:
        sessions = sorted(f.stem for f in e.sessions.iterdir() if f.suffix == ".json")
    except OSError:
        sessions = []
    rapport = {"carte_en_main": {k: en_main.get(k) for k in ("tableau", "carte", "run_id", "role", "voie", "etape")}
               if isinstance(en_main, dict) else None,
               "file_de_sortie": file, "sessions_locales": sessions[-50:],
               "pause_locale": e.pause_locale.exists()}
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    return 0
