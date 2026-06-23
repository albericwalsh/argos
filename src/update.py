
import os
from re import split

from src.utils import fetch_remote_app_properties, open_file
from src.variables import APP_VERSION, APP_REPOSITORY
import src.variables

APP_VERSION_UPDATE = None

def check_app_update():
    global APP_VERSION_UPDATE
    """Vérifie si une mise à jour de l'application est disponible."""
    try:
        if not src.variables.APP_REPOSITORY:
            print("Warning: 'APP_REPOSITORY' not specified in argos.properties.")
            return
        remote_properties = fetch_remote_app_properties(src.variables.APP_REPOSITORY)
        # recupère la version local et le repo dans argos.properties
        remote_version = None

        props = {}

        for line in remote_properties.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            k, v = line.split("=", 1)
            props[k.strip()] = v.strip().strip('"')

        remote_version = props.get("APP_VERSION")
                
        if remote_version is None:
            print("No version found in remote properties")
            return
        
        if src.variables.APP_VERSION != remote_version:
            APP_VERSION_UPDATE = f"{src.variables.APP_VERSION} → v{remote_version}"
        
        return {
        "checked": True,
        "local_version": src.variables.APP_VERSION or None,
        "remote_version": remote_version,
        "update_available": bool(src.variables.APP_VERSION) and remote_version != src.variables.APP_VERSION,
    }
    except Exception as e:
        print(e)

