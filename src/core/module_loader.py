import os
from src.classes.modules import Module
from src.utils import open_file
from src.variables import APP_DIR, MODULES_REGISTERY

def init_modules_registery():
    '''Initialise le registre des modules.'''
    modules_dir = os.path.join(APP_DIR, 'data/modules')
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