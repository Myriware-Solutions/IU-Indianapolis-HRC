#!/usr/bin/env python3
import os, argparse
from pathlib import Path
from nd2_csv_overlay import RequiredArguments, create_overlay

def main(path:Path, config:Path):
    files = [Path(file) for file in os.scandir(path) if file.is_file()]
    
    img_files = [file.resolve() for file in files if file.suffix == ".nd2"]
    
    params = RequiredArguments(Path(), Path(), Path())
    params.config = config
    
    for nd2_img_file in img_files:
        csv_file_complement = Path(str(nd2_img_file).replace("RwImage.nd2", "Measure.csv"))
        if not csv_file_complement.exists():
            print(f"Warning on {nd2_img_file}")
            ans = input("File does not have csv counterpart. Continue [y/n]?: ")
            if not ans == "y": raise
            print("Skipping lonely file.")
            continue
        params.nd2_file = nd2_img_file
        params.csv_file = csv_file_complement
        params.output = path / str(nd2_img_file).replace("RwImage.nd2", "Preview.png")
        create_overlay(params)
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    main(args.path, args.config)
    
# Author(s): Anthony Smith