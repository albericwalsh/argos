"""
src/core/cli_colors.py
─────────────────────────
Couleurs et helpers d'affichage pour le CLI Argos, alignés sur la
palette du WebUI (accent #00e5a0, erreur #ff4d4d, warning #f5a623).

Utilise les codes ANSI directement (compatibles avec print() standard,
fonctionnent dans la plupart des terminaux modernes — Windows Terminal,
iTerm, gnome-terminal, etc.) plutôt que de dépendre de print_formatted_text
de prompt_toolkit pour les messages simples, afin que tout le code
existant qui fait déjà print("[ERROR] ...") puisse être mis à jour sans
changer sa structure, juste en enrobant le texte.

Pour le PROMPT lui-même (la ligne "> " avec curseur), un Style
prompt_toolkit dédié est exposé séparément (PROMPT_STYLE) car
prompt_toolkit gère sa propre colorisation pour les éléments interactifs.
"""

import os
import sys

from prompt_toolkit.styles import Style

# ─── Détection support couleur ──────────────────────────────────────────────────

def _supports_color() -> bool:
    """
    Désactive les couleurs si la sortie n'est pas un vrai terminal (pipe,
    redirection vers fichier) ou si NO_COLOR est définie (convention
    standard https://no-color.org/), pour ne jamais polluer une sortie
    scriptée avec des codes ANSI bruts.
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("ARGOS_FORCE_COLOR") is not None:
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR_ENABLED = _supports_color()

# ─── Palette (alignée sur le WebUI Argos) ──────────────────────────────────────
# Codes ANSI 256 couleurs (38;2;r;g;b) pour matcher les hex exacts du WebUI.

_RESET   = "\033[0m"
_BOLD    = "\033[1m"
_DIM     = "\033[2m"

_ACCENT  = "\033[38;2;0;229;160m"    # #00e5a0 — succès, accent général
_ERROR   = "\033[38;2;255;77;77m"    # #ff4d4d
_WARNING = "\033[38;2;245;166;35m"   # #f5a623
_INFO    = "\033[38;2;77;200;255m"   # #4dc8ff — bleu clair, cohérent avec C_LOW du report engine
_MUTED   = "\033[38;2;107;107;120m"  # #6b6b78 — gris, cohérent avec --muted du WebUI


def _wrap(code: str, text: str) -> str:
    if not _COLOR_ENABLED:
        return text
    return f"{code}{text}{_RESET}"


# ─── Helpers publics ────────────────────────────────────────────────────────────

def success(text: str) -> str:
    return _wrap(_ACCENT, text)

def error(text: str) -> str:
    return _wrap(_ERROR, text)

def warning(text: str) -> str:
    return _wrap(_WARNING, text)

def info(text: str) -> str:
    return _wrap(_INFO, text)

def muted(text: str) -> str:
    return _wrap(_MUTED, text)

def bold(text: str) -> str:
    return _wrap(_BOLD, text)

def accent_bold(text: str) -> str:
    if not _COLOR_ENABLED:
        return text
    return f"{_BOLD}{_ACCENT}{text}{_RESET}"


# ─── Messages préfixés standards ────────────────────────────────────────────────
# Remplacent les print(f"[OK] ...") / print(f"[ERROR] ...") existants par
# des versions colorées, en gardant le même préfixe textuel (utile si la
# sortie est un jour parsée, ou pour rester lisible sans couleur — NO_COLOR).

def print_ok(text: str) -> None:
    print(f"{success('[OK]')} {text}")

def print_error(text: str) -> None:
    print(f"{error('[ERROR]')} {text}")

def print_warn(text: str) -> None:
    print(f"{warning('[WARN]')} {text}")

def print_info(text: str) -> None:
    print(f"{info('[INFO]')} {text}")


# ─── Style du prompt interactif (prompt_toolkit) ───────────────────────────────
# Utilisé par prompt(..., style=PROMPT_STYLE) — colore le ">" d'invite et,
# si jamais on ajoute un message de continuation/erreur inline, ces classes
# sont déjà prêtes à être référencées via des balises <argos-prompt> etc.

PROMPT_STYLE = Style.from_dict({
    "argos-prompt":  "#00e5a0 bold",
    "argos-error":   "#ff4d4d",
    "argos-warning": "#f5a623",
    "argos-muted":   "#6b6b78",
})