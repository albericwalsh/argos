from src.core.command import command
from src.core.cli_session import require_session
from src.core.cli_colors import muted, accent_bold, info
from src.variables import WORKFLOWS_REGISTERY


class ListWorkflowsCommand(command):
    def __init__(self):
        super().__init__(
            name='listwf',
            description='Affiche la liste des workflows accessibles (nécessite une connexion)',
            function=self.show_workflows
            )

    def show_workflows(self, *args):
        session = require_session()
        if session is None:
            return

        # SÉCURITÉ : les workflows sont chiffrés sur disque, owner_id par
        # fichier. On ne lit plus jamais data/workflows/*.json directement —
        # WORKFLOWS_REGISTERY est peuplé au login via load_workflows_for_user(),
        # qui ne contient que ce que CE user peut déchiffrer (owner ou
        # permission workflows:*).
        print(muted("#-----------------------------------------"))
        print(muted("  > Workflows accessibles :"))
        print(muted("#-----------------------------------------\n"))

        if not WORKFLOWS_REGISTERY:
            print(info("  (aucun workflow accessible, ou pas encore chargé — tapez 'login' pour recharger)"))
        else:
            for wf in WORKFLOWS_REGISTERY:
                print(f"- {wf.name} ({muted('ID:')} {accent_bold(wf.id)})")
        print()