import os

from src.core.command import command
from src.utils import open_file
from src.variables import APP_DIR, MODULES_REGISTERY


class ListModulesCommand(command):

    def __init__(self):

        super().__init__(
            name='listmods',
            description='Affiche la liste des modules disponibles',
            function=self.show_modules
        )

    def show_modules(self, *args):
        modules_text = (
            "#-----------------------------------------\n"
            "  > Modules disponibles :\n"
            "#-----------------------------------------\n\n"
        )

        for modules in MODULES_REGISTERY:
            modules_text += f"  - {modules.name} [{modules.id}] : {modules.category}\n"
        print(modules_text)