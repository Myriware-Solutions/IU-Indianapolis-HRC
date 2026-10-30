#!/usr/bin/env python3
"""Overlay point measurements from a CSV file on a Nikon ND2 image."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable
from dataclasses import dataclass

@dataclass
class RequiredArguments:
    # Required
    nd2_file:Path
    csv_file:Path
    output:Path
    # Optional
    channel:int         = 1
    csv_channel:str     = "all"
    time:int            = 1
    z:int               = 1
    position:int        = 1
    z_project:str       = "none"
    config:Path|None    = None
    color_by:str        = "type"
    color:str           = "#ff2d55"
    cmap:str            = "turbo"
    marker_size:float   = 24.0
    marker:str          = "o"
    alpha:float         = 0.85
    linewidth:float     = 0.6
    dpi:int             = 200
    no_filter_csv_z_t:bool = False
    title:str|None      = None

import numpy as np


def parse_args_s() -> RequiredArguments:
    parser = argparse.ArgumentParser(
        description="Overlay CSV point data on an ND2 plane and save a PNG."
    )
    parser.add_argument("nd2_file", type=Path, help="Input .nd2 file")
    parser.add_argument("csv_file", type=Path, help="CSV containing X and Y columns")
    parser.add_argument("output", type=Path, help="Output image (normally .png)")
    parser.add_argument(
        "--channel", type=int, default=1,
        help="1-based ND2 channel used as the background (default: 1)",
    )
    parser.add_argument(
        "--csv-channel", default="all",
        help="Only overlay this 1-based C-pos value, or 'all' (default: all)",
    )
    parser.add_argument("--time", type=int, default=1, help="1-based time point (default: 1)")
    parser.add_argument("--z", type=int, default=1, help="1-based Z plane (default: 1)")
    parser.add_argument(
        "--position", type=int, default=1,
        help="1-based stage/field position for ND2 files with P/S/V axis (default: 1)",
    )
    parser.add_argument(
        "--z-project", choices=("none", "max", "mean"), default="none",
        help="Project all Z planes instead of selecting --z (default: none)",
    )
    parser.add_argument(
        "--config", type=Path,
        help="TOML file mapping CSV Type numbers to colors and labels",
    )
    parser.add_argument(
        "--color-by", choices=("type", "value", "channel", "fixed"), default="type",
        help="How points are colored (default: categorical Type legend)",
    )
    parser.add_argument("--color", default="#ff2d55", help="Point color with --color-by fixed")
    parser.add_argument("--cmap", default="turbo", help="Matplotlib colormap for values")
    parser.add_argument("--marker-size", type=float, default=24.0, help="Marker area in points^2")
    parser.add_argument("--marker", default="o", help="Matplotlib marker (default: o)")
    parser.add_argument("--alpha", type=float, default=0.85, help="Marker opacity")
    parser.add_argument("--linewidth", type=float, default=0.6, help="Marker outline width")
    parser.add_argument("--dpi", type=int, default=200, help="Output resolution (default: 200)")
    parser.add_argument(
        "--no-filter-csv-z-t", action="store_true",
        help="Do not filter CSV rows by Z-pos and T-pos",
    )
    parser.add_argument("--title", default=None, help="Optional figure title")
    
    args = parser.parse_args()
    
    stash = RequiredArguments(**{k: v for k, v in args._get_kwargs()})
    
    print(stash)
    
    raise


def read_points(path: Path) -> list[dict[str, float]]:
    required = {"X", "Y"}
    numeric = ("Type", "Slice", "X", "Y", "Value", "C-pos", "Z-pos", "T-pos")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ValueError(f"CSV is missing required column(s): {', '.join(sorted(missing))}")
        points: list[dict[str, float]] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                point = {
                    name: float(row[name])
                    for name in numeric
                    if name in fields and row.get(name, "").strip() != ""
                }
            except ValueError as exc:
                raise ValueError(f"Non-numeric CSV value on line {line_number}: {exc}") from exc
            points.append(point)
    if not points:
        raise ValueError("CSV contains no data rows")
    return points


def load_type_config(path: Path | None) -> dict[int, dict[str, str]]:
    """Load [types."N"] label/color entries from TOML."""
    if path is None:
        return {}
    try:
        import tomllib
    except ImportError:  # Python 3.10
        try:
            import tomli as tomllib # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "Reading TOML on Python 3.10 requires 'tomli'. "
                "Run: python -m pip install -r requirements.txt"
            ) from exc
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    raw_types = document.get("types")
    if not isinstance(raw_types, dict):
        raise ValueError('Config must contain tables such as [types."1"]')
    result: dict[int, dict[str, str]] = {}
    for raw_number, settings in raw_types.items():
        try:
            number = int(raw_number)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid type number in config: {raw_number!r}") from exc
        if not isinstance(settings, dict):
            raise ValueError(f"Config entry for type {number} must be a TOML table")
        label = settings.get("label", f"Type {number}")
        color = settings.get("color")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Type {number} needs a non-empty text label")
        if not isinstance(color, str) or not color.strip():
            raise ValueError(f"Type {number} needs a color string")
        result[number] = {"label": label, "color": color}
    return result


def _one_based_index(value: int, size: int, label: str) -> int:
    if not 1 <= value <= size:
        raise ValueError(f"{label} must be between 1 and {size}; received {value}")
    return value - 1


def extract_plane(
    data: np.ndarray,
    axes: Iterable[str],
    *,
    channel: int,
    time: int,
    z: int,
    position: int,
    z_project: str,
) -> np.ndarray:
    """Select C/T/P and Z from an ND2 array while retaining Y and X."""
    axes = [str(axis).upper() for axis in axes]
    if data.ndim != len(axes):
        raise ValueError(f"ND2 axis metadata {axes} does not match array shape {data.shape}")

    selectors: list[object] = []
    kept_axes: list[str] = []
    for axis, size in zip(axes, data.shape):
        if axis in {"X", "Y"}:
            selectors.append(slice(None))
            kept_axes.append(axis)
        elif axis == "C":
            selectors.append(_one_based_index(channel, size, "channel"))
        elif axis == "T":
            selectors.append(_one_based_index(time, size, "time"))
        elif axis == "Z":
            if z_project == "none":
                selectors.append(_one_based_index(z, size, "z"))
            else:
                selectors.append(slice(None))
                kept_axes.append(axis)
        elif axis in {"P", "S", "V", "M"}:
            selectors.append(_one_based_index(position, size, f"position ({axis})"))
        else:
            if size != 1:
                raise ValueError(
                    f"Unsupported non-singleton ND2 axis {axis!r} (size {size}). "
                    "Please report the ND2 axis list so support can be added."
                )
            selectors.append(0)

    plane = np.asarray(data[tuple(selectors)]) # type: ignore
    if "Z" in kept_axes:
        z_axis = kept_axes.index("Z")
        plane = plane.max(axis=z_axis) if z_project == "max" else plane.mean(axis=z_axis)
        kept_axes.pop(z_axis)
    if set(kept_axes) != {"Y", "X"} or plane.ndim != 2:
        raise ValueError(f"Could not reduce ND2 to Y/X; remaining axes are {kept_axes}")
    if kept_axes == ["X", "Y"]:
        plane = plane.T
    return plane


def filter_points(points: list[dict[str, float]], args: RequiredArguments) -> list[dict[str, float]]:
    selected = points
    if args.csv_channel.lower() != "all":
        try:
            csv_channel = int(args.csv_channel)
        except ValueError as exc:
            raise ValueError("--csv-channel must be an integer or 'all'") from exc
        selected = [p for p in selected if int(p.get("C-pos", csv_channel)) == csv_channel]
    if not args.no_filter_csv_z_t:
        if any("T-pos" in p for p in selected):
            selected = [p for p in selected if int(p.get("T-pos", args.time)) == args.time]
        if args.z_project == "none" and any("Z-pos" in p for p in selected):
            selected = [p for p in selected if int(p.get("Z-pos", args.z)) == args.z]
    return selected


def create_overlay(args: RequiredArguments) -> None:
    if args.output.suffix.lower() != ".png":
        print(f"Note: output extension is {args.output.suffix!r}; PNG is recommended.")

    try:
        import nd2
    except ImportError as exc:
        raise SystemExit("Missing dependency 'nd2'. Run: python -m pip install -r requirements.txt") from exc

    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm
    from matplotlib.lines import Line2D

    points = filter_points(read_points(args.csv_file), args)
    if not points:
        raise SystemExit("No CSV points remain after applying the requested filters.")

    with nd2.ND2File(args.nd2_file) as image_file:
        axes = list(image_file.sizes.keys())
        data = image_file.asarray()
    plane = extract_plane(
        data, axes, channel=args.channel, time=args.time, z=args.z,
        position=args.position, z_project=args.z_project,
    )

    x = np.array([p["X"] for p in points])
    y = np.array([p["Y"] for p in points])
    inside = (x >= 0) & (x < plane.shape[1]) & (y >= 0) & (y < plane.shape[0])
    if not inside.any():
        raise SystemExit(
            f"No points fall inside image bounds X=[0,{plane.shape[1]-1}], "
            f"Y=[0,{plane.shape[0]-1}]. Check that CSV and ND2 files correspond."
        )
    if not inside.all():
        print(f"Warning: omitting {(~inside).sum()} point(s) outside the image bounds.")
    points = [p for p, keep in zip(points, inside) if keep]
    x, y = x[inside], y[inside]

    fig, ax = plt.subplots(figsize=(10, 10), constrained_layout=True)
    low, high = np.percentile(plane, (0.5, 99.5))
    if high <= low:
        low, high = float(plane.min()), float(plane.max() or 1)
    ax.imshow(plane, cmap="gray", vmin=low, vmax=high, origin="upper")

    scatter_kwargs:dict = dict(
        s=args.marker_size, marker=args.marker, alpha=args.alpha,
        linewidths=args.linewidth, edgecolors="white",
    )
    if args.color_by == "type":
        if not all("Type" in p for p in points):
            raise SystemExit("--color-by type requires a Type column in the CSV.")
        mismatches = sum(
            1 for p in points
            if "Slice" in p and int(p["Type"]) != int(p["Slice"])
        )
        if mismatches:
            print(f"Warning: {mismatches} row(s) have different Type and Slice values; using Type.")
        type_config = load_type_config(args.config)
        type_numbers = sorted({int(p["Type"]) for p in points})
        default_colors = plt.get_cmap("tab10").colors # type: ignore
        legend_handles = []
        for offset, type_number in enumerate(type_numbers):
            settings = type_config.get(type_number, {})
            color = settings.get("color", default_colors[offset % len(default_colors)])
            label = settings.get("label", f"Type {type_number}")
            mask = np.array([int(p["Type"]) == type_number for p in points])
            ax.scatter(x[mask], y[mask], color=color, **scatter_kwargs)
            legend_handles.append(Line2D(
                [0], [0], linestyle="", marker=args.marker, markersize=max(4, args.marker_size ** 0.5),
                markerfacecolor=color, markeredgecolor="white", label=label,
            ))
        ax.legend(handles=legend_handles, title="Type", loc="upper right", framealpha=0.85)
    elif args.color_by == "value":
        if not all("Value" in p for p in points):
            raise SystemExit("--color-by value requires a Value column in the CSV.")
        values = np.array([p["Value"] for p in points])
        plotted = ax.scatter(x, y, c=values, cmap=args.cmap, **scatter_kwargs)
        fig.colorbar(plotted, ax=ax, shrink=0.75, label="CSV Value")
    elif args.color_by == "channel":
        if not all("C-pos" in p for p in points):
            raise SystemExit("--color-by channel requires a C-pos column in the CSV.")
        channels = np.array([int(p["C-pos"]) for p in points])
        unique = np.unique(channels)
        bounds = np.r_[unique - 0.5, unique[-1] + 0.5]
        plotted = ax.scatter(
            x, y, c=channels, cmap="tab10", norm=BoundaryNorm(bounds, 10), **scatter_kwargs
        )
        colorbar = fig.colorbar(plotted, ax=ax, shrink=0.75, ticks=unique)
        colorbar.set_label("CSV channel (C-pos)")
    else:
        ax.scatter(x, y, color=args.color, **scatter_kwargs)

    ax.set_xlim(-0.5, plane.shape[1] - 0.5)
    ax.set_ylim(plane.shape[0] - 0.5, -0.5)
    ax.set_xlabel("X (pixels)")
    ax.set_ylabel("Y (pixels)")
    ax.set_title(args.title or f"{args.nd2_file.stem} — {len(points)} overlaid points")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=args.dpi, facecolor="black")
    plt.close(fig)
    print(f"Saved {args.output} ({plane.shape[1]} x {plane.shape[0]} pixels, {len(points)} points)")


if __name__ == "__main__":
    args = parse_args_s()
    create_overlay(args)
    
# Author(s): ChatGPT, Anthony Smith