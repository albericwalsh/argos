
import os
from re import split

from src.utils import fetch_remote_app_properties, open_file
from src.variables import APP_VERSION, APP_REPOSITORY

APP_VERSION_UPDATE = None

def check_need_update(local_version, remote_version):
    # x.x.x
    la = split(local_version, ".")[0]
    lb = split(local_version, ".")[1]
    lc = split(local_version, ".")[2]

    ra = split(local_version, ".")[0]
    rb = split(local_version, ".")[1]
    rc = split(local_version, ".")[2]

    if la < ra :
        return True
    if lb < rb :
        return True
    if lc < rc :
        return True
    
    return False
    

def check_app_update():
    """Vérifie si une mise à jour de l'application est disponible."""
    global APP_VERSION, APP_REPOSITORY
    try:
        if not APP_REPOSITORY:
            print("Warning: 'repo' not specified in argos.properties.")
            return
        remote_properties = fetch_remote_app_properties(APP_REPOSITORY)
        # recupère la version local et le repo dans argos.properties
        for line in remote_properties:
            if line.startswith('APP_VERSION'):
                remote_version = line.split('=')[1].strip().strip('"')
                
        if not remote_version: # type: ignore
            print("error")
            return
        
        if check_need_update(APP_VERSION, remote_version):
            APP_VERSION_UPDATE = f"v{APP_VERSION} → v{remote_version}"
    except Exception as e:
        print(e)

