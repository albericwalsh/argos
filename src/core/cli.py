import sys
from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import HTML

from src.core.completer import get_completer
from src.core.cli_history import get_history, trim_history
from src.core.cli_colors import PROMPT_STYLE, print_ok, print_error, print_warn, print_info, muted
from src.core.cli_modules import banner
from src.core.commands.help import HelpCommand
from src.core.cli_session import get_session
from src.core.workflow_runner import load_workflows_for_user
from src.variables import COMMANDS_REGISTERY


def _parse_login_args(argv: list) -> tuple[str | None, str | None]:
    """
    Cherche --user/--username et --password dans les arguments de
    lancement (sys.argv). Retourne (username, password), chacun pouvant
    être None si absent — dans ce cas le prompt interactif prendra le relais.
    """
    username = None
    password = None

    for i, arg in enumerate(argv):
        if arg in ("--user", "--username") and i + 1 < len(argv):
            username = argv[i + 1]
        elif arg == "--password" and i + 1 < len(argv):
            password = argv[i + 1]

    return username, password


def authenticate(argv: list) -> bool:
    """
    Authentifie l'utilisateur avant d'entrer dans la boucle CLI.
    Priorité aux arguments de lancement (--user/--password) ; si absents
    ou incomplets, bascule sur un prompt interactif (mot de passe masqué).

    Retourne True si l'authentification a réussi, False sinon (le CLI
    ne devrait alors pas continuer en mode --web sans interaction, mais
    reste utilisable pour les commandes ne nécessitant pas de login,
    comme 'listmods' ou 'help').
    """
    session = get_session()
    username, password = _parse_login_args(argv)

    if username and password:
        print_info(f"Authentification avec les identifiants fournis en argument ({username})…")
    else:
        print(muted("\n── Authentification Argos ──"))
        if not username:
            username = prompt(HTML("<argos-prompt>Identifiant</argos-prompt> : "), style=PROMPT_STYLE).strip()
        if not password:
            password = prompt(HTML("<argos-prompt>Mot de passe</argos-prompt> : "), style=PROMPT_STYLE, is_password=True)

    if not username or not password:
        print_warn("Authentification incomplète — certaines commandes "
                   "(run, listwf) resteront indisponibles. Tapez 'login' pour réessayer.")
        return False

    ok, message = session.login(username, password)
    if not ok:
        print_error(message)
        print_warn("Le CLI démarre quand même, mais 'run'/'listwf' resteront "
                    "indisponibles jusqu'à un 'login' réussi.")
        return False

    print_ok(message)

    try:
        n = len(load_workflows_for_user(session.api_base, session.token))
        print_info(f"{n} workflow(s) chargé(s) pour cette session.")
    except Exception as e:
        print_warn(f"Connecté, mais échec du chargement des workflows : {e}")

    return True


def cli_loop():
    '''Boucle principale du CLI.'''

    banner.print_banner()

    authenticate(sys.argv[1:])

    help_command = HelpCommand()
    help_command.execute()

    history = get_history()
    running = True

    sys.stdout.flush()

    while running:

        try:
            user_input = prompt(
                HTML("\n<argos-prompt>›</argos-prompt> "),
                style=PROMPT_STYLE,
                completer=get_completer(history=history),
                history=history,
            ).strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit']:

                print(muted("Exiting Argos CLI. Goodbye!"))
                running = False
                continue

            command_found = False

            for command in COMMANDS_REGISTERY:

                command_name = user_input.split()[0].lower()

                if command_name == command.name:

                    args = user_input.split()[1:]

                    command.execute(args)

                    command_found = True
                    break

            if not command_found:

                print_error(
                    f"Unknown command: '{user_input}'\n"
                    f"Type 'help' to see available commands."
                )

            # Tronque le fichier d'historique à la limite fixe après chaque
            # commande, plutôt qu'uniquement à la fermeture — protège aussi
            # contre un Ctrl+C ou un crash qui empêcherait la troncature finale.
            trim_history()

        except KeyboardInterrupt:

            print(muted("\nExiting Argos CLI. Goodbye!"))
            running = False
            trim_history()