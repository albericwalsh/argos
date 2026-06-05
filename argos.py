import os
import sys
import threading

from src.core.workflow_runner import init_worflow_registery
from src.core.module_loader import init_modules_registery
from src.command_register import init_command
from src.core.cli import cli_loop
from src.variables import init_app_variables


import threading

def main():
    init_app_variables(os.path.dirname(os.path.abspath(__file__)))
    init_modules_registery()
    init_worflow_registery()
    init_command()
    args = sys.argv[1:]

    if '--web' in args:
        from src.WebUI.server import start_web_server
        if not start_web_server():
            print("[ERROR] Web server failed to start. Exiting.")
            sys.exit(1)

    cli_loop()
    

if __name__ == "__main__":
    main()