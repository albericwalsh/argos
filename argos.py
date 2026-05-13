import os
import sys

from src.core.module_loader import init_modules_registery
from src.command_register import init_command
from src.core.cli import cli_loop
from src.variables import init_app_variables


def main():
    init_app_variables(os.path.dirname(os.path.abspath(__file__)))
    init_modules_registery()
    init_command()
    args = sys.argv[1:]
    if args is not None:
        print("Arguments passed to main:", args)
        if '--web' in args:
            from src.WebUI.server import start_web_server
            assert start_web_server()
    
    cli_loop()
    

if __name__ == "__main__":
    main()