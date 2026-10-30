# ND2 + CSV overlay exporter

This program opens a Nikon `.nd2` microscopy file, selects one image plane (or
creates a Z projection), overlays point measurements from a CSV, and saves a
PNG. It is configured for CSV files like `K107.5-2_Hema01.csv`, which contain
`X`, `Y`, `Value`, `C-pos`, `Z-pos`, and `T-pos` columns.

## Setup

Python 3.10 or newer is recommended.

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux instead
# source .venv/bin/activate

python -m pip install -r requirements.txt
```

## Basic use

Put the `.nd2`, CSV, and script in the same folder, then run:

```bash
python nd2_csv_overlay.py experiment.nd2 K107.5-2_Hema01.csv overlay.png
```

The background defaults to ND2 channel 1, Z plane 1, and time point 1. CSV
points are grouped into categorical colors by `Type`, with a legend instead of
an intensity heatmap. Channel, Z, time, and position arguments are **1-based**,
matching the convention in the example CSV.

## Type labels and colors with TOML

Copy and edit `overlay_config.toml`, then pass it with `--config`:

```bash
python nd2_csv_overlay.py experiment.nd2 points.csv overlay.png \
  --config overlay_config.toml
```

Each type is configured in its own table:

```toml
[types."1"]
label = "Nucleus"
color = "#e41a1c"

[types."2"]
label = "Cell membrane"
color = "deepskyblue"
```

Types omitted from the config still appear, using an automatic color and a
label such as `Type 3`. Configured types that are absent from the selected CSV
rows are omitted from the legend.

Useful examples:

```bash
# Use ND2 channel 2 as the background and show only CSV channel 2 points
python nd2_csv_overlay.py experiment.nd2 points.csv overlay.png \
  --channel 2 --csv-channel 2

# Maximum-intensity projection across Z; color points by CSV channel
python nd2_csv_overlay.py experiment.nd2 points.csv max_projection.png \
  --z-project max --color-by channel

# Larger fixed red circle markers at time point 3
python nd2_csv_overlay.py experiment.nd2 points.csv time3.png \
  --time 3 --color-by fixed --color red --marker-size 50
```

Run `python nd2_csv_overlay.py --help` for every option.

## Coordinate assumptions

- `X` and `Y` are interpreted as zero-based pixel coordinates measured from
  the top-left of the ND2 image.
- The micron-coordinate columns are not used; this avoids dependence on ND2
  calibration metadata when the CSV already provides pixel positions.
- By default, CSV rows are filtered to the requested `Z-pos` and `T-pos`.
  `--csv-channel all` keeps points from all CSV channels. Use
  `--no-filter-csv-z-t` to disable the Z/time filtering.
- Points outside the ND2 image bounds are omitted with a warning. If every
  point is out of bounds, the program stops, which usually indicates that the
  CSV and ND2 do not correspond or that coordinates need transformation.
- `Type` determines the default categorical color and legend entry. When a
  row's `Type` and `Slice` differ, the program warns and uses `Type`.

## Notes

The exporter loads the selected ND2 dataset into memory. For unusually large
ND2 files, close other memory-heavy programs first. Some ND2 files contain
unusual axes; if the script reports an unsupported axis, preserve the error
message because it includes the axis name needed to extend support.
