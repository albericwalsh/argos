from src.core.command import command
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
        help_text = "Commandes disponibles :\n"
        for cmd in self.commands:
            help_text += f"- {cmd.name} : {cmd.description}\n"
            
        help_text += "\nTapez 'exit' ou 'quit' pour quitter le CLI."
        print(help_text) 