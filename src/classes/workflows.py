from src.variables import get_modules
from src.utils import open_file


class Workflow:
    def __init__(self, path):
        self.path = path
        wf = open_file(self.path)
        self.id = wf.get("id")
        self.results = {}  # stockage des résultats du dernier run
        self.load()


    def load(self):
        self.wf = open_file(self.path)
        self.id = self.wf.get("id")
        self.name = self.wf.get("name")
        self.description = self.wf.get("description")
        self.entry_args = self.wf.get("inputs", {})
        self.steps = []
        for step in self.wf.get("steps", []):
            module = get_modules(step.get("module"))
            if module is None:
                print(f"ERROR : No module '{step.get('module')}' found.")
                return
            self.steps.append(module)
        print(self.wf)

    
    def run(self, inputs):
        # Vérifier que tous les entry_args requis sont présents dans inputs
        missing = [key for key in self.entry_args if key not in inputs]
        if missing:
            print(f"Inputs manquants : {missing}")
            print(f"Inputs requis : {list(self.entry_args.keys())}")
            return None

        context = {"inputs": inputs}  # stocke les outputs de chaque step

        for step_data in self.wf.get("steps", []):
            step_id = step_data.get("id")
            module_id = step_data.get("module")

            module = next((m for m in self.steps if m.id == module_id), None)
            if module is None:
                print(f"ERROR: Module '{module_id}' introuvable pour step '{step_id}'")
                context[step_id] = {"output": None, "error": f"Module '{module_id}' introuvable"}
                break  # stop mais contexte préservé

            resolved_args = {}
            for arg_key, arg_val in step_data.get("args", {}).items():
                resolved_args[arg_key] = self.resolve_value(arg_val, context)

            print(f"Running step '{step_id}' with module '{module_id}'...")
            try:
                args_to_pass = resolved_args.get(module.entry_arg) if module.entry_arg else resolved_args
                output = module.execute(args_to_pass)
                context[step_id] = {"output": output}
            except Exception as e:
                print(f"ERROR: Step '{step_id}' a échoué : {e}")
                context[step_id] = {"output": None, "error": str(e)}
                break

        self.results = context  # toujours sauvegardé, même en cas d'erreur
        return context

    def resolve_value(self, value, context):
        """Résout les références comme $inputs.domaine ou $step1.output.port"""
        if not isinstance(value, str) or not value.startswith("$"):
            return value

        parts = value[1:].split(".")  # ["inputs", "domaine"] ou ["step1", "output", "port"]
        result = context
        for part in parts:
            if isinstance(result, dict):
                result = result.get(part)
            else:
                return None
        return result
            