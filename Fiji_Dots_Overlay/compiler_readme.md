# Compiler Script Information

The compiler script is a companion script to the `nd2_csv_overlay.py` program.
It processes a whole folder of `nd2`/`csv` files and compiles them all seperately.
This program requires a few more specificiations than the single script:

All `nd2` and `csv` files must follow a strict naming policy, in which the
roots of both the files are the same. Then, the `nd2` image must end with `RwImage.nd2`
and the `csv` must end with `Measure.csv`. This is how the compiler couples images together
to be processes.

The Measure `csv` must come from the measure option of the
Fiji > Plugins > Analyze > Cell Counter. Alternitively, the `csv`
must contain the following header and rows:

`Type,Slice,X,Y,Value,C-pos,Z-pos,T-pos,X(micron),Y(micron),Z(micron)`

A configuration for the channels/colors is also highly recomended.
Using indexes of each of the channels from the `nd2`, the `toml` should
specify the label and color used on the output images. An example `toml`
can be found in these resources.

## Running

To run the compiler on a directory, use the folowing command:

```bash
python compiler.py [folder_path] [config_path]
```

The compiled images will appear in the directory specified in `path`.