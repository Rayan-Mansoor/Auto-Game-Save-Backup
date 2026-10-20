"""Entry point for the frozen tray program (saveix-tray.exe), which has no console."""

import sys

from saveix.ui.tray import main

if __name__ == "__main__":
    sys.exit(main())
