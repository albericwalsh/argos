import os

from src.core.command import command
from src.utils import delete_parameters
from src.variables import APP_DIR, MODULES_REGISTERY

class RunCommand(command):
    def __init__(self):
        super().__init__(
            name='run',
            description='Exécute un workflow',
            function=self.run_workflow
            )

    def run_workflow(self, *args):
        direct_mode = False
        
        # convert tuple of args to list of args
        if isinstance(args, tuple):
            args = [item for sublist in args for item in (sublist if isinstance(sublist, list) else [sublist])]
            
        # check if there is at least one argument
        if len(args) < 1:
            print("Usage: run <workflow_id>")
            return
        # get the parameters
        for arg in args:
            if arg == "/help" or arg == "/h":
                print("Usage: run <workflow_id>")
                return
            elif arg == "/direct" or arg == "/d":
                direct_mode = True
                print("Running in direct mode")
        # delete all the parameters that start with /
        args = delete_parameters(args)
        print("Workflow ID:", args[0] if len(args) > 0 else "No workflow ID provided")
        
        if direct_mode:
            module_id = args[0] if len(args) > 0 else print("Please provide a module ID to run in direct mode.")
            module = next((m for m in MODULES_REGISTERY if m.id == module_id), None)
            if module is None:
                print(f"Module with ID {module_id} not found.")
                return
            print(f"Running module: {module.name}")
            module.execute(args)