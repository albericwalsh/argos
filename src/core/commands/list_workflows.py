import os

from src.core.command import command
from src.utils import open_file
from src.variables import APP_DIR

class ListWorkflowsCommand(command):
    def __init__(self):
        super().__init__(
            name='listwf',
            description='Affiche la liste des workflows disponibles',
            function=self.show_workflows
            )

    def show_workflows(self, *args):
        # get all workflows from the directory "data/workflows"
        workflows_text = "\
        #-----------------------------------------\n\
          > Workflows disponibles :\n\
        #------------------------------------------\n\n"
        for filename in os.listdir(os.path.join(APP_DIR, 'data/workflows')):
            if filename.endswith('.json'):
                wf = open_file(os.path.join(APP_DIR, 'data/workflows', filename))
                workflows_text += f"- {wf['name']} (ID: {wf['id']})\n"
        print(workflows_text) 