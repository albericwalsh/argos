from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from src.variables import COMMANDS_REGISTERY

from src.variables import COMMANDS_REGISTERY

def get_completer():
    return WordCompleter([c.name for c in COMMANDS_REGISTERY], ignore_case=True)
