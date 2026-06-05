import os

from src.classes.workflows import Workflow
from src.variables import APP_DIR, WORKFLOWS_REGISTERY
from src.utils import open_file


def init_worflow_registery():
    '''Initialise le registre des workflows.'''
    modules_dir = os.path.join(APP_DIR, 'data/workflows')
    for filename in os.listdir(modules_dir):
        WORKFLOWS_REGISTERY.append(Workflow(os.path.join(modules_dir, filename)))
    for w in WORKFLOWS_REGISTERY:
        print(w.id)