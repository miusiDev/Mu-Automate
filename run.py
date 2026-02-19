"""Entry point for MU Online Supervisor."""

import argparse
import os

from mu_supervisor.config import Config
from mu_supervisor.logger_setup import setup_logger
from mu_supervisor.server_manager import get_config_path, get_default, server_menu
from mu_supervisor.supervisor import Supervisor


def resolve_config_path() -> str:
    """Resolve config path from servers/.default, falling back to config.yaml."""
    default_name = get_default()
    if default_name:
        path = get_config_path(default_name)
        if os.path.isfile(path):
            return path
    # Fallback to root config.yaml
    return "config.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description="MU Online Supervisor")
    parser.add_argument(
        "config_path",
        nargs="?",
        default=None,
        help="Ruta explicita a un config.yaml",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        dest="config_menu",
        help="Menu interactivo para elegir o calibrar un servidor",
    )
    args = parser.parse_args()

    if args.config_menu:
        config_path = server_menu()
    elif args.config_path:
        config_path = args.config_path
    else:
        config_path = resolve_config_path()

    config = Config.from_yaml(config_path)
    setup_logger(level=config.log_level)

    supervisor = Supervisor(config)
    supervisor.run()


if __name__ == "__main__":
    main()
