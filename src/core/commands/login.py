from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import HTML

from src.core.command import command
from src.core.cli_session import get_session
from src.core.workflow_runner import load_workflows_for_user
from src.core.cli_colors import PROMPT_STYLE, print_ok, print_error, print_warn, print_info


class LoginCommand(command):
    def __init__(self):
        super().__init__(
            name='login',
            description="Se connecter (ou changer de compte) — recharge les workflows accessibles",
            function=self.do_login
        )

    def do_login(self, *args):
        session = get_session()

        if session.is_authenticated:
            print_info(f"Déjà connecté en tant que {session.username}. "
                       f"Tapez 'logout' avant de vous reconnecter avec un autre compte.")
            return

        username = prompt(HTML("<argos-prompt>Identifiant</argos-prompt> : "), style=PROMPT_STYLE).strip()
        if not username:
            print_error("Identifiant requis.")
            return

        password = prompt(HTML("<argos-prompt>Mot de passe</argos-prompt> : "), style=PROMPT_STYLE, is_password=True)
        if not password:
            print_error("Mot de passe requis.")
            return

        ok, message = session.login(username, password)
        if not ok:
            print_error(message)
            return

        print_ok(message)

        try:
            n = len(load_workflows_for_user(session.api_base, session.token))
            print_info(f"{n} workflow(s) chargé(s) pour cette session.")
        except Exception as e:
            print_warn(f"Connecté, mais échec du chargement des workflows : {e}")