"""Custom exception hierarchy for MU Supervisor."""


class MuSupervisorError(Exception):
    """Base exception for all MU Supervisor errors."""


class ConfigError(MuSupervisorError):
    """Invalid or missing configuration."""


class OCRError(MuSupervisorError):
    """OCR reading failed."""


class CaptchaError(MuSupervisorError):
    """Captcha resolution failed after retries."""


class GameWindowError(MuSupervisorError):
    """Game window not found or lost focus."""


class WebResetError(MuSupervisorError):
    """Web-based reset process failed."""


class LaunchError(MuSupervisorError):
    """Game launch or character selection failed."""


class DistributionError(MuSupervisorError):
    """Stat point distribution failed."""
