"""Entry point for MU Online Supervisor."""

import sys

from mu_supervisor.config import Config
from mu_supervisor.logger_setup import setup_logger
from mu_supervisor.supervisor import Supervisor


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"

    config = Config.from_yaml(config_path)
    setup_logger(level=config.log_level)

    supervisor = Supervisor(config)
    supervisor.run()


if __name__ == "__main__":
    main()
