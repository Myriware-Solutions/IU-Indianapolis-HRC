#!/usr/bin/env python3
"""
nd2_maxip.py - Split Nikon .nd2 multipoint z-stacks into per-position
max-intensity projections (max-IP) and save them in the format you choose.

Install:
    pip install nd2 tifffile numpy dask

Usage (--mode is required):
    python nd2_maxip.py file.nd2 --mode simple
    python nd2_maxip.py folder_of_nd2s --mode multi-max -o output_dir
    python nd2_maxip.py a.nd2 b.nd2 --mode one-max --overwrite

Modes:
    simple      8-bit color RGB TIFF for presentations (one per position),
                channels tinted with their ND2 colors.
    one-max     One intensity TIFF per position: max-IP over Z and over all
                channels (original bit depth).
    multi-max   One intensity TIFF per position per channel: max-IP over Z
                (original bit depth).
    as-nd2      One file per .nd2 with every position and channel kept
                separate, only Z removed. ND2 files cannot be written by any
                available library, so this is saved as an OME-TIFF
                (<name>_maxip.ome.tif), which Fiji/ImageJ and Bio-Formats
                based tools open with the positions as separate series.

File names:
    <index>_<nd2 name>_P<position #>_<position name>[_C<channel #>_<channel name>].tif
    <index> counts every output file in the run (0001, 0002, ...), so names
    never collide and you can see progress. Characters Windows does not allow
    in file names are replaced with underscores.
"""
import argparse
import itertools
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


def channel_names(f, n):
    """Channel names from the ND2 metadata ('' where missing)."""
    names = []
    try:
        names = [(ch.channel.name or "") for ch in f.metadata.channels[:n]]
    except Exception as e:
        print(f"  WARNING: could not read channel names ({e!r})")
    return names + [""] * (n - len(names))


def build_name(idx, stem, p, pos_name, ch=None, ch_name="", t=None,
               suffix=""):
    """<idx>_<stem>_P001[_<pos name>][_C1[_<ch name>]][_T001][suffix].tif"""
    parts = [f"{idx:04d}", stem, f"P{p + 1:03d}"]
    if safe_name(pos_name):
        parts.append(safe_name(pos_name))
    if ch is not None:
        parts.append(f"C{ch + 1}")
        if safe_name(ch_name):
            parts.append(safe_name(ch_name))
    if t is not None:
        parts.append(f"T{t + 1:03d}")
    return "_".join(parts) + suffix + ".tif"


def write_intensity(path, arr, px_x, px_y, has_s=False):
    """arr is (T, Y, X), or (T, Y, X, S) when has_s. Original bit depth.
    One timepoint -> plain 2D image; several -> a time stack. Opens in
    Fiji/ImageJ with pixel size in um."""
    if arr.shape[0] == 1:
        arr = arr[0]
    res = {}
    if px_x and px_y:
        res = {"resolution": (1.0 / px_x, 1.0 / px_y)}
    if has_s:  # camera RGB data: plain RGB TIFF
        tifffile.imwrite(str(path), arr, photometric="rgb",
                         resolutionunit="MICROMETER" if res else None, **res)
    else:
        tifffile.imwrite(str(path), arr, imagej=True,
                         metadata={"unit": "um"} if res else {}, **res)


