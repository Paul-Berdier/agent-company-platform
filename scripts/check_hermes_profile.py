"""Refuse les fichiers susceptibles de remplacer les bornes du lanceur local.

Hermes 0.21.1 charge son .env avec override=True. Le lanceur ne modifie donc pas
silencieusement un profil contradictoire : il le refuse avant tout démarrage.
"""
import argparse
import io
import os
from pathlib import Path

from dotenv import dotenv_values
import yaml

PROTECTED = {
    "HERMES_HOME", "HERMES_PROFILE", "HERMES_CONFIG", "HERMES_ENV",
    "HERMES_CONFIG_PATH", "HERMES_ENV_PATH", "HERMES_MANAGED_DIR",
    "HERMES_DISABLE_LAZY_INSTALLS", "HERMES_LAZY_INSTALL_TARGET",
    "OBSIDIAN_VAULT_PATH", "PYTHON_DOTENV_DISABLED", "PYTHONPATH", "PYTHONHOME",
}


def check_profile(source: Path, profile: Path, *, managed: Path | None = None) -> None:
    if (source / ".env").exists():
        raise ValueError("Le checkout Hermes contient un .env ; le lanceur local refuse ce repli de configuration.")
    directories = [profile]
    if managed is not None and managed.is_dir():
        directories.append(managed)
    for directory in directories:
        for name in (".env", ".op.env"):
            path = directory / name
            if not path.exists():
                continue
            try:
                raw = path.read_bytes()
                # Le chargeur tiers retire les NUL avant de parser. Refuser ce
                # contenu empêche qu'une clé innocente ici devienne réservée là-bas.
                if b"\x00" in raw:
                    raise ValueError("Un fichier d'environnement Hermes contient un octet NUL ; démarrage refusé.")
                values = dotenv_values(stream=io.StringIO(raw.decode("utf-8-sig")), interpolate=False)
            except (OSError, UnicodeError):
                raise ValueError("Un fichier d'environnement Hermes est illisible ; démarrage refusé.") from None
            protected = [key for key in values if key.upper() in PROTECTED or key.upper().startswith("API_SERVER_")]
            if protected:
                raise ValueError("Retirer du profil/paramétrage géré les réglages réservés au lanceur : " + ", ".join(sorted(protected)))
        path = directory / "config.yaml"
        if path.exists():
            try:
                config = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
            except (OSError, UnicodeError, yaml.YAMLError):
                raise ValueError("Configuration Hermes illisible ; démarrage refusé.") from None
            if not isinstance(config, dict):
                raise ValueError("Configuration Hermes invalide.")
            if config.get("secrets"):
                raise ValueError("Sources de secrets externes non prises en charge par ce lanceur local ; utiliser un profil dédié sans injection externe.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    args = parser.parse_args()
    try:
        check_profile(args.source, args.profile,
                      managed=Path(os.environ.get("HERMES_MANAGED_DIR", "/etc/hermes")))
    except ValueError as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
