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

Codes de sortie : 0 (normal, non enrôlé, révoqué), 1 (erreur imprévue ou Hermes injoignable), 2 (configuration
refusée), 3 (autre instance), 4 (jeton gardé mais refusé par la couture de Hermes). Tout message est en français ;
aucune commande n'imprime un jeton, un code ou un chemin de profil.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import __version__
from .chemins import EmplacementsIndisponibles
from .coffre import CoffreErreur
from .contexte import Contexte
from .journal import lire_fin

EPILOGUE = ("Poste Windows d'ACP (étape P5 : présence, catalogue, quotas ; aucune exécution de carte avant P6). "
            "Installation : packaging/poste ; documentation : apps/poste/README.md.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acp-poste", epilog=EPILOGUE)
    parser.add_argument("--version", action="version", version=f"acp-poste {__version__}")
    commandes = parser.add_subparsers(dest="commande", required=True)
    commandes.add_parser("servir", help="Boucle du service : attente des ordres, relevés, inventaire")
    enroler = commandes.add_parser("enroler", help="Enrôler ce poste auprès de Hermes (code de la page Poste)")
    enroler.add_argument("--code-stdin", action="store_true", help="Lire le code sur l'entrée standard")
    enroler.add_argument("--remplacer", action="store_true", help="Remplacer le jeton d'un enrôlement précédent")
    connexion = commandes.add_parser("connexion", help="Connexions manuelles du compte du poste")
    connexion.add_argument("cible", choices=("codex", "claude", "bac-a-sable"))
    releve = commandes.add_parser("releve", help="Relever maintenant (sondes) et imprimer l'inventaire")
    releve.add_argument("--publier", action="store_true", help="Publier aussi l'inventaire sur Hermes")
    preuve = commandes.add_parser("preuve", help="Archiver une preuve (cahier P5 § 16)")
    preuve.add_argument("quoi", choices=("model-list",))
    diagnostic = commandes.add_parser("diagnostic", help="État du poste, sans chemin ni secret")
    diagnostic.add_argument("--reseau", action="store_true", help="Joindre /api/health de Hermes (sans jeton)")
    diagnostic.add_argument("--isolement", action="store_true",
                            help="Vérifier que les profils interdits ne sont pas listables")
    journal = commandes.add_parser("journal", help="Fin du journal local")
    journal.add_argument("--lignes", type=int, default=40)
    commandes.add_parser("oublier-jeton", help="Effacer le jeton machine local")
    commandes.add_parser("quotas", help="Relevés de quotas (Codex, ligne d'état Claude Code)")
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
        print("Poste non enrôlé : lancez « acp-poste enroler » avant de publier.", file=sys.stderr)
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


def executer(args: argparse.Namespace, contexte: Contexte) -> int:
    commande = args.commande
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
        from .service import servir

        return asyncio.run(servir(contexte))
    if commande == "connexion" and args.cible == "claude":
        from .connexions import connexion_claude

        return connexion_claude(contexte)
    politique, refus = _charger(contexte)
    if politique is None:
        print(f"Configuration du poste refusée : {refus}", file=sys.stderr)
        return 2
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
    args = _parser().parse_args(argv)
    try:
        contexte = contexte or Contexte.du_compte()
    except EmplacementsIndisponibles as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        return executer(args, contexte)
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
