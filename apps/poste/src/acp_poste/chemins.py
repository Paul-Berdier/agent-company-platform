"""Emplacements du poste (cahier P5 § 3.1, § 5.4, § 6, § 7.1).

Trois racines, jamais journalisées :

- ``%ProgramData%`` : ``ACP\\poste.toml`` (politique en lecture seule pour le compte du poste, décision D52) et
  ``ACP\\quotas\\claude-code.json`` (ligne d'état des sessions Claude Code du propriétaire, D56) ;
- ``%LOCALAPPDATA%`` **du compte qui fait tourner le poste** : ``ACP\\secrets`` (coffre DPAPI), ``ACP\\etat``
  (verrous, identité non secrète du poste, état du service, catalogue embarqué de Codex), ``ACP\\journal``,
  ``ACP\\preuves``, ``ACP\\bac-a-sable`` ;
- ``%ProgramFiles%`` : ``ACP\\poste`` (bibliothèques, lanceur) et ``ACP\\outils`` (binaires de Codex et de Claude
  Code, D54).

Sous Windows, elles sont lues par ``SHGetKnownFolderPath`` et **jamais** dans l'environnement : une variable
utilisateur ``PROGRAMDATA`` (registre ``HKCU\\Environment``, modifiable par le compte du poste) pourrait sinon
faire lire au poste une politique écrite par un exécutant mal confiné. Hors Windows, il n'existe aucun
emplacement par défaut : les tests (et le bout en bout local) injectent une racine jetable
(:meth:`Emplacements.de_test`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

FOLDERID_PROGRAMDATA = "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97"
FOLDERID_LOCALAPPDATA = "F1B32785-6FBA-4FCF-9D55-7B8E7F157091"
FOLDERID_PROGRAMFILES = "905E63B6-C1BF-494E-B29C-65B732D3D21A"


class EmplacementsIndisponibles(RuntimeError):
    """Emplacements du poste introuvables (hors Windows, ou dossier connu illisible)."""


def _dossier_connu(identifiant: str) -> Path:
    """Chemin d'un dossier connu de Windows (``SHGetKnownFolderPath``), sans passer par l'environnement."""

    import ctypes
    import uuid
    from ctypes import wintypes

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    brut = uuid.UUID(identifiant)
    guid = _GUID(brut.fields[0], brut.fields[1], brut.fields[2], (ctypes.c_ubyte * 8)(*brut.bytes[8:]))
    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
                                             ctypes.POINTER(ctypes.c_wchar_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    chemin = ctypes.c_wchar_p()
    resultat = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(chemin))
    try:
        if resultat != 0 or not chemin.value:
            raise EmplacementsIndisponibles(
                f"Dossier connu de Windows illisible ({identifiant}, code {resultat & 0xFFFFFFFF:#010x}).")
        return Path(chemin.value)
    finally:
        if chemin:
            ole32.CoTaskMemFree(ctypes.cast(chemin, ctypes.c_void_p))


@dataclass(frozen=True)
class Emplacements:
    """Racines du poste ; toutes les autres adresses en dérivent."""

    programdata: Path
    localappdata: Path
    programfiles: Path

    # ---------------------------------------------------------------- %ProgramData%\ACP
    @property
    def acp_programdata(self) -> Path:
        return self.programdata / "ACP"

    @property
    def politique(self) -> Path:
        return self.acp_programdata / "poste.toml"

    @property
    def quotas_claude(self) -> Path:
        return self.acp_programdata / "quotas" / "claude-code.json"

    # ---------------------------------------------------------------- %LOCALAPPDATA%\ACP (compte du poste)
    @property
    def acp_local(self) -> Path:
        return self.localappdata / "ACP"

    @property
    def secrets(self) -> Path:
        return self.acp_local / "secrets"

    @property
    def etat(self) -> Path:
        return self.acp_local / "etat"

    @property
    def journal(self) -> Path:
        return self.acp_local / "journal"

    @property
    def preuves(self) -> Path:
        return self.acp_local / "preuves"

    @property
    def bac_a_sable(self) -> Path:
        return self.acp_local / "bac-a-sable"

    @property
    def verrou_instance(self) -> Path:
        return self.etat / "poste.verrou"

    @property
    def verrou_sondes(self) -> Path:
        return self.etat / "sondes.verrou"

    @property
    def machine(self) -> Path:
        """Identité NON secrète du poste enrôlé : ``machine_id``, empreinte courte, date d'enrôlement."""
        return self.etat / "machine.json"

    @property
    def etat_service(self) -> Path:
        """Dernier échange avec Hermes, écart d'horloge, refus : lu par ``acp-poste diagnostic``."""
        return self.etat / "service.json"

    @property
    def dernier_inventaire(self) -> Path:
        """Dernier inventaire construit (sans identifiant par construction, § 11.3) : lu par le diagnostic."""
        return self.etat / "dernier-inventaire.json"

    def catalogue_embarque(self, version: str) -> Path:
        return self.etat / f"catalogue-embarque-{version}.json"

    # ---------------------------------------------------------------- %ProgramFiles%\ACP
    @property
    def acp_programfiles(self) -> Path:
        return self.programfiles / "ACP"

    @property
    def outils(self) -> Path:
        return self.acp_programfiles / "outils"

    @property
    def codex_par_defaut(self) -> Path:
        # Disposition du paquet npm @openai/codex (vendor/x86_64-pc-windows-msvc) recopiée telle quelle : le
        # binaire natif sous bin/, ses assistants (codex-windows-sandbox-setup.exe…) sous codex-resources/, que
        # Codex cherche à partir de son propre exécutable.
        return self.outils / "codex" / "bin" / "codex.exe"

    @property
    def claude_par_defaut(self) -> Path:
        return self.outils / "claude" / "claude.exe"

    # ---------------------------------------------------------------- construction
    @classmethod
    def de_test(cls, racine: Path) -> "Emplacements":
        """Racine jetable (tests, bout en bout local) : jamais les vrais dossiers d'une installation."""
        racine = Path(racine)
        return cls(programdata=racine / "ProgramData", localappdata=racine / "LocalAppData",
                   programfiles=racine / "Program Files")

    def sous(self, racine: Path) -> bool:
        """Les trois racines sont-elles DANS ``racine`` (garde du lanceur de bout en bout, § 14.5) ?"""
        base = Path(os.path.realpath(racine))
        for chemin in (self.programdata, self.localappdata, self.programfiles):
            reel = Path(os.path.realpath(chemin))
            if reel != base and base not in reel.parents:
                return False
        return True


def emplacements_du_compte() -> Emplacements:
    """Emplacements réels du compte courant (Windows seulement)."""

    if os.name != "nt":
        raise EmplacementsIndisponibles(
            "Les emplacements du poste ne sont définis que sous Windows (dossiers connus du système).")
    return Emplacements(programdata=_dossier_connu(FOLDERID_PROGRAMDATA),
                        localappdata=_dossier_connu(FOLDERID_LOCALAPPDATA),
                        programfiles=_dossier_connu(FOLDERID_PROGRAMFILES))
