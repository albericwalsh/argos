import os

import src.utils
from src.variables import APP_DIR

def print_banner():
    banner = src.utils.open_file(os.path.join(APP_DIR, 'banner.txt'))
    print(banner, flush=True)