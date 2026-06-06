from datetime import datetime
import os
import json

from src.utils import create_file
from src.variables import APP_DIR

class MissionEncoder(json.JSONEncoder):
        def default(self, obj): # type: ignore
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            if hasattr(obj, '__str__'):
                return str(obj)
            return super().default(obj)

class Mission:
    
    def __init__(self, name, workflow):
        self.id = "#MSN-" + str(abs(hash(name + datetime.now().isoformat())))[:8]
        self.name = name
        self.workflow = workflow
        self.status = "pending"
        self.result = None
        self.date_created = datetime.now()
        self.date_completed = None
    
    def execute(self, inputs):
        self.status = "running"
        try:
            self.result = self.workflow.run(inputs)
            self.status = "completed"
        except Exception as e:
            self.result = str(e)
            self.status = "failed"
        finally:
            self.date_completed = datetime.now()
            folder_name = f"{self.date_created.strftime('%Y-%m-%d_%H-%M-%S')}_{self.id}"
            folder_path = os.path.join(APP_DIR, f"data/missions/{folder_name}")
            os.makedirs(folder_path, exist_ok=True)
            data = {
                "id": self.id,
                "name": self.name,
                "workflow": self.workflow.id,
                "status": self.status,
                "inputs": inputs,
                "result": self.result,
                "date_created": self.date_created.isoformat(),
                "date_completed": self.date_completed.isoformat()
            }
            create_file(
                os.path.join(folder_path, f"{self.id}.json"),
                json.dumps(data, indent=2, ensure_ascii=False, cls=MissionEncoder)
            )