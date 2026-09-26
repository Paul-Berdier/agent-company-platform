"""Écrivain de la ligne d'état de VOS sessions Claude Code, installé à côté du poste (étape P5, décision D56).

Copié par ``Installer-PosteAcp.ps1`` sous ``C:\\Program Files\\ACP\\poste\\ligne_etat.py``. Réglage de Claude Code
(``~/.claude/settings.json`` de votre compte, barres obliques) :

    {"statusLine": {"type": "command",
      "command": "\\"C:/Program Files/Python312/python.exe\\" -I \\"C:/Program Files/ACP/poste/ligne_etat.py\\""}}

Il recopie ``rate_limits.five_hour`` et ``rate_limits.seven_day`` dans ``C:\\ProgramData\\ACP\\quotas\\claude-code.json``
(``acp_poste.claude_statusline``), que lit le compte du poste. Il ne lève jamais et sort toujours avec le code 0.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from acp_poste.claude_statusline import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
