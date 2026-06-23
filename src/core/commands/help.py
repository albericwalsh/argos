from src.core.command import command
from src.core.cli_colors import muted, accent_bold
from src.variables import COMMANDS_REGISTERY

class HelpCommand(command):
    def __init__(self):
        super().__init__(
            name='help',
            description='Affiche la liste des commandes disponibles',
            function=self.show_help
            )
        # get all commands from the command registry
        self.commands = COMMANDS_REGISTERY

    def show_help(self, *args):
        print(muted("Commandes disponibles :"))
        for cmd in self.commands:
            print(f"- {accent_bold(cmd.name)} : {cmd.description}")

        print(muted("\nTapez 'exit' ou 'quit' pour quitter le CLI."))