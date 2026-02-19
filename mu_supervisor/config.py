"""Configuration loader: YAML file → validated Config dataclass."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

import yaml

from .exceptions import ConfigError


@dataclass
class Region:
    x: int
    y: int
    w: int
    h: int


@dataclass
class Point:
    """A simple x, y screen coordinate (for buttons)."""
    x: int
    y: int


@dataclass
class OcrRegions:
    level: Region
    experience: Region


@dataclass
class StatsConfig:
    interval_levels: int
    points_per_level: int
    distribution: Dict[str, float]

    def __post_init__(self) -> None:
        total = sum(self.distribution.values())
        if abs(total - 1.0) > 0.01:
            raise ConfigError(
                f"Stat distribution ratios must sum to 1.0, got {total:.2f}"
            )
        for key in self.distribution:
            if key not in ("str", "agi", "vit", "ene"):
                raise ConfigError(f"Unknown stat key: {key!r}")


@dataclass
class NavigationConfig:
    coords_region: Region
    spot: Point
    waypoints: List[Point]
    tolerance: int = 3
    step_delay: float = 1.5
    max_steps: int = 100


@dataclass
class LauncherConfig:
    exe_path: str
    password: str
    start_button: Point
    server_button: Point
    sub_server_button: Point
    password_field: Point
    ok_button: Point
    connect_button: Point


@dataclass
class Config:
    window_title: str
    tesseract_path: str
    ocr_regions: OcrRegions
    stats: StatsConfig
    reset_level: int
    launcher: LauncherConfig
    navigation: NavigationConfig | None = None
    loop_interval_seconds: int = 30
    log_level: str = "INFO"

    @classmethod
    def from_yaml(cls, path: str) -> Config:
        """Load configuration from a YAML file."""
        if not os.path.isfile(path):
            raise ConfigError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        if not isinstance(raw, dict):
            raise ConfigError("Config file must be a YAML mapping")

        try:
            ocr_raw = raw["ocr_regions"]
            ocr_regions = OcrRegions(
                level=Region(**ocr_raw["level"]),
                experience=Region(**ocr_raw["experience"]),
            )

            stats_raw = raw["stats"]
            stats = StatsConfig(
                interval_levels=stats_raw["interval_levels"],
                points_per_level=stats_raw["points_per_level"],
                distribution=stats_raw["distribution"],
            )

            lr = raw["launcher"]
            launcher = LauncherConfig(
                exe_path=lr["exe_path"],
                password=lr["password"],
                start_button=Point(**lr["start_button"]),
                server_button=Point(**lr["server_button"]),
                sub_server_button=Point(**lr["sub_server_button"]),
                password_field=Point(**lr["password_field"]),
                ok_button=Point(**lr["ok_button"]),
                connect_button=Point(**lr["connect_button"]),
            )

            navigation = None
            nav_raw = raw.get("navigation")
            if nav_raw is not None:
                waypoints = [
                    Point(**wp) for wp in nav_raw.get("waypoints", [])
                ]
                navigation = NavigationConfig(
                    coords_region=Region(**nav_raw["coords_region"]),
                    spot=Point(**nav_raw["spot"]),
                    waypoints=waypoints,
                    tolerance=nav_raw.get("tolerance", 3),
                    step_delay=nav_raw.get("step_delay", 1.5),
                    max_steps=nav_raw.get("max_steps", 100),
                )

            return cls(
                window_title=raw["window_title"],
                tesseract_path=raw["tesseract_path"],
                ocr_regions=ocr_regions,
                stats=stats,
                reset_level=raw["reset_level"],
                launcher=launcher,
                navigation=navigation,
                loop_interval_seconds=raw.get("loop_interval_seconds", 30),
                log_level=raw.get("log_level", "INFO"),
            )
        except KeyError as exc:
            raise ConfigError(f"Missing config key: {exc}") from exc
        except TypeError as exc:
            raise ConfigError(f"Invalid config structure: {exc}") from exc
