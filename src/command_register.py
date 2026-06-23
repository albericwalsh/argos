from src.core.commands.run import RunCommand
from src.core.commands.list_modules import ListModulesCommand
from src.core.commands.help import HelpCommand
from src.core.commands.list_workflows import ListWorkflowsCommand
from src.core.commands.login import LoginCommand
from src.core.commands.logout import LogoutCommand
from src.variables import register_command

def init_command():
    '''Initialise les commandes de base.'''
    register_command(HelpCommand())
    register_command(ListWorkflowsCommand())
    register_command(ListModulesCommand())
    register_command(RunCommand())
    register_command(LoginCommand())
    register_command(LogoutCommand())