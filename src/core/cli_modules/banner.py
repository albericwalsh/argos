import os

import src.utils
from src.variables import APP_DIR, APP_NAME, APP_VERSION
from src.update import APP_VERSION_UPDATE
import src.variables
import src.update

def print_banner():
    if src.update.APP_VERSION_UPDATE :
        version = src.update.APP_VERSION_UPDATE
    else:
        version = src.variables.APP_VERSION

    banner = src.utils.open_file(os.path.join(APP_DIR, 'banner.txt'))
    banner += f"    Autonomous Recon & Operations Grid System \n"
    banner += f"─────────────────────────────────────────────────────── \n"
    banner += f"        {src.variables.APP_NAME} v{version} | Cyber Workflow Engine \n"
    banner += f"───────────────────────────────────────────────────────\n"
    print(banner, flush=True)