def process_file(path: Path, outdir: Path, overwrite: bool, mode: str,
                 counter, lo_pct: float = 0.5, hi_pct: float = 99.8,
                 override_colors=None):
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
        n_t = f.sizes.get("T", 1)
        n_c = f.sizes.get("C", 1)
        pos_names = position_names(f, n_points)
        ch_names = channel_names(f, n_c)

        writer = None
        if mode == "as-nd2":
            ome_out = outdir / f"{next(counter):04d}_{path.stem}_maxip.ome.tif"
            if ome_out.exists() and not overwrite:
                print(f"  skip {ome_out.name} (exists; use --overwrite)")
                return
            writer = tifffile.TiffWriter(str(ome_out), ome=True, bigtiff=True)

        try:
            for p in range(n_points):
                # ---- plan the output files for this position ----------
                jobs = []  # (out path, kind, index)
                if mode == "simple":
                    for t in range(n_t):
                        jobs.append((outdir / build_name(
                            next(counter), path.stem, p, pos_names[p],
                            t=t if n_t > 1 else None, suffix="_rgb"),
                            "simple", t))
                elif mode == "one-max":
                    jobs.append((outdir / build_name(
                        next(counter), path.stem, p, pos_names[p],
                        suffix="_maxall"), "one", None))
                elif mode == "multi-max":
                    for c in range(n_c):
                        jobs.append((outdir / build_name(
                            next(counter), path.stem, p, pos_names[p],
                            ch=c, ch_name=ch_names[c], suffix="_max"),
                            "multi", c))

                todo = []
                for job in jobs:
                    if job[0].exists() and not overwrite:
                        print(f"  skip {job[0].name} (exists; use --overwrite)")
                    else:
                        todo.append(job)
                if mode != "as-nd2" and not todo:
                    continue

                # ---- max-IP over Z for this position -------------------
                sub, sub_dims = data, dims[:]
                if "P" in sub_dims:
                    pi = sub_dims.index("P")
                    sub = sub[(slice(None),) * pi + (p,)]
                    sub_dims.pop(pi)
                if "Z" in sub_dims:
                    zi = sub_dims.index("Z")
                    sub = sub.max(axis=zi)
                    sub_dims.pop(zi)

                arr = np.asarray(sub.compute())
                arr, order = reorder(arr, sub_dims)  # T, C, Y, X [, S]
                if order not in (["T", "C", "Y", "X"],
                                 ["T", "C", "Y", "X", "S"]):
                    raise ValueError(f"unexpected axes {order} after max-IP")

                # ---- write -----------------------------------------------
                if mode == "as-nd2":
                    meta = {"axes": "".join(order),
                            "Name": (f"P{p + 1:03d}_{pos_names[p]}"
                                     if pos_names[p] else f"P{p + 1:03d}"),
                            "Channel": {"Name": [
                                f"C{c + 1}" + (f"_{n}" if n else "")
                                for c, n in enumerate(ch_names)]}}
                    if px_x and px_y:
                        meta.update(PhysicalSizeX=px_x, PhysicalSizeY=px_y,
                                    PhysicalSizeXUnit="µm",
                                    PhysicalSizeYUnit="µm")
                    writer.write(arr, metadata=meta, contiguous=False)
                    print(f"  added position {p + 1}/{n_points} "
                          f"({meta['Name']}) shape={arr.shape}")
                    continue

                for out, kind, k in todo:
                    if kind == "simple":
                        colors = override_colors or channel_colors(f, n_c)
                        if len(colors) < n_c:
                            raise ValueError(
                                f"--colors gave {len(colors)} colors but "
                                f"the file has {n_c} channels")
                        rgb = make_rgb(arr, order, colors, lo_pct, hi_pct)
                        res = {}
                        if px_x and px_y:
                            res = {"resolution": (1.0 / px_x, 1.0 / px_y),
                                   "resolutionunit": "MICROMETER"}
                        tifffile.imwrite(str(out), rgb[k], photometric="rgb",
                                         **res)
                        print(f"  wrote {out.name}  shape={rgb[k].shape} "
                              "(8-bit RGB)")
                    else:
                        img = (arr.max(axis=1) if kind == "one"
                               else arr[:, k])        # (T, Y, X[, S])
                        write_intensity(out, img, px_x, px_y, "S" in order)
                        print(f"  wrote {out.name}  shape={img.shape} "
                              f"dtype={img.dtype}")
        finally:
            if writer is not None:
                writer.close()
                print(f"  wrote {ome_out.name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help=".nd2 files and/or folders")
    ap.add_argument("--mode", required=True,
                    choices=["simple", "one-max", "multi-max", "as-nd2"],
                    help="REQUIRED. simple: color RGB for presentations; "
                         "one-max: one intensity TIFF per position (all "
                         "channels combined); multi-max: one intensity TIFF "
                         "per position per channel; as-nd2: one multi-"
                         "position, multi-channel file per .nd2 (OME-TIFF)")
    ap.add_argument("-o", "--outdir", default=None,
                    help="output folder (default: next to each input file)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--low", type=float, default=0.5,
                    help="simple mode: low contrast percentile (default 0.5)")
    ap.add_argument("--high", type=float, default=99.8,
                    help="simple mode: high contrast percentile (default 99.8)")
    ap.add_argument("--colors", default=None,
                    help="simple mode: override channel colors, in channel "
                         "order, e.g. blue,red or '#0000ff,#ff0000'. Names: "
                         + ", ".join(NAMED_COLORS))
    args = ap.parse_args()

    if args.mode != "simple" and (args.colors or args.low != 0.5
                                  or args.high != 99.8):
        print("Note: --colors/--low/--high only apply to --mode simple.",
              file=sys.stderr)

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

    counter = itertools.count(1)  # overall output-file index for the run
    for fp in files:
        outdir = Path(args.outdir) if args.outdir else fp.parent
        try:
            process_file(fp, outdir, args.overwrite, args.mode, counter,
                         args.low, args.high, override)
        except Exception as e:
            print(f"ERROR processing {fp.name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
