import os
from src.utils import open_file


APP_DIR = ""
APP_NAME = ""
APP_VERSION = ""
APP_DESCRIPTION = ""
APP_AUTHOR = ""
APP_LICENSE = ""
APP_REPOSITORY = ""


LOG_LEVEL = ""
DATA_STORAGE_PATH = ""


WEB_SERVER_HOST = 'localhost'
WEB_SERVER_PORT = 8080
CORS_ORIGINS = []
CORS_METHODS = []
CORS_HEADERS = []

COMMANDS_REGISTERY = []

MODULES_REGISTERY = []
WORKFLOWS_REGISTERY = []
MISSIONS_REGISTERY = []

def init_app_variables(app_dir):
    '''Initialise les variables de l'application.'''
    global APP_DIR, APP_NAME, APP_VERSION
    APP_DIR = app_dir
    with open_file(os.path.join(APP_DIR, 'argos.properties')) as f:
        for line in f:
            if line.startswith('APP_NAME'):
                APP_NAME = line.split('=')[1].strip().strip('"')
            elif line.startswith('APP_VERSION'):
                APP_VERSION = line.split('=')[1].strip().strip('"')
            elif line.startswith('WEB_SERVER_HOST'):
                global WEB_SERVER_HOST
                WEB_SERVER_HOST = line.split('=')[1].strip().strip('"')
            elif line.startswith('WEB_SERVER_PORT'):
                global WEB_SERVER_PORT
                WEB_SERVER_PORT = int(line.split('=')[1].strip().strip('"'))
            elif line.startswith('DATA_STORAGE_PATH'):
                global DATA_STORAGE_PATH
                DATA_STORAGE_PATH = line.split('=')[1].strip().strip('"')
            elif line.startswith('LOG_LEVEL'):
                global LOG_LEVEL
                LOG_LEVEL = line.split('=')[1].strip().strip('"')
            elif line.startswith('APP_DESCRIPTION'):
                global APP_DESCRIPTION
                APP_DESCRIPTION = line.split('=')[1].strip().strip('"')
            elif line.startswith('APP_AUTHOR'):
                global APP_AUTHOR
                APP_AUTHOR = line.split('=')[1].strip().strip('"')
            elif line.startswith('APP_LICENSE'):
                global APP_LICENSE
                APP_LICENSE = line.split('=')[1].strip().strip('"')
            elif line.startswith('APP_REPOSITORY'):
                global APP_REPOSITORY
                APP_REPOSITORY = line.split('=')[1].strip().strip('"')
            elif line.startswith('CORS_ORIGINS'):
                global CORS_ORIGINS
                CORS_ORIGINS = [v.strip().strip('"') for v in line.split('=', 1)[1].strip().strip('[]').split(',')]
            elif line.startswith('CORS_METHODS'):
                global CORS_METHODS
                CORS_METHODS = [v.strip().strip('"') for v in line.split('=', 1)[1].strip().strip('[]').split(',')]
            elif line.startswith('CORS_HEADERS'):
                global CORS_HEADERS
                CORS_HEADERS = [v.strip().strip('"') for v in line.split('=', 1)[1].strip().strip('[]').split(',')]
            


def register_command(command):
    '''Enregistre une commande dans le registre des commandes.'''
    if command.name not in COMMANDS_REGISTERY:
        COMMANDS_REGISTERY.append(command)

    
def get_modules(id):
    for module in MODULES_REGISTERY:
        if module.id == id:
            return module
    print(f"No modume with id {id}")
    return None