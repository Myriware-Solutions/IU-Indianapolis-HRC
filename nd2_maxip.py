#!/usr/bin/env python3
"""
nd2_maxip.py - Split Nikon .nd2 multipoint z-stacks into per-point
max-intensity projections and save each as a TIFF.

Install:
    pip install nd2 tifffile numpy dask

Usage:
    python nd2_maxip.py file.nd2
    python nd2_maxip.py folder_of_nd2s -o output_dir
    python nd2_maxip.py a.nd2 b.nd2 -o out --overwrite
    python nd2_maxip.py file.nd2 --simple              # 8-bit RGB for Windows/PowerPoint

Output: <output_dir>/<nd2 name>_P001_<position name>.tif, _P002_<name>.tif, ...
(the position name is the one set in NIS-Elements; characters that Windows
does not allow in file names are replaced with underscores)
Each TIFF is an ImageJ-compatible hyperstack (axes T, C, Y, X) with
pixel size (um) stored, so it opens with correct scaling in Fiji.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import nd2
import tifffile

# Order used when writing (ImageJ requires T, Z, C, Y, X, S ordering)
OUT_ORDER = ["T", "C", "Y", "X", "S"]


def reorder(arr, dims):
    """Reorder arr (with axis labels dims) to OUT_ORDER, adding singleton
    T/C axes if missing so output is always at least TCYX."""
    for ax in ("T", "C"):
        if ax not in dims:
            arr = arr[np.newaxis, ...]
            dims = [ax] + dims
    order = [d for d in OUT_ORDER if d in dims]
    extra = [d for d in dims if d not in order]  # unexpected axes (e.g. 'L')
    order = extra + order
    perm = [dims.index(d) for d in order]
    return np.transpose(arr, perm), order


DEFAULT_COLORS = [(0, 0, 255), (0, 255, 0), (255, 0, 0),
                  (255, 0, 255), (0, 255, 255), (255, 255, 0)]


NAMED_COLORS = {
    "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
    "cyan": (0, 255, 255), "magenta": (255, 0, 255), "yellow": (255, 255, 0),
    "orange": (255, 128, 0), "gray": (255, 255, 255), "white": (255, 255, 255),
}


def parse_colors(text):
    """'blue,red' or '#0000ff,#ff0000' -> [(r,g,b), ...]"""
    out = []
    for tok in text.split(","):
        tok = tok.strip().lower()
        if tok in NAMED_COLORS:
            out.append(NAMED_COLORS[tok])
        elif len(tok) == 7 and tok.startswith("#"):
            out.append(tuple(int(tok[i:i + 2], 16) for i in (1, 3, 5)))
        else:
            raise ValueError(f"Unknown color '{tok}'")
    return out


def channel_colors(f, n):
    """Per-channel display colors (R, G, B) from the ND2 metadata.
    Falls back to a default palette (grayscale if there is one channel)."""
    try:
        cols = []
        for ch in f.metadata.channels[:n]:
            meta = ch.channel
            if hasattr(meta, "color"):  # current nd2 versions: Color(r,g,b,a)
                col = (int(meta.color.r), int(meta.color.g), int(meta.color.b))
            else:  # older nd2 versions: packed 0x00BBGGRR integer
                c = int(meta.colorRGB)
                col = (c & 255, (c >> 8) & 255, (c >> 16) & 255)
            cols.append(col if any(col) else (255, 255, 255))
        if len(cols) == n:
            print(f"  channel colors from file (RGB): {cols}")
            return cols
        print(f"  WARNING: file lists {len(cols)} channel colors for {n} "
              "channels; using default palette (use --colors to override)")
    except Exception as e:
        print(f"  WARNING: could not read channel colors ({e!r}); "
              "using default palette (use --colors to override)")
    if n == 1:
        return [(255, 255, 255)]
    return [DEFAULT_COLORS[i % len(DEFAULT_COLORS)] for i in range(n)]


def stretch(a, lo_pct, hi_pct):
    """Contrast-stretch to 0..1 using percentiles."""
    a = a.astype(np.float32)
    lo, hi = np.percentile(a, (lo_pct, hi_pct))
    if hi <= lo:
        hi = lo + 1.0
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def make_rgb(arr, order, colors, lo_pct, hi_pct):
    """arr is T,C,Y,X (or T,C,Y,X,S). Returns uint8 array (T, Y, X, 3) with
    each channel tinted by its color and summed (like a Fiji composite)."""
    if "S" in order:  # camera RGB data: already color
        a = arr[:, 0, :, :, :3]
        if a.dtype != np.uint8:
            a = (stretch(a, lo_pct, hi_pct) * 255 + 0.5).astype(np.uint8)
        return a
    T, C, Y, X = arr.shape
    out = np.zeros((T, Y, X, 3), np.float32)
    for c in range(C):
        out += stretch(arr[:, c], lo_pct, hi_pct)[..., None] * (
            np.array(colors[c], np.float32) / 255.0)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def position_names(f, n_points):
    """Names of the multipoint positions, in order (list of str; '' if
    a position has no name)."""
    names = []
    try:
        for loop in f.experiment:
            if getattr(loop, "type", "") == "XYPosLoop":
                names = [(pt.name or "") for pt in loop.parameters.points]
                break
    except Exception as e:
        print(f"  WARNING: could not read position names ({e!r})")
    if names and len(names) != n_points:
        print(f"  WARNING: file lists {len(names)} position names for "
              f"{n_points} positions; names ignored")
        names = []
    return names or [""] * n_points


def safe_name(name, max_len=80):
    """Make a position name safe for use in a file name (Windows-safe)."""
    cleaned = "".join("_" if (c in '<>:"/\\|?*' or ord(c) < 32) else c
                      for c in name.strip())
    cleaned = "_".join(cleaned.split())  # whitespace -> underscores
    return cleaned.strip("._")[:max_len]


def process_file(path: Path, outdir: Path, overwrite: bool,
                 simple: bool = False, lo_pct: float = 0.5,
                 hi_pct: float = 99.8, override_colors=None):
    outdir.mkdir(parents=True, exist_ok=True)
    with nd2.ND2File(str(path)) as f:
        dims = list(f.sizes.keys())  # e.g. ['P','T','Z','C','Y','X']
        data = f.to_dask()           # lazy; axes match `dims`
        print(f"{path.name}: axes {dict(f.sizes)}, dtype {data.dtype}")

        try:
            vs = f.voxel_size()  # microns
            px_x, px_y = vs.x, vs.y
        except Exception:
            px_x = px_y = None

        n_points = f.sizes.get("P", 1)
        names = position_names(f, n_points)
        for p in range(n_points):
            suffix = "_rgb" if simple else ""
            label = safe_name(names[p])
            label = f"_{label}" if label else ""
            out = outdir / f"{path.stem}_P{p + 1:03d}{label}{suffix}.tif"
            if out.exists() and not overwrite:
                print(f"  skip {out.name} (exists; use --overwrite)")
                continue

            sub, sub_dims = data, dims[:]
            if "P" in sub_dims:
                pi = sub_dims.index("P")
                sub = sub[(slice(None),) * pi + (p,)]
                sub_dims.pop(pi)

            # Max intensity projection along Z
            if "Z" in sub_dims:
                zi = sub_dims.index("Z")
                sub = sub.max(axis=zi)
                sub_dims.pop(zi)

            arr = np.asarray(sub.compute())
            arr, order = reorder(arr, sub_dims)

            if simple:
                # 8-bit RGB, uncompressed, one page: opens in Windows,
                # PowerPoint, etc. One file per timepoint if T > 1.
                n_c = arr.shape[order.index("C")]
                colors = override_colors or channel_colors(f, n_c)
                if len(colors) < n_c:
                    raise ValueError(f"--colors gave {len(colors)} colors "
                                     f"but the file has {n_c} channels")
                rgb = make_rgb(arr, order, colors, lo_pct, hi_pct)
                res = {}
                if px_x and px_y:
                    res = {"resolution": (1.0 / px_x, 1.0 / px_y),
                           "resolutionunit": "MICROMETER"}
                for t in range(rgb.shape[0]):
                    tout = out if rgb.shape[0] == 1 else out.with_name(
                        f"{out.stem}_T{t + 1:03d}.tif")
                    tifffile.imwrite(str(tout), rgb[t], photometric="rgb",
                                     **res)
                    print(f"  wrote {tout.name}  shape={rgb[t].shape} (8-bit RGB)")
                continue

            kwargs = {"compression": "zlib"}
            if order == ["T", "C", "Y", "X"]:
                meta = {"axes": "TCYX"}
                kwargs["imagej"] = True
                if px_x and px_y:
                    kwargs["resolution"] = (1.0 / px_x, 1.0 / px_y)
                    meta["unit"] = "um"
                kwargs["metadata"] = meta
            elif px_x and px_y:
                kwargs["resolution"] = (1.0 / px_x, 1.0 / px_y)
                kwargs["resolutionunit"] = "MICROMETER"

            tifffile.imwrite(str(out), arr, **kwargs)
            print(f"  wrote {out.name}  shape={arr.shape} axes={''.join(order)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help=".nd2 files and/or folders")
    ap.add_argument("-o", "--outdir", default=None,
                    help="output folder (default: next to each input file)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--simple", action="store_true",
                    help="save plain 8-bit RGB color TIFFs (<name>_P001_rgb.tif) "
                         "readable by Windows/PowerPoint; channels are "
                         "contrast-stretched and tinted with their ND2 colors")
    ap.add_argument("--low", type=float, default=0.5,
                    help="--simple: low contrast percentile (default 0.5)")
    ap.add_argument("--high", type=float, default=99.8,
                    help="--simple: high contrast percentile (default 99.8)")
    ap.add_argument("--colors", default=None,
                    help="--simple: override channel colors, in channel "
                         "order, e.g. blue,red or '#0000ff,#ff0000'. Names: "
                         + ", ".join(NAMED_COLORS))
    args = ap.parse_args()

    override = None
    if args.colors:
        try:
            override = parse_colors(args.colors)
        except ValueError as e:
            sys.exit(str(e))

    files = []
    for item in args.inputs:
        p = Path(item)
        if p.is_dir():
            files += sorted(p.glob("*.nd2"))
        elif p.suffix.lower() == ".nd2" and p.exists():
            files.append(p)
        else:
            print(f"Ignoring {item}", file=sys.stderr)

    if not files:
        sys.exit("No .nd2 files found.")

    for fp in files:
        outdir = Path(args.outdir) if args.outdir else fp.parent
        try:
            process_file(fp, outdir, args.overwrite, args.simple,
                         args.low, args.high, override)
        except Exception as e:
            print(f"ERROR processing {fp.name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
