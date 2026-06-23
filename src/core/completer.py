"""
src/core/completer.py
────────────────────────
Autocomplétion contextuelle pour le CLI Argos.

Au-delà du simple matching sur les noms de commandes (WordCompleter de
base), ce completer propose :
  - les ids de workflow accessibles après "run "
  - les ids de module après "run <wf> /direct " ou en argument direct
  - les flags connus (/help, /h, /direct, /d) après "run "
  - les noms de commandes en tout début de ligne, comme avant

Utilise prompt_toolkit.completion.Completer (API bas niveau) plutôt que
WordCompleter, car WordCompleter ne sait proposer qu'une seule liste
statique — ici la liste de complétion dépend du contexte (mot en cours,
commande déjà tapée).
"""

from prompt_toolkit.completion import Completer, Completion

from src.variables import COMMANDS_REGISTERY, WORKFLOWS_REGISTERY, MODULES_REGISTERY

RUN_FLAGS = ["/help", "/h", "/direct", "/d"]


class ArgosCompleter(Completer):

    def __init__(self, history=None):
        """
        history : objet History (prompt_toolkit) — optionnel. Si fourni,
        les commandes complètes déjà tapées (ex: "run recon_full
        {\"domaine\":\"x\"}") sont proposées comme complétion sur toute la
        ligne, pas seulement sur le premier mot — pratique pour retrouver
        une commande complexe déjà utilisée sans tout retaper.
        """
        self.history = history

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split(" ")

        # ── Complétion depuis l'historique complet (priorité haute si le
        #    texte tapé correspond au début d'une ancienne commande déjà
        #    saisie, avec ses arguments) ───────────────────────────────────
        if self.history and text:
            seen = set()
            for past_line in reversed(list(self.history.get_strings())):
                if past_line in seen:
                    continue
                seen.add(past_line)
                if past_line.lower().startswith(text.lower()) and past_line != text:
                    yield Completion(
                        past_line,
                        start_position=-len(text),
                        display_meta="(historique)",
                    )

        # ── Premier mot : nom de commande ──────────────────────────────────
        if len(words) <= 1:
            current = words[0] if words else ""
            for cmd in COMMANDS_REGISTERY:
                if cmd.name.lower().startswith(current.lower()):
                    yield Completion(
                        cmd.name,
                        start_position=-len(current),
                        display_meta=cmd.description,
                    )
            return

        command_name = words[0].lower()
        current_word = words[-1]

        # ── Commande "run" : propose workflow_id, module_id, flags ──────────
        if command_name == "run":
            # Détecte si /direct ou /d a déjà été tapé sur la ligne → on
            # propose alors des module_id plutôt que des workflow_id.
            direct_mode = any(f in words for f in ("/direct", "/d"))

            if current_word.startswith("/"):
                for flag in RUN_FLAGS:
                    if flag.startswith(current_word):
                        yield Completion(flag, start_position=-len(current_word))
                return

            if direct_mode:
                for mod in MODULES_REGISTERY:
                    if mod.id.lower().startswith(current_word.lower()):
                        yield Completion(
                            mod.id,
                            start_position=-len(current_word),
                            display_meta=f"{mod.name} · {mod.category}",
                        )
            else:
                for wf in WORKFLOWS_REGISTERY:
                    if wf.id.lower().startswith(current_word.lower()):
                        yield Completion(
                            wf.id,
                            start_position=-len(current_word),
                            display_meta=wf.name,
                        )
            return

        # ── Autres commandes : pas de complétion contextuelle pour l'instant ──
        return


def get_completer(history=None) -> ArgosCompleter:
    return ArgosCompleter(history=history)