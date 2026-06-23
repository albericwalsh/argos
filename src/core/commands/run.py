import json

from src.core.command import command
from src.core.cli_session import require_session
from src.core.cli_colors import print_ok, print_error, print_info, accent_bold, muted, success, warning, error as color_error
from src.utils import delete_parameters
from src.variables import MODULES_REGISTERY, WORKFLOWS_REGISTERY
from src.classes.missions import Mission


class RunCommand(command):
    def __init__(self):
        super().__init__(
            name='run',
            description='Exécute un workflow (nécessite une connexion)',
            function=self.run_workflow
            )

    def run_workflow(self, *args):
        session = require_session()
        if session is None:
            return

        direct_mode = False

        # convert tuple of args to list of args
        if isinstance(args, tuple):
            args = [item for sublist in args for item in (sublist if isinstance(sublist, list) else [sublist])]

        # check if there is at least one argument
        if len(args) < 1:
            print_info("Usage: run <workflow_id> /{input/}")
            return
        # get the parameters
        for arg in args:
            if arg == "/help" or arg == "/h":
                print_info("Usage: run <workflow_id>")
                return
            elif arg == "/direct" or arg == "/d":
                direct_mode = True
                print_info("Running in direct mode")
        # delete all the parameters that start with /
        args = delete_parameters(args)
        print(muted("Workflow ID:"), accent_bold(args[0]) if len(args) > 0 else color_error("No workflow ID provided"))

        if direct_mode:
            module_id = args[0] if len(args) > 0 else None
            if module_id is None:
                print_error("Please provide a module ID to run in direct mode.")
                return
            module = next((m for m in MODULES_REGISTERY if m.id == module_id), None)
            if module is None:
                print_error(f"Module with ID {module_id} not found.")
                return
            print_info(f"Running module: {accent_bold(module.name)}")
            module.execute(args)
        else:
            wf_id = args[0] if len(args) > 0 else None
            if wf_id is None:
                print_error("Please provide a Workflow ID to run.")
                return
            workflow = next((w for w in WORKFLOWS_REGISTERY if w.id == wf_id), None)
            if workflow is None:
                print_error(f"Workflow with ID {wf_id} not found. "
                            f"Tapez 'listwf' pour voir les workflows accessibles à votre compte.")
                return
            print_info(f"Running workflow: {accent_bold(workflow.name)}")
            inputs = json.loads(args[1]) if len(args) > 1 else {}

            mission_name = f"CLI — {workflow.name}"
            mission = Mission(
                name=mission_name,
                workflow=workflow,
                owner_id=session.user_id,
                owner_key=session.enc_key,
                api_base=session.api_base,
                api_token=session.token,
            )

            # Exécution synchrone (contrairement au WebUI qui lance un thread,
            # le CLI attend le résultat directement avant de rendre la main).
            mission.execute(inputs)

            if workflow.results:
                print(muted("\n--- Résultats du workflow ---"))
                for step_id, data in workflow.results.items():
                    if step_id == "inputs":
                        continue
                    status_label = error_label = None
                    if data.get("error"):
                        print(f"{warning('[' + step_id + ']')} {color_error(str(data.get('error')))}")
                    else:
                        print(f"{success('[' + step_id + ']')} {data.get('output')}")

            status_color = success if mission.status == "completed" else color_error
            print_ok(f"Mission {accent_bold(mission.id)} — statut : {status_color(mission.status)} "
                     f"(résultat chiffré et envoyé à l'API)")