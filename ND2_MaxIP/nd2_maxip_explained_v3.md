# `nd2_maxip.py` explained

A guided tour of the script for someone learning Python. It covers what the
program does, how the code is organized, and what every function, method and
symbol means.

**How to use this document:** keep `nd2_maxip.py` open beside it. Read
Part 1 and 2 first (the ideas), then Part 3 (the symbols), then walk through
Part 5 (the code, function by function). Part 7 has small experiments to try.

---

## Contents

1. [The big picture](#1-the-big-picture)
2. [How the script is organized](#2-how-the-script-is-organized)
3. [Python symbols and syntax glossary](#3-python-symbols-and-syntax-glossary)
4. [The libraries and the methods used from them](#4-the-libraries-and-the-methods-used-from-them)
5. [Function-by-function walkthrough](#5-function-by-function-walkthrough)
6. [Following the data through `process_file`](#6-following-the-data-through-process_file)
7. [Experiments to try](#7-experiments-to-try)
8. [Reading error messages](#8-reading-error-messages)

---

## 1. The big picture

### The problem

A Nikon `.nd2` file from the AX confocal is a big multi-dimensional block of
numbers. Each number is the brightness of one pixel. The "dimensions" are:

| Letter | Meaning | Example |
|---|---|---|
| `P` | **P**osition (multipoint) | 12 stage positions |
| `T` | **T**ime point | 1 (or many, for a time series) |
| `Z` | **Z**-slice (focus depth) | 30 slices |
| `C` | **C**hannel (color/fluorophore) | 2 (e.g. DAPI and Cy5) |
| `Y` | Pixel rows (image height) | 2048 |
| `X` | Pixel columns (image width) | 2048 |

So one file might hold `12 × 1 × 30 × 2 × 2048 × 2048` numbers.

### What the program does

1. **Open** the `.nd2` file and read its dimensions and metadata
   (position names, channel names/colors, pixel size).
2. **Loop over each position** `P`.
3. **Max-IP** (maximum intensity projection): flatten the `Z` axis by keeping
   only the *brightest value at each pixel across all Z slices*. A 30-slice
   stack becomes one flat image.
4. **Save** the result, in one of five formats chosen by `--mode`.

### Why "maximum"? A tiny example

Imagine one pixel position viewed through 4 Z-slices, with brightness values
`[3, 90, 12, 5]`. The max projection keeps `90`. Do that for every pixel in
the image and you get a flat picture showing the brightest structure at every
spot, regardless of which slice it sat in.

### The five modes

| Mode | Output | What is combined |
|---|---|---|
| `simple` | 8-bit color picture, 1 per position | Z (max), then channels tinted and added |
| `one-max` | grayscale, 1 per position | Z (max) **and** channels (max) |
| `multi-max` | grayscale, 1 per position **per channel** | Z (max) only |
| `as-nd2` | one multi-position, multi-channel file per `.nd2` | Z (max) only |
| `as-nd2-color` | same as `as-nd2`, plus each channel's display color stored in the file | Z (max) only |

---

## 2. How the script is organized

A Python script is read top to bottom. The order in this file is:

```
docstring            <- the """ ... """ block: the help text at the top
imports              <- load the libraries we depend on
constants            <- OUT_ORDER, DEFAULT_COLORS, NAMED_COLORS (values that never change)
helper functions     <- small single-purpose tools
    reorder, parse_colors, channel_colors, stretch, to_unit, full_scale_max, make_rgb,
    position_names, safe_name, channel_names, build_name, write_intensity
process_file()       <- the main worker: handles ONE .nd2 file
main()               <- reads your command, finds files, calls process_file for each
if __name__ == "__main__": main()   <- the "start button"
```

**Important idea:** `def` only *defines* a function (writes the recipe).
Nothing runs until the function is *called*. So although `main` appears near
the bottom, the very last two lines are what actually start the program.

### The call chain (who calls whom)

```
python nd2_maxip.py file.nd2 --mode multi-max
        │
        ▼
     main()                       parse the command line, build the list of files
        │   (for each file)
        ▼
  process_file()                  open one file, loop over positions
        │
        ├── position_names()      read position names
        ├── channel_names()       read channel names
        ├── ome_color()           (as-nd2-color) pack a color for the OME metadata
        ├── build_name()          make an output file name
        │       └── safe_name()   clean text so Windows accepts it
        ├── reorder()             put axes in a known order
        ├── channel_colors()      (simple mode) read channel colors
        ├── make_rgb()            (simple mode) merge channels into one color image
        ├── full_scale_max()      (simple mode) the camera's brightest possible value
        │       └── to_unit()     (simple mode) scale brightness to 0..1
        │             └── stretch()   only if --low/--high were given (auto-contrast)
        └── write_intensity()     (one-max / multi-max) save a TIFF
```

---

## 3. Python symbols and syntax glossary

Everything in the script that is not a word you would guess. Examples use real
lines from the file.

### Structure and punctuation

| Symbol | Name | Meaning | Example from the script |
|---|---|---|---|
| `#` | comment | Python ignores the rest of the line. Notes for humans. | `# microns` |
| `""" ... """` | triple-quoted string | A string that can span many lines. As the *first thing* in a file or function it is a **docstring** (built-in documentation). | The help text at the top |
| `:` (end of line) | colon | Starts an indented block: after `def`, `if`, `for`, `else`, `try`, `with`, `while`. | `for p in range(n_points):` |
| indentation | 4 spaces | Python uses indentation to show what belongs inside a block. This is *grammar*, not decoration. | everything under `def` |
| `( )` | parentheses | (1) call a function: `print(x)`. (2) group math: `(a - lo) / (hi - lo)`. (3) make a tuple: `(255, 0, 0)`. (4) let a statement continue over several lines. | |
| `[ ]` | square brackets | (1) make a list: `[0, 1]`. (2) pick items out of something (indexing/slicing): `names[p]`. | `jobs = []` |
| `{ }` | curly braces | (1) make a dictionary: `{"red": (255, 0, 0)}`. (2) mark a hole in an f-string: `f"{idx:04d}"`. | `NAMED_COLORS = {...}` |
| `,` | comma | Separates items, arguments, or list entries. A trailing comma is allowed. | |
| `.` | dot | "Look inside": `np.zeros` means "the `zeros` tool inside `np`". Also used for methods: `text.split(",")`. | `f.sizes` |
| `\` | backslash | Escape character inside a string. `"\\"` is one backslash. A backslash at the very end of a line means "continued on the next line". | `'<>:"/\\|?*'` |
| `->` | arrow | (Not used in this script.) In other code it marks a function's return type. | |

### Assignment and comparison

| Symbol | Meaning | Example |
|---|---|---|
| `=` | **assign**: store a value under a name. Read it as "becomes", not "equals". | `n_c = f.sizes.get("C", 1)` |
| `==` | **is equal to?** (asks a question, gives True/False) | `if mode == "simple":` |
| `!=` | **is not equal to?** | `args.mode != "simple"` |
| `<=`, `>=`, `<`, `>` | less/greater than (or equal) | `if hi <= lo:` |
| `+=` | add to the existing value: `x += 1` means `x = x + 1` | `out += to_unit(...)` |
| `+` | add numbers, **or join** strings/lists | `suffix + ".tif"`, `[ax] + dims` |
| `*` | multiply numbers; also **repeat** a sequence: `[""] * 3` gives `["", "", ""]` | `[""] * n_points` |
| `/` | divide (always gives a decimal). **With Paths** it means "join the path": `outdir / "file.tif"` | `1.0 / px_x`, `outdir / build_name(...)` |
| `%` | remainder after division (modulo). Used to "wrap around" a list. | `i % len(DEFAULT_COLORS)` |
| `&` | **bitwise AND**: compares numbers bit by bit (see "Bit tricks" below) | `c & 255` |
| `>>` | **bit shift right**: slides the bits over | `(c >> 8) & 255` |
| `<<` | **bit shift left**: slides the bits the other way (multiplies by 2 each step) | `r << 24` |
| `\|` | **bitwise OR**: combines the bits of two numbers (used to pack values together) | `(r << 24) \| (g << 16)` |

### Logic words

| Word | Meaning | Example |
|---|---|---|
| `and` / `or` / `not` | combine True/False questions | `if px_x and px_y:` |
| `in` | "is it inside?" (membership), also the `for x in y` loop | `if "Z" in sub_dims:` |
| `is` / `None` | `None` is Python's "nothing / no value". | `default=None` |
| `True` / `False` | the two yes/no values | `required=True` |

**The `or` default trick.** `A or B` gives `A` if `A` counts as "something",
otherwise `B`. So:

```python
colors = override_colors or channel_colors(f, n_c)
```
means "use the colors the user typed with `--colors`; if there are none
(`None`), read them from the file instead." Similarly
`return names or [""] * n_points` means "return the names, but if the list is
empty return a list of blank names."

**Truthiness.** In an `if`, these all count as *False*: `None`, `0`, `0.0`,
`""` (empty string), `[]` (empty list). Almost everything else counts as True.
That is why `if safe_name(pos_name):` works: an empty name is False, so no
position name is added to the file name.

### Keywords (the words that control the flow)

| Keyword | What it does |
|---|---|
| `import x` | load library `x`. `import numpy as np` loads it under the short nickname `np`. |
| `from x import y` | load just `y` from `x` (`from pathlib import Path`). |
| `def name(args):` | define a function. |
| `return value` | hand a value back to whoever called the function, and exit it. |
| `if` / `elif` / `else` | choose between branches. `elif` = "else if". |
| `for item in things:` | repeat the indented block once for each item. |
| `range(n)` | the numbers `0, 1, 2, ..., n-1`. Note it **starts at 0** and **stops before n**. |
| `continue` | skip the rest of this loop pass and jump to the next item. |
| `break` | leave the loop completely. |
| `try: ... except Exception as e:` | "try this; if it crashes, run the `except` block instead of dying." `e` holds the error. |
| `finally:` | code that runs **no matter what**, even after an error (used to make sure the output file is closed). |
| `raise ValueError("...")` | deliberately trigger an error with a message. |
| `with something as name:` | open a resource, use it, and **automatically close it** at the end of the block, even if an error occurs. |
| `pass` | do nothing (placeholder). |

### Strings

| Syntax | Meaning | Example |
|---|---|---|
| `"text"` or `'text'` | a string (text). Both quote styles are identical. | |
| `f"...{x}..."` | **f-string**: `{x}` is replaced by the value of `x`. | `f"P{p + 1:03d}"` |
| `{x:04d}` | format spec after the colon. `04d` = whole number, at least 4 wide, padded with `0`. | `f"{7:04d}"` gives `0007` |
| `{x:03d}` | same, 3 wide | `f"{3:03d}"` gives `003` |
| `{e!r}` | show the "technical" `repr` form of `e` (includes the error type) | `ValueError('x')` |
| `"a" "b"` | two string literals side by side are **joined automatically** | used to split long messages over several lines |
| `"_".join(parts)` | glue a list of strings together with `_` between them | `["a","b"]` gives `a_b` |
| `text.split(",")` | cut a string into a list at each comma | `"blue,red"` gives `["blue","red"]` |
| `text.split()` | with no argument: split on any whitespace | `"a  b"` gives `["a","b"]` |
| `.strip()` | remove spaces from both ends. `.strip("._")` removes any `.` or `_` characters from both ends. | |
| `.lower()` | lowercase | |
| `.startswith("#")` | does it begin with `#`? | |

### Indexing and slicing (picking parts out of things)

Python counts from **0**. `names[0]` is the first item, `names[1]` the second.

| Syntax | Meaning | Example |
|---|---|---|
| `x[i]` | item number `i` | `pos_names[p]` |
| `x[:n]` | the **first n** items | `"abc"[:2]` gives `"ab"`; `cleaned[:max_len]` cuts a name to 80 characters |
| `x[-1]` | the last item | (not used here) |
| `x[a:b]` | from `a` up to but **not including** `b` | `tok[i:i + 2]` takes 2 characters |
| `arr[:, 0]` | **every** item along the first axis, item 0 along the second. A lone `:` means "all of it." | `arr[:, k]` picks channel `k` for all time points |
| `arr[0]` | drop the first axis by taking its first entry | `arr = arr[0]` turns `(1, Y, X)` into `(Y, X)` |
| `arr[..., None]` | `...` means "all the axes I did not mention". `None` **adds a new axis of length 1** at that spot. | `(5, 6)` becomes `(5, 6, 1)` |
| `arr[np.newaxis, ...]` | add a new length-1 axis at the front (`np.newaxis` is just another name for `None`) | |
| `(slice(None),) * pi + (p,)` | builds the index "`:, :, ..., p`" as a tuple, so that item `p` is picked along axis number `pi`. Written this way because `pi` (which axis `P` is on) is only known while the program runs. | in `process_file` |

### Functions, arguments and the `*` / `**` symbols

```python
def process_file(path: Path, outdir: Path, overwrite: bool, mode: str,
                 counter, lo_pct=None, hi_pct=None,
                 override_colors=None):
```

* `process_file` is the function's name; the parts in `( )` are its
  **parameters** (the inputs it needs).
* `path: Path` is a **type hint**: a note that `path` should be a `Path`.
  Python does not enforce it; it is documentation.
* `lo_pct=None` gives a **default value**. If the caller leaves it out,
  `None` ("no value") is used, and the code treats that as "auto-contrast is
  off". Parameters with defaults must come after those without.
* **Positional vs keyword arguments.** `build_name(3, "exp1", 1, "Control")`
  matches by position. `build_name(..., ch=0, suffix="_max")` matches by
  **name**, so the order of keyword arguments does not matter.
* `**res` (double star) **unpacks a dictionary into keyword arguments**. If
  `res = {"resolution": (2.0, 2.0)}` then `f(a, **res)` means
  `f(a, resolution=(2.0, 2.0))`. If `res` is empty, nothing is added. This is
  how the code *optionally* passes pixel-size information.
* `*` before a name in a call (not used here) would unpack a list the same way.

### Data containers

| Type | Written | Notes |
|---|---|---|
| **list** | `[1, 2, 3]` | ordered, changeable. `.append(x)` adds to the end. |
| **tuple** | `(255, 0, 0)` | ordered, **unchangeable**. Used for RGB colors. |
| **dict** (dictionary) | `{"red": (255, 0, 0)}` | look things up by key: `NAMED_COLORS["red"]` |
| **string** | `"text"` | text |
| **int / float** | `3`, `0.5` | whole number / decimal |
| **bool** | `True`, `False` | |
| **NumPy array** | `np.zeros((4, 5))` | grid of numbers (see Part 4) |

**List comprehension**: a compact loop that builds a list.

```python
names = [(pt.name or "") for pt in loop.parameters.points]
```
reads as: "for every `pt` in the list of points, take its name (or an empty
string if it has none), and collect all of those into a list." It is
equivalent to:
```python
names = []
for pt in loop.parameters.points:
    names.append(pt.name or "")
```
The `tuple(... for i in (1, 3, 5))` in `parse_colors` is the same idea,
turned into a tuple. Written *without* square brackets like this, a loop
expression is called a **generator expression**: it produces the items one at
a time and is handed straight to whatever function wraps it, e.g.
`r, g, b = (int(v) for v in rgb)` in `ome_color` converts each of the three
color values to a whole number and unpacks them into three names.

**Conditional expression** (a one-line `if/else`):
```python
t=t if n_t > 1 else None
```
means "use `t` when there is more than one time point, otherwise `None`."

**Tuple unpacking**: assign several names at once.
```python
px_x, px_y = vs.x, vs.y
T, C, Y, X = arr.shape
for out, kind, k in todo:       # each item of todo is a 3-item tuple
```

### Bit tricks (only in the old-format color branch of `channel_colors`)

Older ND2 versions store a color as **one number** that packs three bytes
together: blue, green, red. To pull them apart:

```python
col = (c & 255, (c >> 8) & 255, (c >> 16) & 255)
```
* `c & 255` keeps only the lowest 8 bits (the red value).
* `c >> 8` slides everything 8 bits right, dropping the red byte. Then `& 255`
  keeps what is now the lowest 8 bits (green).
* `c >> 16` does it twice for blue.

Example: the number `0x00FF8040` gives `(64, 128, 255)` (R, G, B). Newer
`nd2` versions give the color already separated (`meta.color.r/.g/.b`), so
that branch is only a fallback.

`ome_color` does the **reverse** (packing) with `<<` and `|`: shifting a
value left by 24 bits moves it into the top byte, by 16 into the second byte,
and so on. `|` then merges the pieces into one number. See the `ome_color`
walkthrough in Part 5.

### Built-in functions and list methods

These come with Python itself (no `import` needed).

| Call | What it does | Where it appears |
|---|---|---|
| `print(x)` | show `x` on screen | progress messages |
| `len(x)` | how many items in a list/string | `len(tok) == 7` |
| `range(n)` | the numbers `0` to `n-1` | `for c in range(C):` |
| `str(x)` | convert to text | `str(path)` |
| `int(x)` / `float(x)` | convert to a whole number / decimal. `int("ff", 16)` reads the text as base-16. | `parse_colors`, `channel_colors` |
| `list(x)` | turn something into a list | `list(f.sizes.keys())` |
| `tuple(x)` | turn something into a tuple | `parse_colors` |
| `sorted(x)` | a sorted copy | `sorted(p.glob("*.nd2"))` |
| `any(x)` | True if **at least one** item is true/nonzero | `any(col)` |
| `ord(c)` | the number code of a character (`ord("A")` is 65) | `safe_name` |
| `enumerate(x)` | gives `(0, first), (1, second), ...` so a loop gets the **number and the item** | `for c, n in enumerate(ch_names)` |
| `next(counter)` | the next value from a counter/iterator | file index |
| `getattr(obj, "name", default)` | read `obj.name`, or `default` if it does not exist | `position_names` |
| `hasattr(obj, "name")` | does `obj.name` exist? (True/False) | `channel_colors` |
| `x.append(item)` | add to the end of a list | `jobs.append(...)` |
| `x.pop(i)` | remove (and return) item number `i` from a list | `sub_dims.pop(pi)` |
| `x.index(item)` | the position of `item` in a list | `dims.index("Z")` |
| `d.get(key, default)` | dictionary lookup that does not crash when the key is missing | `f.sizes.get("C", 1)` |
| `d.keys()` | the keys of a dictionary | `f.sizes.keys()` |
| `dims[:]` | a **copy** of a list (slice of everything). Used so that changing the copy does not change the original. | `sub_dims = dims[:]` |
| `r"C:\data\a.nd2"` | a **raw string**: backslashes are kept literally (handy for Windows paths) | experiments in Part 7 |

### Special names

* `__name__` and `"__main__"`: when you run a file directly,
  Python sets `__name__` to `"__main__"`. The last two lines therefore mean
  "only run `main()` if this file was *run*, not if it was *imported* by
  another script." It lets you reuse the functions elsewhere without
  accidentally starting the program.
* `_` in names like `n_points` is just a separator Python allows (the
  convention is `snake_case`). A leading underscore (not used here) usually
  means "internal".
* `UPPER_CASE` names (`OUT_ORDER`, `NAMED_COLORS`) are a convention for
  **constants**: values set once and never changed.

---

## 4. The libraries and the methods used from them

### `pathlib.Path`: file paths as objects

`Path("/data/run1/exp1.nd2")` is a path object that knows how to answer
questions about itself.

| Expression | Result for `/data/run1/exp1.nd2` |
|---|---|
| `p.name` | `exp1.nd2` (file name with extension) |
| `p.stem` | `exp1` (file name **without** extension) |
| `p.suffix` | `.nd2` |
| `p.parent` | `/data/run1` (the folder it is in) |
| `p.parent / "0001_exp1.tif"` | `/data/run1/0001_exp1.tif` (the `/` joins paths) |
| `p.exists()` | `True` or `False` |
| `p.is_dir()` | is it a folder? |
| `p.glob("*.nd2")` | all files in the folder ending in `.nd2` (`*` = any text) |
| `p.mkdir(parents=True, exist_ok=True)` | create the folder (and parents) if needed; no error if it exists |

### `argparse`: reading what you typed after the program name

Defines the options the program accepts and handles `--help` and errors for you.

* `ArgumentParser(description=__doc__, ...)`: makes the parser. `__doc__` is
  the docstring at the top of the file, reused as the help text.
* `ap.add_argument("inputs", nargs="+")`: a **positional** argument. `nargs="+"`
  means "one or more".
* `ap.add_argument("--mode", required=True, choices=[...])`: an **option**
  (starts with `--`). `required=True` forces you to give it; `choices` limits
  the allowed values. Anything else produces an error message.
* `action="store_true"` (as in `--overwrite`): a **flag** with no value. It is
  `False` unless you type it, then `True`.
* `type=float` converts typed text to a decimal number; `default=0.5` is used
  when the option is not typed.
* `args = ap.parse_args()` reads the command line. Afterwards `args.mode`,
  `args.outdir`, `args.overwrite`, ... hold the values. (`-o` and `--outdir`
  are two names for the same option; the attribute is named after the long
  one.)

### `sys`

* `sys.exit("message")` prints the message to the error output and stops the
  program.
* `file=sys.stderr` in a `print` sends the text to the *error* channel
  instead of normal output.

### `itertools.count`

`counter = itertools.count(1)` makes a counter that yields `1, 2, 3, ...`
forever. `next(counter)` gives the next number each time it is called. This
is the "overall index" in the file names. Because the *same* counter object is
passed into every `process_file` call, the numbering continues across files.

### `numpy` (imported as `np`): grids of numbers

A NumPy **array** is a block of numbers with a **shape**. The shape
`(2, 8, 10)` means 2 layers of 8 rows by 10 columns. `arr.dtype` is the number
type (`uint16` = whole numbers 0 to 65535, typical for microscope cameras;
`uint8` = 0 to 255; `float32` = decimals).

| Call | What it does |
|---|---|
| `arr.shape` | the dimensions, e.g. `(3, 2, 8, 10)` |
| `arr.max(axis=k)` | collapse axis `k` by keeping the largest value. **`axis` counts from 0.** On shape `(2,3,4)`, `axis=0` gives `(3,4)` and `axis=1` gives `(2,4)`. This is the actual max projection. |
| `np.asarray(x)` | make sure `x` is a real in-memory array |
| `np.transpose(arr, perm)` | reorder the axes. `perm=[1,0,2]` swaps the first two. |
| `np.zeros(shape, dtype)` | an array of all zeros |
| `arr.astype(np.float32)` | convert to another number type |
| `np.clip(a, 0, 1)` | force values below 0 up to 0 and above 1 down to 1 |
| `np.percentile(a, (lo, hi))` | the values below which `lo`% and `hi`% of all numbers fall |
| `np.array([255,0,0], np.float32)` | make an array from a list |
| `np.newaxis` | add a length-1 axis (same as `None`) |

**Element-wise math.** `arr / 255.0`, `a - lo`, `a * b` work on *every number
at once* with no loop needed. If shapes differ, NumPy **broadcasts**: it
stretches the smaller one to fit. In `make_rgb`, a `(T, Y, X, 1)` array times a
`(3,)` color is stretched to `(T, Y, X, 3)`.

**Axis names vs axis numbers.** NumPy knows only axis *numbers*. The script
keeps a parallel list of letters (`dims`, `order`) so it can say "the axis
labelled `Z` is currently number 2". That is what
`dims.index("Z")` does: it returns the position of `"Z"` in the list.

### `dask`: lazy, piece-by-piece loading

`f.to_dask()` returns a **dask array**. It looks like a NumPy array, but
nothing has been loaded from disk yet; it is a *plan*. Slicing (`sub[...,p]`)
and `.max(axis=...)` just add steps to the plan. Only `.compute()` actually
reads the data and does the work. This lets you process a file bigger than
your RAM, because one position at a time is read, reduced and then discarded.

### `nd2` (the Nikon reader)

| Call | Meaning |
|---|---|
| `nd2.ND2File(path)` | open a file. Used with `with ... as f:` so it closes itself. |
| `f.sizes` | an ordered dictionary of dimension sizes, e.g. `{'P': 12, 'T': 1, 'Z': 30, 'C': 2, 'Y': 2048, 'X': 2048}`. Only dimensions that exist appear. |
| `f.sizes.get("C", 1)` | dictionary `.get(key, default)`: the value for `"C"`, **or 1 if there is no `"C"`** (a file with one channel may not list it). |
| `f.to_dask()` | the pixel data as a lazy array (axes in the same order as `f.sizes`) |
| `f.voxel_size()` | pixel size in microns; `.x`, `.y`, `.z` |
| `f.metadata.channels` | one entry per channel; `.channel.name` and `.channel.color` are its name and display color |
| `f.experiment` | the list of acquisition loops; the one of `type == "XYPosLoop"` holds the multipoint positions and their names |

### `tifffile`: writing TIFF images

* `tifffile.imwrite(path, array, ...)`: write an array to a TIFF file in one
  step. Options used:
  * `photometric="rgb"`: the last axis of length 3 is red/green/blue, so it
    is stored as an ordinary color picture.
  * `imagej=True`: store in the ImageJ-compatible layout, so Fiji reads
    time stacks and pixel size correctly.
  * `resolution=(a, b)`: pixels **per unit** along X and Y. The script gives
    `1.0 / px_x` = pixels per micron.
  * `resolutionunit="MICROMETER"` / `metadata={"unit": "um"}`: says what the
    unit is.
* `tifffile.TiffWriter(path, ome=True, bigtiff=True)`: opens a file that you
  can write to **several times**. `ome=True` stores OME-XML metadata (names,
  channels, pixel size). `bigtiff=True` allows files over 4 GB.
  `writer.write(arr, metadata=...)` adds one more "series" (one position).
  `writer.close()` finishes the file.

### Why "TCYX"?

NumPy needs a fixed, known axis order to index reliably. The script always
rearranges to **T, C, Y, X** (optionally followed by **S**, "samples", only
for color-camera data) using `reorder()`.

---

## 5. Function-by-function walkthrough

### Constants

```python
OUT_ORDER = ["T", "C", "Y", "X", "S"]
```
The axis order the script standardizes on. `reorder` uses it as a template.

```python
DEFAULT_COLORS = [(0, 0, 255), (0, 255, 0), (255, 0, 0), ...]
```
A fallback list of `(R, G, B)` colors, each value 0 to 255: blue, green, red,
magenta, cyan, yellow. Used only if the file's own colors cannot be read.

```python
OME_MODES = ("as-nd2", "as-nd2-color")
```
A **tuple** of the two mode names that write an OME-TIFF. Later the code asks
`mode in OME_MODES` instead of repeating both names everywhere. Defining it
once means a future OME mode only needs adding in one place.

```python
NAMED_COLORS = {"red": (255, 0, 0), ...}
```
A **dictionary** mapping a color word to its `(R, G, B)`. This is what lets you
type `--colors blue,red`.

---

### `reorder(arr, dims)`

**Purpose:** put the axes of an array into the standard order `T, C, Y, X[, S]`,
adding length-1 `T` or `C` axes if the file did not have them.

```python
for ax in ("T", "C"):
    if ax not in dims:
        arr = arr[np.newaxis, ...]   # add a new first axis of length 1
        dims = [ax] + dims           # and record its label at the front
```
A file with one channel might not have a `C` axis at all. This invents a
length-1 one so the rest of the code can always count on `C` existing.

```python
order = [d for d in OUT_ORDER if d in dims]
```
A list comprehension: "walk through the template `T,C,Y,X,S` and keep the
letters this array actually has."

```python
extra = [d for d in dims if d not in order]
order = extra + order
```
Any *unexpected* axes get put in front so they are not silently lost (the
caller then raises a clear error).

```python
perm = [dims.index(d) for d in order]
return np.transpose(arr, perm), order
```
`perm` is a list of "where is each wanted axis currently?" Then
`np.transpose` reorders. The function **returns two things** (a tuple):
the reordered array and the list of letters.

Verified examples:

| Input | Output shape | `order` |
|---|---|---|
| shape `(5, 6)`, dims `["Y","X"]` | `(1, 1, 5, 6)` | `['T','C','Y','X']` |
| shape `(2, 6, 7)`, dims `["C","Y","X"]` | `(1, 2, 6, 7)` | `['T','C','Y','X']` |
| shape `(3, 2, 6, 7)`, dims `["C","T","X","Y"]` | `(2, 3, 7, 6)` | `['T','C','Y','X']` |

---

### `parse_colors(text)`

**Purpose:** convert what you typed after `--colors` into a list of `(R, G, B)`.

```python
out = []
for tok in text.split(","):          # "blue,#ff8000" -> "blue", then "#ff8000"
    tok = tok.strip().lower()        # tidy up
    if tok in NAMED_COLORS:          # a known word?
        out.append(NAMED_COLORS[tok])
    elif len(tok) == 7 and tok.startswith("#"):   # looks like #rrggbb?
        out.append(tuple(int(tok[i:i + 2], 16) for i in (1, 3, 5)))
    else:
        raise ValueError(f"Unknown color '{tok}'")
return out
```

The hex line deserves a closer look. `"#ff8000"` is red `ff`, green `80`, blue
`00` written in **hexadecimal** (base 16). `tok[1:3]` is `"ff"`, `tok[3:5]` is
`"80"`, `tok[5:7]` is `"00"`. `int("ff", 16)` converts hex text to the number
255. Result: `(255, 128, 0)`.

`parse_colors("blue,#ff8000")` returns `[(0, 0, 255), (255, 128, 0)]`.

---

### `channel_colors(f, n)`

**Purpose:** get the display color of each of the `n` channels from the ND2
metadata, falling back to defaults.

* The `try / except` wraps everything because metadata layouts vary between
  files and library versions; failure must not crash the run.
* `hasattr(meta, "color")` asks "does this object have an attribute named
  `color`?" This detects the newer library layout vs the older packed number
  (the bit-tricks branch described in Part 3).
* `cols.append(col if any(col) else (255, 255, 255))`:
  `any(col)` is True if *any* of R, G, B is nonzero. A pure `(0, 0, 0)` color
  would be invisible, so it is replaced with white.
* `if len(cols) == n:` the colors are only trusted if there is exactly one
  per channel. Otherwise a warning is printed and we **fall through** to the
  defaults at the bottom.
* The last two lines:
  `[DEFAULT_COLORS[i % len(DEFAULT_COLORS)] for i in range(n)]`. The `%` wraps
  around, so channel 7 reuses the first color instead of running off the end
  of the list.

---

### `full_scale_max(f, dtype)`

**Purpose:** find the brightest value the detector can possibly record, so
brightness can be measured against a fixed yardstick.

Microscope cameras often record 12 bits (values 0 to 4095) but store them in
16-bit numbers (which could go to 65535). The ND2 file knows the real bit
depth: `f.attributes.bitsPerComponentSignificant`. The function returns
`2 ** bits - 1` (`**` means "to the power of"): 4095 for 12-bit, 65535 for
16-bit.

* `np.issubdtype(dtype, np.integer)` asks "are these whole numbers?" If the
  data are decimals (float), it returns `None` and `make_rgb` falls back to the
  brightest value present.
* The `try / except` covers files with no such attribute: it then uses the
  data type's own maximum (`np.iinfo(dtype).bits` gives 16 for uint16).
* `if not 0 < bits <= type_bits:` is a **chained comparison** (Python allows
  `0 < bits <= 16`): it rejects nonsense values and falls back to the type's
  maximum.

Verified: 12-bit gives 4095, 16-bit gives 65535, uint8 gives 255, float gives
`None`, and a bogus value (24 bits in a 16-bit container) falls back to 65535.

---

### `stretch(a, lo_pct, hi_pct)`

**Purpose:** *auto-contrast.* Rescale brightness to the range 0 to 1 using the
image's **own** brightest and darkest values. This is only used if you give
`--low` and/or `--high`.

```python
a = a.astype(np.float32)                         # decimals, so we can do math
lo, hi = np.percentile(a, (lo_pct, hi_pct))      # the "black" and "white" points
if hi <= lo:                                     # a flat image: avoid dividing by 0
    hi = lo + 1.0
return np.clip((a - lo) / (hi - lo), 0.0, 1.0)
```

The formula `(a - lo) / (hi - lo)` is a straight-line remap: `lo` becomes 0,
`hi` becomes 1, everything between is proportional. `np.clip` then forces
anything outside (the very dark and very bright tails) to 0 or 1.

Why percentiles instead of min and max? One hot pixel would otherwise set the
white point and make the whole image look dim. Example with the values
`[0, 10, 20, 30, 40, 1000]` and percentiles `(0, 100)`: the result is
`[0, 0.01, 0.02, 0.03, 0.04, 1.0]`. The one outlier (1000) dominates; using
percentiles such as 99.8 instead of 100 ignores the extreme tail.

**The catch: this is why it is off by default.** `stretch` adapts to whatever
is in each channel. If a channel contains almost no real signal (just
background noise), its "white point" is set by the noise, so the noise is
stretched all the way up to full brightness. That shows up as a colored haze
(for example green, then yellow where it overlaps red) over the whole image,
including over the real structures of the other channels. A **fixed scale**
(`to_unit` below) does not do this: noise that is 2% of the camera's range
stays at 2%.

---

### `to_unit(a, lo_pct, hi_pct, full_max)`

**Purpose:** the one place that decides *how* brightness becomes 0..1.

```python
if lo_pct is None and hi_pct is None:
    return np.clip(a.astype(np.float32) / full_max, 0.0, 1.0)
return stretch(a, DEFAULT_LOW_PCT if lo_pct is None else lo_pct,
                  DEFAULT_HIGH_PCT if hi_pct is None else hi_pct)
```

* **Default (both `None`):** divide by `full_max`. 0 is black, `full_max` is
  full brightness, for every channel and every image, so images are comparable
  and background noise stays dark. This is simple division, with `np.clip`
  guarding against rounding past 1.
* **If you gave `--low` and/or `--high`:** call `stretch`. Whichever one you
  left out is filled in with its default (`DEFAULT_LOW_PCT = 0.5` or
  `DEFAULT_HIGH_PCT = 99.8`) using the one-line `x if condition else y`.
* `is None` is the proper way to test for "no value". (We do not use `== 0`
  because `--low 0` is a legitimate request and must not be treated as
  "not given".)

The trade-off: a fixed scale shows data *as recorded*, so a dim image looks
dim. Use `--high` (for example `--high 99.9`) if you want it brightened.

---

### `make_rgb(arr, order, colors, lo_pct, hi_pct, full_max=None)`

**Purpose:** build the presentation picture for `simple` mode: merge channels
into one color image.

```python
T, C, Y, X = arr.shape
out = np.zeros((T, Y, X, 3), np.float32)       # blank color image, all black
for c in range(C):                             # one channel at a time
    out += to_unit(arr[:, c], lo_pct, hi_pct, full_max)[..., None] * (
        np.array(colors[c], np.float32) / 255.0)
return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
```

Read the middle line from the inside out:

1. `arr[:, c]`: channel `c` for all time points, shape `(T, Y, X)`.
2. `to_unit(...)`: brightness scaled to 0..1 (fixed scale by default; auto-contrast if `--low`/`--high` were given).
3. `[..., None]`: add a trailing length-1 axis, shape `(T, Y, X, 1)`.
4. `np.array(colors[c]) / 255.0`: the color as fractions, e.g. blue
   `(0, 0, 255)` becomes `(0.0, 0.0, 1.0)`, shape `(3,)`.
5. Multiply: broadcasting turns the product into `(T, Y, X, 3)`. Where the
   channel is bright, you get its color; where dark, black.
6. `out += ...`: **add** each channel's tinted picture on top. Blue plus red
   overlap becomes magenta. This is how fluorescence composites work.

Finally `np.clip(out, 0, 1)` limits overlaps to 1 (they could add up past 1),
`* 255` scales to 0..255, `+ 0.5` makes the next step **round** to the
nearest whole number instead of chopping, and `.astype(np.uint8)` converts to
8-bit integers (the format ordinary picture viewers expect).

The early branch `if "S" in order:` handles data that is *already* a color
camera image; it just takes the first three samples.

---

### `position_names(f, n_points)`

**Purpose:** return a list with the name of each multipoint position, in order.

```python
for loop in f.experiment:
    if getattr(loop, "type", "") == "XYPosLoop":
        names = [(pt.name or "") for pt in loop.parameters.points]
        break
```
`f.experiment` is a list describing how the experiment was acquired (the
multipoint loop, the time loop, the z loop...). We look for the multipoint
one, `XYPosLoop`. `getattr(obj, "type", "")` is a safe way to read
`obj.type`, returning `""` if it does not exist. `break` stops the search once
found.

The sanity check afterward: if the list length differs from the number of
positions in the image data, the names cannot be trusted, so they are dropped.
Finally `return names or [""] * n_points` returns blank names if nothing was
found, so `pos_names[p]` never fails.

---

### `safe_name(name, max_len=80)`

**Purpose:** make arbitrary text safe to put in a Windows file name.

```python
cleaned = "".join("_" if (c in '<>:"/\\|?*' or ord(c) < 32) else c
                  for c in name.strip())
```
This loops over every character `c` in the name. Characters Windows forbids
(`< > : " / \ | ? *`), or invisible control characters (`ord(c) < 32`; `ord`
gives a character's numeric code), become `_`; all others are kept.
`"".join(...)` glues the characters back into one string.

```python
cleaned = "_".join(cleaned.split())      # spaces -> underscores
return cleaned.strip("._")[:max_len]     # trim edges, cap the length
```

Verified: `safe_name("ctrl/2: x?")` gives `ctrl_2__x`;
`safe_name("  Well A1 ")` gives `Well_A1`; `safe_name("")` gives `""`.
(Windows also dislikes names that end in a dot or space, hence the
`strip("._")`.)

---

### `ome_color(rgb)`

**Purpose:** convert an `(R, G, B)` color into the single number the OME
metadata format uses to store a channel's color (`as-nd2-color` mode).

```python
r, g, b = (int(v) for v in rgb)
v = (r << 24) | (g << 16) | (b << 8) | 255
return v - (1 << 32) if v >= (1 << 31) else v
```

1. Unpack the three values (red, green, blue).
2. **Pack** them into one 32-bit number, one byte each:
   `RRRRRRRR GGGGGGGG BBBBBBBB AAAAAAAA`. The last byte, `255`, is "alpha"
   (opacity), meaning fully opaque. `<< 24` moves red into the top byte,
   `<< 16` green into the second, `<< 8` blue into the third, and `|` merges
   them.
3. OME stores this as a **signed** 32-bit integer, which can be negative. Any
   number at or above `1 << 31` (2,147,483,648, i.e. the top bit is set) is
   converted by subtracting `1 << 32` (4,294,967,296).
   `x if condition else y` is the one-line if/else described in Part 3.

Verified results:

| Color | `ome_color(...)` |
|---|---|
| blue `(0, 0, 255)` | `65535` |
| red `(255, 0, 0)` | `-16776961` |
| green `(0, 255, 0)` | `16711935` |

A viewer such as Fiji (through Bio-Formats) reverses this to recover the
colors.

---

### `channel_names(f, n)`

Same pattern as `position_names`, for channel names. Note the last line:
`return names + [""] * (n - len(names))` pads the list with blanks if fewer
than `n` names were found, so `ch_names[c]` is always safe.

---

### `build_name(idx, stem, p, pos_name, ch=None, ch_name="", t=None, suffix="")`

**Purpose:** assemble an output file name from pieces.

```python
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
```
It starts with the always-present parts and appends optional ones only when
they exist. **`p + 1`** because Python counts positions from 0 but file names
read better from 1. `ch=None` as a default means "not supplied", so
`ch is not None` tests whether a channel was given.

Verified:

```
build_name(3, "exp1", 1, "Control", ch=0, ch_name="DAPI", suffix="_max")
  -> 0003_exp1_P002_Control_C1_DAPI_max.tif
build_name(2, "exp1", 1, "", suffix="_maxall")
  -> 0002_exp1_P002_maxall.tif
```

---

### `write_intensity(path, arr, px_x, px_y, has_s=False)`

**Purpose:** save a grayscale (or camera-color) array as a TIFF at its original
bit depth.

* `if arr.shape[0] == 1: arr = arr[0]`: with a single time point, drop that
  length-1 axis so you get a plain 2D picture, not a one-frame "stack."
* `res = {}` then, only if pixel size is known,
  `res = {"resolution": (1.0 / px_x, 1.0 / px_y)}`. A dictionary built up
  conditionally, then unpacked with `**res` into the `imwrite` call. If it is
  empty, no resolution arguments are passed.
* `imagej=True` makes Fiji interpret multiple frames as a time series.
* `str(path)` converts the `Path` object to plain text for the library.

---

### `process_file(...)`: the main worker

Takes one `.nd2` file and writes all outputs for it. See Part 6 for a detailed
trace. In outline:

1. `outdir.mkdir(...)`: make sure the output folder exists.
2. `with nd2.ND2File(str(path)) as f:`: open the file (auto-closes).
3. Read dimensions, the lazy data array, pixel size, names.
4. `as-nd2` / `as-nd2-color` only (`ome_mode`): open one output writer for
   the whole file. In `as-nd2-color` the channel colors are looked up first
   (from the file, or from `--colors`) and stored alongside the channel names.
5. `for p in range(n_points):`
   * **Plan** which files this position needs (`jobs`) and drop the ones that
     exist already (unless `--overwrite`).
   * **Reduce:** slice out position `p`, max over `Z`, `.compute()`.
   * **Reorder** to `T, C, Y, X`.
   * **Write** according to the mode.
6. `finally:` close the OME writer.

### `main()`: the command-line entry point

1. Build the argument parser and read your command (`parse_args`).
2. Warn if you gave simple-only options with another mode.
3. Convert `--colors` text into colors with `parse_colors` (exit cleanly on a
   typo using `sys.exit`).
4. Build the **list of files**: a folder expands to its `*.nd2` files (sorted),
   an `.nd2` path is added directly, anything else is reported and ignored.
5. Create the shared `counter`.
6. Loop over files, calling `process_file` inside `try / except` so one bad
   file does not stop the rest. The error is printed and the loop continues.

---

## 6. Following the data through `process_file`

Take an example file with **3 positions, 1 time, 4 Z, 2 channels, 8 rows, 10
columns**, run with `--mode multi-max`.

| Step | Code | Array shape | Axis letters |
|---|---|---|---|
| Open | `data = f.to_dask()` | `(3, 1, 4, 2, 8, 10)` (lazy) | `P T Z C Y X` |
| Pick position `p` | `sub[(slice(None),) * pi + (p,)]` | `(1, 4, 2, 8, 10)` | `T Z C Y X` |
| Max over Z | `sub.max(axis=zi)` | `(1, 2, 8, 10)` | `T C Y X` |
| Load into memory | `.compute()` | same, now real numbers | |
| `reorder` | `np.transpose(...)` | `(1, 2, 8, 10)` | `T C Y X` |
| Pick channel `k` | `arr[:, k]` | `(1, 8, 10)` | `T Y X` |
| Save | `write_intensity` drops the length-1 `T` | `(8, 10)` | `Y X` |

Key ideas:

* **`pi = sub_dims.index("P")`**: the position of the letter `"P"` in the list.
  Because the code does not assume `P` is first, it also works if the file's
  axes are in a different order.
* **`sub_dims.pop(pi)`**: remove that letter from the label list, since the
  axis it described is now gone. The labels always track the array.
* For **`one-max`** the saving step uses `arr.max(axis=1)` instead of
  `arr[:, k]`: axis 1 is `C`, so it collapses the channels too.
* For **`as-nd2`** and **`as-nd2-color`** the whole `(T, C, Y, X)` array is
  written as one series per position instead of being split. The only
  difference is that `as-nd2-color` adds `chan["Color"] = [ome_color(c) ...]`
  to the metadata. The pixel numbers are identical in both modes.

### The "jobs" list

```python
jobs = []   # (out path, kind, index)
...
jobs.append((outdir / build_name(...), "multi", c))
```
Each job is a **tuple** of three things: where to write, what kind of image,
and which channel or time index. Planning first lets the script check whether
the files already exist **before** doing the expensive projection. Later,
`for out, kind, k in todo:` unpacks each tuple into three named variables.

### Why `next(counter)` is called while planning

The index is taken when a job is *planned*, whether or not the file ends up
being skipped. That keeps numbering stable: re-running the same data always
gives the same names, so `--overwrite` replaces the right files and skipped
ones are recognized.

### Why a `try` / `finally` around the loop

If anything crashes mid-way in an OME mode (`as-nd2` / `as-nd2-color`), `finally` still runs
`writer.close()`, so the half-written file is closed properly rather than
left locked or corrupt.

---

## 7. Experiments to try

Make a copy of the script first (`copy nd2_maxip.py nd2_maxip_test.py`) so you
can always get back to the original. Run a change, read the output or error,
and undo it if it breaks. This is the fastest way to learn.

1. **See what a file contains without changing anything.** Run Python
   interactively:
   ```python
   import nd2
   f = nd2.ND2File(r"C:\data\a.nd2")
   print(f.sizes)
   print(f.voxel_size())
   print(f.metadata.channels)
   f.close()
   ```
   Seeing the real objects makes the rest of the code much less abstract.

2. **Compare contrast settings.** Run `--mode simple` on the same file three
   times with different options: none, `--high 99.9`, and `--low 1 --high 99`.
   (Add `-o` with a different folder each time, or `--overwrite`.) Then, in
   `DEFAULT_HIGH_PCT`, change `99.8` to `99.0` and run with only `--low 1`.

3. **Change how files are named.** In `build_name`, change `f"P{p + 1:03d}"` to
   `f"Pos{p + 1:02d}"`. Run and look at the names.

4. **Add a new color name.** Add `"pink": (255, 105, 180),` inside
   `NAMED_COLORS`, then try `--colors blue,pink`.

5. **Use only the first channel in one-max.** Replace `arr.max(axis=1)` with
   `arr[:, 0]` (and think about why that works).

6. **Add print statements.** Put `print(arr.shape, arr.dtype)` right after the
   `.compute()` line. Printing values is the most common debugging tool.

7. **Make a new mode (harder).** For example `mean`, an average projection
   instead of a max. You would: add `"mean"` to `choices=[...]` in `main`,
   plan a job for it, and use `.mean(axis=zi)` instead of `.max(axis=zi)` in
   the projection step.

---

## 8. Reading error messages

Python errors are read **from the bottom up**. The last line says *what*
went wrong; the lines above show *where*.

```
Traceback (most recent call last):
  File "nd2_maxip.py", line 57, in reorder
    return np.transpose(arr, perm), order
ValueError: axes don't match array
```

* Last line: the error type (`ValueError`) and message.
* Lines above: the file, line number and function where it happened.

| Error | Usually means |
|---|---|
| `SyntaxError` | A typo in the code: missing `:` or quote, or a bracket that is not closed. Python also shows a `^` near the spot. |
| `IndentationError` | The leading spaces are inconsistent. Use 4 spaces and never mix tabs with spaces. |
| `NameError: name 'x' is not defined` | You used a name before creating it, or misspelled it. |
| `TypeError` | Wrong kind of thing (e.g. adding text to a number, or a function given the wrong number of arguments). |
| `ValueError` | Right kind of thing, unusable value. This script raises its own `ValueError`s on purpose (bad `--colors`, unexpected axes). |
| `KeyError` | A dictionary does not have that key. |
| `IndexError` | You asked for item 5 of a 3-item list. |
| `AttributeError` | The object has no such attribute or method (a typo, or a different library version). |
| `ModuleNotFoundError` | A library is not installed. Run the `pip install` line. |
| `FileNotFoundError` | The path is wrong. |

**Habit that helps most:** when something breaks, read the *last line*, then the
line number it points to, and print the values involved just before that
line (`print(arr.shape)`) to see what is actually there.

---

## Quick reference: the whole program in one paragraph

`main()` reads your command line, builds a list of `.nd2` files, and passes
each to `process_file()`. That function opens the file lazily (dask), reads
names and pixel size, and for each position slices out its data, collapses `Z`
with `.max(axis=...)`, loads the small result into memory, standardizes the
axes to `T, C, Y, X`, and then writes it according to `--mode`: tinted and
merged into an 8-bit color picture (`simple`), max-ed over channels
(`one-max`), split per channel (`multi-max`), or kept whole as one series of
an OME-TIFF (`as-nd2`, or `as-nd2-color` which also stores each channel's color). File names are assembled by `build_name()` from a run
counter, the file name, the position, and the channel, cleaned by
`safe_name()` so Windows accepts them.
