"""Point d'entrée ``python -m acp_database`` : délègue à ``acp_database.migrate``."""

import sys

from .migrate import main

if __name__ == "__main__":
    sys.exit(main())
