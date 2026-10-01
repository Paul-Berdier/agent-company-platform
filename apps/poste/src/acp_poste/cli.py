"""Commande ``acp-poste`` (cahier P5 § 6.3).

| Commande | Rôle | Réseau |
|---|---|---|
| ``servir`` | boucle du service (tâche planifiée) | Hermes ; OpenAI et Anthropic par les CLI |
| ``enroler [--code-stdin] [--remplacer]`` | échange un code d'enrôlement contre le jeton machine | Hermes |
| ``connexion codex`` / ``claude`` / ``bac-a-sable`` | gestes manuels du propriétaire | OpenAI / aucun / UAC |
| ``releve [--publier]`` | sondes une fois, inventaire imprimé (et publié) | comme ``servir`` |
| ``preuve model-list`` | archive du relevé ``model/list`` (preuve n° 1) | OpenAI |
| ``diagnostic [--reseau] [--isolement]`` | état du poste, sans chemin ni secret | ``--reseau`` : ``/api/health`` |
| ``journal [--lignes N]`` | fin du journal local | aucun |
| ``oublier-jeton`` | efface le jeton machine local | aucun |
| ``quotas`` | relevés de quotas (Codex, ligne d'état Claude) | comme ``releve`` |
| ``sonde-plateforme [--json]`` | exécutant Linux : sonde d'isolement (cahier P6 § 4.1), sans identifiant ni politique | aucun |
| ``connexion claude|github --stdin`` | exécutant Linux : jeton déposé en 0600 root sur le volume (D92) | aucun |
| ``bundle <alias> <branche>`` | exécutant Linux : ``git bundle`` d'une branche prête (§ 12.2) | aucun |
| ``pause`` / ``reprise`` / ``cartes`` | exécutant Linux : pause locale, état local des cartes | aucun |

Codes de sortie : 0 (normal, non enrôlé, révoqué), 1 (erreur imprévue ou Hermes injoignable), 2 (configuration
refusée), 3 (autre instance), 4 (jeton gardé mais refusé par la couture de Hermes). Tout message est en français ;
aucune commande n'imprime un jeton, un code ou un chemin de profil.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys

from . import __version__
from .chemins import EmplacementsIndisponibles, commande_poste
from .coffre import CoffreErreur
from .contexte import Contexte
from .journal import lire_fin
from .plateforme import PlateformeIndisponible

EPILOGUE = ("Poste Windows d'ACP (étape P5 : présence, catalogue, quotas ; aucune exécution de carte avant P6). "
            "Installation : packaging/poste ; documentation : apps/poste/README.md.")

# Messages d'argparse (Python 3.12) en français (relecture de P5 : une saisie erronée répondait en anglais). argparse
# les lit par son ``_`` (gettext) au moment de construire le parseur et d'analyser : ils ne sont remplacés que le
# temps de ces deux appels (:func:`_argparse_en_francais`), jamais pour le reste du processus.
_ARGPARSE_FR = {
    "usage: ": "utilisation : ",
    "%(heading)s:": "%(heading)s :",
    " (default: %(default)s)": " (par défaut : %(default)s)",
    "argument %(argument_name)s: %(message)s": "argument %(argument_name)s : %(message)s",
    "show program's version number and exit": "afficher la version du poste et quitter",
    "show this help message and exit": "afficher cette aide et quitter",
    "positional arguments": "arguments positionnels",
    "options": "options",
    "subcommands": "commandes",
    "unrecognized arguments: %s": "arguments non reconnus : %s",
    "not allowed with argument %s": "interdit avec l'argument %s",
    "ambiguous option: %(option)s could match %(matches)s": "option ambiguë : %(option)s peut désigner %(matches)s",
    "ignored explicit argument %r": "argument explicite ignoré : %r",
    "the following arguments are required: %s": "arguments obligatoires manquants : %s",
    "one of the arguments %s is required": "l'un des arguments %s est obligatoire",
    "expected one argument": "une valeur attendue",
    "expected at most one argument": "au plus une valeur attendue",
    "expected at least one argument": "au moins une valeur attendue",
    "unexpected option string: %s": "option inattendue : %s",
    "invalid %(type)s value: %(value)r": "valeur invalide (%(type)s attendu) : %(value)r",
    "invalid choice: %(value)r (choose from %(choices)s)": "choix invalide : %(value)r (choix possibles : %(choices)s)",
    "unknown parser %(parser_name)r (choices: %(choices)s)":
        "commande inconnue %(parser_name)r (choix possibles : %(choices)s)",
    "%(prog)s: error: %(message)s\n": "%(prog)s : commande refusée : %(message)s\n",
}
_ARGPARSE_FR_PLURIEL = {"expected %s argument": ("%s valeur attendue", "%s valeurs attendues")}


@contextlib.contextmanager
def _argparse_en_francais():
    ancien, ancien_pluriel = argparse._, argparse.ngettext

    def pluriel(singulier: str, pluriel_anglais: str, n: int) -> str:
        francais = _ARGPARSE_FR_PLURIEL.get(singulier)
        if francais is None:
            return ancien_pluriel(singulier, pluriel_anglais, n)
        return francais[0] if n == 1 else francais[1]

    argparse._ = lambda message: _ARGPARSE_FR.get(message, message)
    argparse.ngettext = pluriel
    try:
        yield
    finally:
        argparse._, argparse.ngettext = ancien, ancien_pluriel


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acp-poste", epilog=EPILOGUE)
    parser.add_argument("--version", action="version", version=f"acp-poste {__version__}")
    commandes = parser.add_subparsers(dest="commande", required=True)
    servir = commandes.add_parser("servir", help="Boucle du service : attente des ordres, relevés, inventaire")
    servir.add_argument("--plateforme", choices=("windows", "linux"),
                        help="Assertion de la plateforme (l'entrée de l'image passe « linux ») ; jamais un choix")
    enroler = commandes.add_parser("enroler", help="Enrôler ce poste auprès de Hermes (code de la page Poste)")
    enroler.add_argument("--code-stdin", action="store_true", help="Lire le code sur l'entrée standard")
    enroler.add_argument("--remplacer", action="store_true", help="Remplacer le jeton d'un enrôlement précédent")
    connexion = commandes.add_parser("connexion", help="Connexions manuelles du compte du poste")
    connexion.add_argument("cible", choices=("codex", "claude", "github", "bac-a-sable"))
    connexion.add_argument("--stdin", action="store_true", help="Lire le jeton sur l'entrée standard (jamais en "
                           "argument)")
    releve = commandes.add_parser("releve", help="Relever maintenant (sondes) et imprimer l'inventaire")
    releve.add_argument("--publier", action="store_true", help="Publier aussi l'inventaire sur Hermes")
    preuve = commandes.add_parser("preuve", help="Archiver une preuve (cahier P5 § 16)")
    preuve.add_argument("quoi", choices=("model-list",))
    diagnostic = commandes.add_parser("diagnostic", help="État du poste, sans chemin ni secret")
    diagnostic.add_argument("--reseau", action="store_true", help="Joindre /api/health de Hermes (sans jeton)")
    diagnostic.add_argument("--isolement", action="store_true",
                            help="Vérifier que les profils interdits ne sont pas listables")
    journal = commandes.add_parser("journal", help="Fin du journal local")
    journal.add_argument("--lignes", type=int, default=40, help="Nombre de lignes à afficher (1 à 2000)")
    commandes.add_parser("oublier-jeton", help="Effacer le jeton machine local")
    commandes.add_parser("quotas", help="Relevés de quotas (Codex, ligne d'état Claude Code)")
    bundle = commandes.add_parser("bundle", help="Exécutant : git bundle d'une branche prête (railway ssh)")
    bundle.add_argument("alias", help="Alias du dépôt dans executant.toml")
    bundle.add_argument("branche", help="hermes/projet-<slug> ou hermes/<carte>")
    commandes.add_parser("pause", help="Exécutant : pause locale (aucune carte ni sonde)")
    commandes.add_parser("reprise", help="Exécutant : lever la pause locale")
    commandes.add_parser("cartes", help="Exécutant : état local des cartes (sans contenu ni secret)")
    sonde = commandes.add_parser("sonde-plateforme",
                                 help="Exécutant Linux : sonde d'isolement (bubblewrap, UID), sans identifiant")
    sonde.add_argument("--json", action="store_true", help="Relevé complet en JSON (publiable : aucun identifiant)")
    return parser


def _charger(contexte: Contexte):
    from .politique import PolitiqueRefusee, charger

    try:
        return charger(contexte.emplacements), None
    except PolitiqueRefusee as exc:
        return None, str(exc)


def _valeurs(contexte: Contexte) -> list[str]:
    valeurs = []
    for usage in ("jeton-machine", "jeton-claude"):
        try:
            valeur = contexte.coffre.lire(usage)
        except CoffreErreur:
            valeur = None
        if valeur:
            valeurs.append(valeur)
    return valeurs


def _releve(contexte: Contexte, politique, *, publier: bool) -> int:
    from .inventaire import InventaireRetenu, construire, relever
    from .jeton import Jeton, JetonInvalide
    from .protocole import Protocole, Refus
    from .verrou import Verrou, VerrouOccupe

    try:
        verrou = Verrou(contexte.emplacements.verrou_sondes).prendre()
    except VerrouOccupe:
        print("Une sonde est en cours dans le service : réessayez dans une minute.", file=sys.stderr)
        return 2
    try:
        codex, claude = asyncio.run(relever(politique, emplacements=contexte.emplacements, coffre=contexte.coffre,
                                            lanceurs=contexte.lanceurs, environnement=contexte.environnement))
    finally:
        verrou.rendre()
    valeurs = _valeurs(contexte)
    try:
        inventaire = construire(politique, codex, claude, windows=contexte.version_windows(), valeurs_exactes=valeurs)
    except InventaireRetenu as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(inventaire, ensure_ascii=False, indent=2))
    if not publier:
        return 0
    brut = next((v for v in valeurs if v.startswith("acpm_")), None)
    try:
        jeton = Jeton(brut or "")
    except JetonInvalide:
        print(f"Poste non enrôlé : lancez « {commande_poste('enroler')} » avant de publier.", file=sys.stderr)
        return 2
    try:
        reponse = Protocole(contexte.client(politique)).publier(jeton, inventaire)
    except Refus as exc:
        print(exc.message, file=sys.stderr)
        return 1
    print(f"Inventaire publié ({', '.join(f'{v} : {i}' for v, i in reponse.releves.items())}) ; "
          f"{len(reponse.alertes)} alerte(s).")
    return 0


def _quotas(contexte: Contexte, politique) -> int:
    from .inventaire import relever
    from .verrou import Verrou, VerrouOccupe

    if not (politique.sondes.codex or politique.sondes.claude):
        print("Relevé des quotas refusé : aucune sonde autorisée par poste.toml ([sondes] codex et claude à false) ; "
              "rien n'a été lancé ni lu.", file=sys.stderr)
        return 2
    try:
        verrou = Verrou(contexte.emplacements.verrou_sondes).prendre()
    except VerrouOccupe:
        print("Une sonde est en cours dans le service : réessayez dans une minute.", file=sys.stderr)
        return 2
    try:
        codex, claude = asyncio.run(relever(politique, emplacements=contexte.emplacements, coffre=contexte.coffre,
                                            lanceurs=contexte.lanceurs, environnement=contexte.environnement))
    finally:
        verrou.rendre()
    rapport = {r.releve["voie"]: {"etat": r.releve["etat"], "detail": r.releve["detail"],
                                  "compteurs": r.releve["compteurs"]} for r in (codex, claude) if r is not None}
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    return 0


def _sonde_plateforme(args: argparse.Namespace, contexte: Contexte) -> int:
    """Sonde R0 : ni politique, ni volume, ni jeton ; sortie 0 quel que soit le régime (c'est un relevé)."""
    if contexte.plateforme != "linux":
        print("La sonde de plateforme ne concerne que l'exécutant Linux (bubblewrap, UID dédiés) : rien n'a été "
              "lancé.", file=sys.stderr)
        return 2
    from .sonde_plateforme import imprimer, sonder

    resultat = sonder(codex=str(contexte.emplacements.codex_par_defaut),
                      claude=str(contexte.emplacements.claude_par_defaut))
    if args.json:
        print(imprimer(resultat))
    else:
        v = resultat["verdict"]
        print(f"Régime {v['regime']} : bubblewrap {v['bwrap']}, UID séparés : {'oui' if v['uid_separes'] else 'non'}. "
              f"{v['raison']}")
    return 0


def executer(args: argparse.Namespace, contexte: Contexte) -> int:
    commande = args.commande
    if commande == "sonde-plateforme":
        return _sonde_plateforme(args, contexte)
    linux = contexte.plateforme == "linux"
    if commande in ("pause", "reprise", "cartes", "bundle") and not linux:
        print(f"« {commande} » ne concerne que l'exécutant Linux : sans objet sur le poste Windows.", file=sys.stderr)
        return 2
    if commande in ("pause", "reprise"):
        from .gestes_executant import pause

        return pause(contexte, commande == "pause")
    if commande == "cartes":
        from .gestes_executant import cartes

        return cartes(contexte)
    if commande == "journal":
        lignes = lire_fin(contexte.emplacements.journal, max(1, min(args.lignes, 2000)))
        if lignes is None:
            print("Aucun journal : le service n'a encore rien écrit.")
            return 0
        print("\n".join(lignes))
        return 0
    if commande == "oublier-jeton":
        try:
            efface = contexte.coffre.effacer("jeton-machine")
        except CoffreErreur as exc:
            print(str(exc), file=sys.stderr)
            return 2
        try:
            contexte.emplacements.machine.unlink()
        except OSError:
            pass
        print("Jeton machine effacé de ce poste (la révocation reste un geste sur la page Poste)." if efface
              else "Aucun jeton machine sur ce poste.")
        return 0
    if commande == "diagnostic":
        from .diagnostic import diagnostic

        print(json.dumps(diagnostic(contexte, reseau=args.reseau, isolement=args.isolement), ensure_ascii=False,
                         indent=2))
        return 0
    if commande == "servir":
        from .plateforme import PlateformeIndisponible, verifier_annonce
        from .service import servir

        try:
            verifier_annonce(args.plateforme)
        except PlateformeIndisponible as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return asyncio.run(servir(contexte))
    politique, refus = _charger(contexte)
    if politique is None:
        print(f"Configuration du poste refusée : {refus}", file=sys.stderr)
        return 2
    if commande in ("enroler", "connexion", "preuve"):
        # Jeton, profil Codex et coffre appartiennent au compte du poste : lancés dans un autre compte, ils
        # atterriraient dans son profil et le service ne les trouverait jamais.
        from .politique import PolitiqueRefusee, verifier_compte

        try:
            verifier_compte(politique, contexte.compte_courant())
        except PolitiqueRefusee as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if commande == "connexion" and linux:
        from .gestes_executant import connexion_codex_linux, deposer_jeton

        if args.cible == "bac-a-sable":
            print("« connexion bac-a-sable » ne concerne que le poste Windows : l'exécutant Linux mesure son bac à "
                  "sable par la sonde de plateforme.", file=sys.stderr)
            return 2
        if args.cible == "codex":
            return connexion_codex_linux(contexte, politique)
        return deposer_jeton(contexte, "jeton-claude" if args.cible == "claude" else "jeton-github",
                             stdin=args.stdin)
    if commande == "connexion" and args.cible == "github":
        print("« connexion github » ne concerne que l'exécutant Linux (dépôts distants) : sans objet sur le poste "
              "Windows.", file=sys.stderr)
        return 2
    if commande == "connexion" and args.cible == "claude":
        from .connexions import connexion_claude

        return connexion_claude(contexte, lire=(lambda _invite: sys.stdin.readline()) if args.stdin else None)
    if commande == "enroler":
        from .enrolement import enroler

        return enroler(contexte, politique, contexte.journal(politique), code_stdin=args.code_stdin,
                       remplacer=args.remplacer)
    if commande == "connexion":
        from .connexions import connexion_bac_a_sable, connexion_codex

        return connexion_codex(contexte, politique) if args.cible == "codex" else \
            connexion_bac_a_sable(contexte, politique)
    if commande == "releve":
        return _releve(contexte, politique, publier=args.publier)
    if commande == "preuve":
        from .preuves import preuve_model_list

        return preuve_model_list(contexte, politique, _valeurs(contexte))
    if commande == "quotas":
        return _quotas(contexte, politique)
    if commande == "bundle":
        from .gestes_executant import bundle

        return bundle(contexte, politique, args.alias, args.branche)
    raise AssertionError(commande)


def _utf8() -> None:
    for flux in (sys.stdout, sys.stderr):
        reconfigurer = getattr(flux, "reconfigure", None)
        if reconfigurer is not None:
            try:
                reconfigurer(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None, *, contexte: Contexte | None = None) -> int:
    _utf8()
    with _argparse_en_francais():
        args = _parser().parse_args(argv)
    try:
        contexte = contexte or Contexte.du_compte()
    except (EmplacementsIndisponibles, PlateformeIndisponible) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        return executer(args, contexte)
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
