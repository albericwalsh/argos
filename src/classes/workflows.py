"""
src/classes/workflows.py
─────────────────────────
SÉCURITÉ : Workflow ne lit plus jamais un fichier .json en clair sur
disque (open_file(self.path) a été supprimé). Un Workflow est désormais
construit à partir d'un dict déjà déchiffré, obtenu via
src.WebUI.crypto_bridge.fetch_and_decrypt_json() — appelé uniquement
dans le contexte d'une requête authentifiée (post-login).
"""

from src.variables import get_modules


class Workflow:
    def __init__(self, wf_dict: dict, source_name: str | None = None):
        """
        wf_dict      : contenu JSON déjà déchiffré du workflow
        source_name  : nom du fichier .enc d'origine (informatif uniquement,
                       utilisé pour les ré-écritures via l'API, pas pour
                       relire en clair sur disque)
        """
        self.source_name = source_name
        self.results      = {}
        self.status        = "pending"
        self.progress      = None   # injecté par Mission.execute()
        self.load(wf_dict)

    @classmethod
    def from_dict(cls, wf_dict: dict, source_name: str | None = None) -> "Workflow":
        return cls(wf_dict, source_name=source_name)

    @property
    def raw_steps(self):
        return self.wf.get("steps", [])

    def load(self, wf_dict: dict):
        self.wf           = wf_dict
        self.id            = self.wf.get("id")
        self.name          = self.wf.get("name")
        self.description   = self.wf.get("description")
        self.entry_args    = self.wf.get("inputs", {})
        self.steps         = []
        for step in self.wf.get("steps", []):
            module = get_modules(step.get("module"))
            if module is None:
                print(f"ERROR : No module '{step.get('module')}' found.")
                return
            self.steps.append(module)

    def run(self, inputs):
        missing = [key for key in self.entry_args if key not in inputs]
        if missing:
            print(f"Inputs manquants : {missing}")
            print(f"Inputs requis : {list(self.entry_args.keys())}")
            self.status = "failed"
            return None

        context     = {"inputs": inputs}
        failed_step = None
        prog        = self.progress

        for step_data in self.wf.get("steps", []):
            step_id   = step_data.get("id")
            module_id = step_data.get("module")

            module = next((m for m in self.steps if m.id == module_id), None)
            if module is None:
                msg = f"Module '{module_id}' introuvable pour step '{step_id}'"
                print(f"ERROR: {msg}")
                if prog: prog.finish_step(step_id, error=msg)
                context[step_id] = {"output": None, "error": msg}
                failed_step = step_id
                break

            resolved_args = {}
            for arg_key, arg_val in step_data.get("args", {}).items():
                resolved_args[arg_key] = self.resolve_value(arg_val, context)

            print(f"Running step '{step_id}' with module '{module_id}'...")
            if prog: prog.start_step(step_id)

            try:
                args_to_pass = resolved_args.get(module.entry_arg) if module.entry_arg else resolved_args
                output = self._run_with_log_capture(module, args_to_pass, step_id, prog)
                context[step_id] = {"output": output}
                if prog: prog.finish_step(step_id)

            except Exception as e:
                error_msg = str(e)
                print(f"ERROR: Step '{step_id}' a échoué : {error_msg}")
                if prog: prog.finish_step(step_id, error=error_msg)
                context[step_id] = {"output": None, "error": error_msg}
                failed_step = step_id
                break

        self.results = context
        self.status  = "failed" if failed_step else "completed"
        return context

    def _run_with_log_capture(self, module, args, step_id, prog):
        if prog is None:
            return module.execute(args)

        import sys
        import io

        class _SSEWriter(io.TextIOBase):
            def __init__(self, original, tracker, sid):
                self._orig    = original
                self._tracker = tracker
                self._sid     = sid
                self._buf     = ""

            def write(self, s):
                self._orig.write(s)
                self._orig.flush()
                self._buf += s
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    if line.strip():
                        self._tracker.log(self._sid, line)
                return len(s)

            def flush(self):
                self._orig.flush()

        old_stdout = sys.stdout
        sys.stdout = _SSEWriter(old_stdout, prog, step_id)
        try:
            return module.execute(args)
        finally:
            sys.stdout = old_stdout

    def resolve_value(self, value, context):
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        parts  = value[1:].split(".")
        result = context
        for part in parts:
            if isinstance(result, dict):
                result = result.get(part)
            else:
                return None
        return result