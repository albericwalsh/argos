import json
import yaml


def open_file(file_path, mode='r'):
    """Ouvre un fichier selon son extension."""

    try:
        # TXT
        if file_path.endswith('.txt'):
            with open(file_path, mode, encoding='utf-8') as file:
                return file.read()

        # JSON
        elif file_path.endswith('.json'):
            with open(file_path, mode, encoding='utf-8') as file:
                return json.load(file)

        # YAML
        elif file_path.endswith(('.yaml', '.yml')):
            with open(file_path, mode, encoding='utf-8') as file:
                return yaml.safe_load(file)

        # PROPERTIES
        elif file_path.endswith('.properties'):
            return open(file_path, mode, encoding='utf-8')

        # AUTRES
        else:
            print(f"Warning: Unsupported file type for '{file_path}'")

            with open(file_path, mode, encoding='utf-8') as file:
                return file.read()

    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        raise

    except Exception as e:
        print(f"Error while reading '{file_path}': {e}")
        raise
    
def delete_parameters(args):
    """Supprime les paramètres d'une liste d'arguments."""
    # Aplatit si args est un tuple contenant une liste
    if isinstance(args, tuple):
        args = [item for sublist in args for item in (sublist if isinstance(sublist, list) else [sublist])]
    return [arg for arg in args if not isinstance(arg, str) or not arg.startswith((" /"))]

