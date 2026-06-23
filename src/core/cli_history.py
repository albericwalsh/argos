"""
src/core/cli_history.py
─────────────────────────
Historique persistant des commandes du CLI Argos.

Utilise prompt_toolkit.history.FileHistory (navigation flèches haut/bas
native), stocké dans un fichier sur disque, avec troncature à une limite
fixe de lignes pour éviter une croissance illimitée.

Le fichier n'est jamais chiffré : il contient les commandes telles que
tapées (y compris les arguments JSON passés à 'run'), à l'exclusion des
mots de passe — login()/logout() utilisent un prompt() séparé pour le
mot de passe (jamais sur la ligne de commande elle-même), donc rien de
sensible n'y transite par construction, sauf si l'utilisateur inclut
volontairement un secret dans les inputs JSON d'une mission.
"""

import os

from prompt_toolkit.history import FileHistory

HISTORY_MAX_LINES = 50
HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".argos_history")


def _truncate_history_file(path: str, max_lines: int) -> None:
    """
    Tronque le fichier d'historique aux `max_lines` dernières entrées.
    FileHistory de prompt_toolkit écrit chaque entrée sous la forme :
        # timestamp
        +ligne_de_commande
        (ligne vide)
    Donc une "entrée" correspond à un bloc de 3 lignes (ou plus si la
    commande tapée contient elle-même des retours à la ligne — rare ici,
    le CLI ne lit qu'une ligne à la fois). On tronque par bloc plutôt que
    par ligne brute pour ne jamais couper une entrée au milieu.
    """
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Les entrées sont séparées par une ligne vide en fin de bloc.
    blocks = [b for b in content.split("\n\n") if b.strip()]
    if len(blocks) <= max_lines:
        return

    kept = blocks[-max_lines:]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(kept) + "\n\n")


def get_history() -> FileHistory:
    """
    Retourne l'objet FileHistory à passer à prompt(). Tronque le fichier
    existant AVANT de le charger, pour que la session courante démarre
    déjà sur un historique borné plutôt que d'attendre une future écriture.
    """
    _truncate_history_file(HISTORY_PATH, HISTORY_MAX_LINES)
    return FileHistory(HISTORY_PATH)


def trim_history() -> None:
    """
    À appeler après chaque commande (ou à la fermeture du CLI) pour
    re-tronquer le fichier au fil de l'écriture — FileHistory ajoute en
    continu, donc sans cet appel périodique le fichier dépasserait la
    limite entre deux démarrages du CLI.
    """
    _truncate_history_file(HISTORY_PATH, HISTORY_MAX_LINES)