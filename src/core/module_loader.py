import os
from src.classes.modules import Module
from src.utils import open_file
from src.variables import APP_DIR, MODULES_REGISTERY


def init_modules_registery():
    '''Initialise le registre des modules (vide d'abord, pour permettre un rechargement à chaud).'''
    MODULES_REGISTERY.clear()
    modules_dir = os.path.join(APP_DIR, 'data/modules')
    if not os.path.isdir(modules_dir):
        os.makedirs(modules_dir, exist_ok=True)
        return

    for folder_name in os.listdir(modules_dir):

            folder_path = os.path.join(
                modules_dir,
                folder_name
            )

            # Vérifie que c'est bien un dossier
            if os.path.isdir(folder_path):

                module_json = os.path.join(
                    folder_path,
                    'module.json'
                )

                # Vérifie que module.json existe
                if os.path.exists(module_json):

                    try:
                        MODULES_REGISTERY.append(
                            Module(folder_path)
                        )
                    except Exception as e:
                        print(f"Error loading module from {folder_path}: {e}")


def reload_modules_registery():
    '''
    Recharge le registre des modules à chaud, après installation/suppression
    d'un module via le panel WebUI — sans nécessiter de redémarrage du process.
    '''
    init_modules_registery()
    return MODULES_REGISTERY