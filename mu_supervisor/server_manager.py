"""Server profile manager: list, select, and set default server configs."""

from __future__ import annotations

import glob
import os

SERVERS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "servers")
DEFAULT_FILE = os.path.join(SERVERS_DIR, ".default")


def list_servers() -> list[str]:
    """Return sorted list of server profile names (without .yaml extension)."""
    if not os.path.isdir(SERVERS_DIR):
        return []
    names = []
    for path in glob.glob(os.path.join(SERVERS_DIR, "*.yaml")):
        names.append(os.path.splitext(os.path.basename(path))[0])
    names.sort()
    return names


def get_default() -> str | None:
    """Read the default server name from servers/.default, or None."""
    if not os.path.isfile(DEFAULT_FILE):
        return None
    with open(DEFAULT_FILE, "r", encoding="utf-8") as fh:
        name = fh.read().strip()
    return name if name else None


def set_default(name: str) -> None:
    """Write the default server name to servers/.default."""
    os.makedirs(SERVERS_DIR, exist_ok=True)
    with open(DEFAULT_FILE, "w", encoding="utf-8") as fh:
        fh.write(name + "\n")


def get_config_path(name: str) -> str:
    """Return the full path for a server config: servers/{name}.yaml."""
    return os.path.join(SERVERS_DIR, f"{name}.yaml")


def server_menu() -> str:
    """Interactive menu to pick a server or calibrate a new one.

    Returns the config file path to use.
    """
    servers = list_servers()
    default = get_default()

    print("\n=== MU Automate — Configuracion ===\n")

    if servers:
        print("Servidores disponibles:")
        for i, name in enumerate(servers, 1):
            suffix = "  (default)" if name == default else ""
            print(f"  {i}. {name}{suffix}")
    else:
        print("No hay servidores configurados.")

    print(f"\n  N. Calibrar nuevo servidor\n")

    # Determine default choice
    default_choice = ""
    if default and default in servers:
        default_choice = str(servers.index(default) + 1)

    prompt = f"Elegir [{default_choice}]: " if default_choice else "Elegir: "
    choice = input(prompt).strip()

    # Default selection
    if not choice and default_choice:
        choice = default_choice

    # Calibrate new server
    if choice.upper() == "N":
        return _calibrate_new()

    # Pick existing server
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(servers):
            name = servers[idx]
            set_default(name)
            print(f"\nServidor seleccionado: {name}")
            return get_config_path(name)
    except (ValueError, IndexError):
        pass

    print("Opcion invalida.")
    return server_menu()


def _calibrate_new() -> str:
    """Run the calibration flow for a new server and return its config path."""
    # Import here to avoid circular deps and keep tools/ optional
    from tools.calibrate_launcher import calibrate_new_server

    config_path = calibrate_new_server(SERVERS_DIR)
    name = os.path.splitext(os.path.basename(config_path))[0]
    set_default(name)
    return config_path
