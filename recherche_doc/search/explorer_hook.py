"""Point d'entrée du plugin explorateur (lancé par le shell Windows).

Enregistré par ExplorerSearchPane.register() : commande
« Recherche Documentaire... » visible dans le menu contextuel / ruban de
l'explorateur lorsque le drive sync root est visité. Ouvre l'interface de
recherche Tkinter.
"""

import sys


def main():
    from recherche_doc.search.gui_app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
