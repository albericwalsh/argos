from src.core.cli_modules import banner
from src.core.commands.help import HelpCommand
from src.variables import COMMANDS_REGISTERY


def cli_loop():
    '''Boucle principale du CLI.'''

    banner.print_banner()

    help_command = HelpCommand()
    help_command.execute()

    running = True

    while running:

        try:

            user_input = input("> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit']:

                print("Exiting Argos CLI. Goodbye!")
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

                print(
                    f"[ERROR] Unknown command: '{user_input}'\n"
                    f"Type 'help' to see available commands."
                )

        except KeyboardInterrupt:

            print("\nExiting Argos CLI. Goodbye!")
            running = False