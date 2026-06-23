from src.core.command import command
from src.core.cli_session import get_session
from src.core.cli_colors import print_ok, print_info
from src.variables import WORKFLOWS_REGISTERY


class LogoutCommand(command):
    def __init__(self):
        super().__init__(
            name='logout',
            description="Se déconnecter — vide la session et les workflows chargés",
            function=self.do_logout
        )

    def do_logout(self, *args):
        session = get_session()
        if not session.is_authenticated:
            print_info("Aucune session active.")
            return

        username = session.username
        session.logout()
        WORKFLOWS_REGISTERY.clear()
        print_ok(f"Déconnecté ({username}). Les workflows chargés ont été vidés de la mémoire.")