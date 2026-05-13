from src.utils import get_modules, open_file


class Workflow:
    def __init__(self, path):
        self.path = path
        wf = open_file(self.path)
        self.id = wf.get("id")

    def load(self):
        wf = open_file(self.path)
        self.id = wf.get("id")
        self.name = wf.get("name")
        self.description = wf.get("description")
        self.entry_args = wf.get("entry", {}).get("args", {})
        self.steps = []
        for step in wf.get("steps", []):
            try:
                self.steps.append(get_modules(step.module))
            except:
                print(f"ERROR : No module {step.module} found.")
                return

    
    def run(self, args):
        # //TODO faire la lecture du workflow ici
        for step in self.steps:
            step.run(args)
