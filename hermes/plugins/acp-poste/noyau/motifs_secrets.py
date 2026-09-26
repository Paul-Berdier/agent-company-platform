"""Motifs de secrets refusés dans les textes que le greffon écrit sur une carte ou transmet au poste
(objectif, consigne, réponse, surcharge) : les MÊMES motifs que ``scripts/balayer_secrets.py``
(un test du dépôt vérifie la parité). Un secret d'une autre forme passerait : c'est une barrière de
plus, pas une garantie (limite dite dans la documentation)."""

from __future__ import annotations

import re
from typing import Optional

MOTIFS = {
    "clé privée PEM": re.compile(r"^\s*-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----\s*$"),
    "clé privée PEM en ligne": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----(?:\\[nr]|\s)+[A-Za-z0-9+/]{32,}"),
    "clé d'API Anthropic": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "clé d'API OpenAI": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9]{20,}"),
    "clé d'API Google": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "jeton GitHub": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "clé d'accès AWS": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "jeton Slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "empreinte argon2id": re.compile(r"\$argon2id\$v=19\$m=\d+,t=\d+,p=\d+\$[A-Za-z0-9+/]{16,}\$[A-Za-z0-9+/]{16,}"),
    "jeton JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}


def motif_trouve(texte: Optional[str]) -> Optional[str]:
    """Nom du premier motif trouvé dans ``texte`` (ligne par ligne pour les motifs ancrés), ou None."""
    if not texte:
        return None
    for nom, motif in MOTIFS.items():
        if motif.pattern.startswith("^"):
            if any(motif.search(ligne) for ligne in str(texte).splitlines()):
                return nom
        elif motif.search(str(texte)):
            return nom
    return None
