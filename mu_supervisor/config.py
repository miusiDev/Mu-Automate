"""Configuration loader: YAML file → validated Config dataclass."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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
class FarmingSpot:
    """A farming location with its level threshold and action."""
    name: str
    until_level: int
    farm_action: str  # "hold_right_click" or "middle_click"
    warp_button: Point | None = None
    spot: Point | None = None
    waypoints: List[Point] = field(default_factory=list)


@dataclass
class NavigationConfig:
    coords_region: Region
    spots: List[FarmingSpot]
    tolerance: int = 3
    step_delay: float = 1.5
    max_steps: int = 100


@dataclass
class LoginStep:
    """A single step in the launcher login sequence."""
    action: str          # "click" or "paste"
    label: str
    point: Point
    wait_after: float
    text: Optional[str] = None


@dataclass
class LauncherConfig:
    exe_path: str
    launcher_window_title: str
    connect_button: Point
    login_steps: List[LoginStep]


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
            login_steps = []
            for step_raw in lr.get("login_steps", []):
                login_steps.append(LoginStep(
                    action=step_raw["action"],
                    label=step_raw.get("label", ""),
                    point=Point(**step_raw["point"]),
                    wait_after=float(step_raw.get("wait_after", 0)),
                    text=step_raw.get("text"),
                ))
            launcher = LauncherConfig(
                exe_path=lr["exe_path"],
                launcher_window_title=lr.get("launcher_window_title", ""),
                connect_button=Point(**lr["connect_button"]),
                login_steps=login_steps,
            )

            navigation = None
            nav_raw = raw.get("navigation")
            if nav_raw is not None:
                spots = []
                for spot_raw in nav_raw.get("spots", []):
                    warp_btn = None
                    if "warp_button" in spot_raw:
                        warp_btn = Point(**spot_raw["warp_button"])
                    spot_pt = None
                    if "spot" in spot_raw:
                        spot_pt = Point(**spot_raw["spot"])
                    wps = [Point(**wp) for wp in spot_raw.get("waypoints", [])]
                    spots.append(FarmingSpot(
                        name=spot_raw["name"],
                        until_level=spot_raw["until_level"],
                        farm_action=spot_raw["farm_action"],
                        warp_button=warp_btn,
                        spot=spot_pt,
                        waypoints=wps,
                    ))
                navigation = NavigationConfig(
                    coords_region=Region(**nav_raw["coords_region"]),
                    spots=spots,
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
