import os
import importlib.util

from src.utils import open_file


class Module:

    def __init__(self, directory):

        self.directory = directory

        # Chargement du module.json
        module_file = open_file(
            os.path.join(directory, 'module.json')
        )

        self.id = module_file.get('id')
        self.name = module_file.get('name')
        self.category = module_file.get('category')
        self.description = module_file.get('description')
        self.entry_arg = module_file.get('entry_arg')
        # Chargement dynamique du entry.py
        entry_path = os.path.join(directory, 'entry.py')

        self.entry = self.load_entry(entry_path)

    def load_entry(self, entry_path):

        if not os.path.exists(entry_path):

            raise FileNotFoundError(
                f"entry.py not found in {self.directory}"
            )

        module_name = f"argos_module_{self.id}"

        spec = importlib.util.spec_from_file_location(
            module_name,
            entry_path
        )
        
        assert spec is not None, f"Failed to load module spec for {entry_path}"

        loaded_module = importlib.util.module_from_spec(spec)
        
        assert spec.loader is not None, f"Module spec loader is None for {entry_path}"

        spec.loader.exec_module(loaded_module)

        if not hasattr(loaded_module, 'main'):

            raise Exception(
                f"Module '{self.id}' "
                f"does not define main(args)"
            )

        return loaded_module.main

    def execute(self, args=None):

        if args is None:
            args = {}

        return self.entry(args)