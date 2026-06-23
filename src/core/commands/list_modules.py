from src.core.command import command
from src.core.cli_colors import muted, accent_bold
from src.variables import MODULES_REGISTERY


class ListModulesCommand(command):

    def __init__(self):

        super().__init__(
            name='listmods',
            description='Affiche la liste des modules disponibles',
            function=self.show_modules
        )

    def show_modules(self, *args):
        print(muted("#-----------------------------------------"))
        print(muted("  > Modules disponibles :"))
        print(muted("#-----------------------------------------\n"))

        for module in MODULES_REGISTERY:
            version = f" v{module.version}" if getattr(module, "version", None) else ""
            print(f"  - {module.name} [{accent_bold(module.id)}]{muted(version)} : {module.category}")
        print()