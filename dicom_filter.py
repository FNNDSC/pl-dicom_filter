#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter
from pydicom.pixel_data_handlers import convert_color_space
from chris_plugin import chris_plugin, PathMapper
import pydicom as dicom
import cv2
import json
# from pflog import pflog
from pydicom.pixel_data_handlers import convert_color_space
import numpy as np
import re
from PIL import Image
import pytesseract

__version__ = '1.2.7'

DISPLAY_TITLE = r"""
       _           _ _                        __ _ _ _            
      | |         | (_)                      / _(_) | |           
 _ __ | |______ __| |_  ___ ___  _ __ ___   | |_ _| | |_ ___ _ __ 
| '_ \| |______/ _` | |/ __/ _ \| '_ ` _ \  |  _| | | __/ _ \ '__|
| |_) | |     | (_| | | (_| (_) | | | | | | | | | | | ||  __/ |   
| .__/|_|      \__,_|_|\___\___/|_| |_| |_| |_| |_|_|\__\___|_|   
| |                                     ______                    
|_|                                    |______|                   

                      
""" + "\t\t -- version " + __version__ + " --\n\n"

parser = ArgumentParser(description='A ChRIS plugin to filter dicoms using filters on dicom tags',
                        formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument('-d', '--dicomFilter', default="{}", type=str,
                    help='comma separated dicom tags with values')
parser.add_argument('-f', '--fileFilter', default='dcm', type=str,
                    help='input file filter glob')
parser.add_argument('-m', '--minImgCount', default='1', type=int,
                    help='A configurable threshold—any series with fewer images is dropped.')
parser.add_argument('-V', '--version', action='version',
                    version=f'%(prog)s {__version__}')
parser.add_argument('-o', '--outputType', default='dcm', type=str,
                    help='output file type(extension only)')
parser.add_argument('-t', '--textInspect', default=False, action="store_true",
                    help='True means detect text in images, else no.')
parser.add_argument(  '--pftelDB',
                    dest        = 'pftelDB',
                    default     = '',
                    type        = str,
                    help        = 'optional pftel server DB path')

class TagCondition:
    def __init__(self, tag, op, values):
        self.tag = tag
        self.op = op
        self.values = values  # list for '=' OR values; length 1 otherwise

    def __repr__(self):
        return f"<TagCondition {self.tag}{self.op}{self.values}>"

OPERATORS = ["!=", ">=", "<=", "=", ">", "<", "~"]

def parse_filter_string(filter_str):
    conditions = []
    parts = [p.strip() for p in filter_str.split(",") if p.strip()]

    for part in parts:
        # find operator
        op = None
        for candidate in OPERATORS:
            if candidate in part:
                op = candidate
                break
        if not op:
            raise ValueError(f"Invalid filter expression: {part}")

        tag, value = part.split(op, 1)
        tag = tag.strip().strip('"').strip("'")
        value = value.strip().strip('"').strip("'")

        # support OR-values for '=' operator: CT/MR/US
        if op == "=" and "/" in value:
            values = value.split("/")
        else:
            values = [value]

        conditions.append(TagCondition(tag, op, values))

    return conditions

def passes_filters(ds, conditions):
    for cond in conditions:
        try:
            elem = ds.data_element(cond.tag)
            actual_full = str(elem)            # FULL element string (your requirement)
        except Exception:
            print(f"[{cond.tag}] MISSING TAG → fails condition {cond}")
            return False

        # This extracts ONLY the value part for numeric comparisons:
        # Example elem: "(0008,0020) Study Date DA: '20121126'"
        # Extracts "20121126"
        try:
            actual_value_only = str(elem.value)
        except Exception:
            actual_value_only = actual_full    # fallback

        # Expected string for printing
        expected_str = "/".join(cond.values) if cond.op == "=" else cond.values[0]

        print(f"[{cond.tag}] expected: {cond.op}{expected_str} | actual: {actual_full}")

        # ---------------------------------------------------------------------
        # 1) Exact or OR matching against the FULL ELEMENT STRING
        # ---------------------------------------------------------------------
        if cond.op == "=":
            if not any(v in actual_full for v in cond.values):
                print("  -> FAIL (substring not found in element)")
                return False
            print("  -> OK")
            continue

        # ---------------------------------------------------------------------
        # 2) Negated match against the FULL ELEMENT STRING
        # ---------------------------------------------------------------------
        elif cond.op == "!=":
            if any(v in actual_full for v in cond.values):
                print("  -> FAIL (excluded substring found in element)")
                return False
            print("  -> OK")
            continue

        # ---------------------------------------------------------------------
        # 3) Numeric comparisons (value-only, not full element)
        # ---------------------------------------------------------------------
        elif cond.op in [">", "<", ">=", "<="]:
            try:
                v = float(actual_value_only)
                c = float(cond.values[0])
            except ValueError:
                print("  -> FAIL (cannot extract numeric value)")
                return False

            result = eval(f"{v} {cond.op} {c}")
            print(f"  -> {'OK' if result else 'FAIL'}")

            if not result:
                return False
            continue

        # ---------------------------------------------------------------------
        # 4) Regex (FULL element string)
        # ---------------------------------------------------------------------
        elif cond.op == "~":
            pattern = cond.values[0]
            result = bool(re.search(pattern, actual_full))
            print(f"  -> {'OK' if result else 'FAIL'}")

            if not result:
                return False
            continue

    return True

def extract_text_from_pixeldata(ds):
    """Return OCR-ed text from pixel data, or '' if unreadable."""
    try:
        if 'PixelData' not in ds:
            return ""

        arr = ds.pixel_array

        # Convert numpy array to PIL Image (auto-handles monochrome / RGB)
        if arr.ndim == 2:
            img = Image.fromarray(arr)
        elif arr.ndim == 3:
            img = Image.fromarray(arr)
        else:
            return ""

        text = pytesseract.image_to_string(img)
        return text.strip()

    except Exception as e:
        print(f"OCR error: {e}")
        return ""





# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin
@chris_plugin(
    parser=parser,
    title='A ChRIS plugin to filter dicom files using dicom tags',
    category='',  # ref. https://chrisstore.co/plugins
    min_memory_limit='2Gi',  # supported units: Mi, Gi
    min_cpu_limit='1000m',  # millicores, e.g. "1000m" = 1 CPU core
    min_gpu_limit=0  # set min_gpu_limit=1 to enable GPU
)
def main(options: Namespace, inputdir: Path, outputdir: Path):
    """
    *ChRIS* plugins usually have two positional arguments: an **input directory** containing
    input files and an **output directory** where to write output files. Command-line arguments
    are passed to this main method implicitly when ``main()`` is called below without parameters.

    :param options: non-positional arguments parsed by the parser given to @chris_plugin
    :param inputdir: directory containing (read-only) input files
    :param outputdir: directory where to write output files
    """

    print(DISPLAY_TITLE)

    mapper = PathMapper.file_mapper(inputdir, outputdir, glob=f"**/*.{options.fileFilter}",fail_if_empty=False)

    # Exit if minimum image count is not met
    if len(mapper)<options.minImgCount:
        print(f"Total no. of images found ({len(mapper)}) is less than {options.minImgCount}. Exiting analysis..")
        return
    print(f"Total no. of images found: {len(mapper)}")

    for input_file, output_file in mapper:
        # Read each input file from the input directory that matches the input filter specified
        dcm_img = read_input_dicom(input_file, options.dicomFilter, options.textInspect)

        # check if a valid image file is returned
        if dcm_img is None:
            continue

        # Save the file in o/p directory in the specified o/p type\
        if options.outputType == "dcm":
            save_dicom(dcm_img, output_file)
        else:
            save_as_image(dcm_img, output_file, options.outputType)
        print("\n\n")


def save_as_image(dcm_file, output_file_path, file_ext):
    """
    Save the pixel array of a dicom file as an image file
    """
    pixel_array_numpy = dcm_file.pixel_array
    output_file_path = str(output_file_path).replace('dcm', file_ext)
    print(f"Saving output file as {output_file_path}")
    print(f"Photometric Interpretation is {dcm_file.PhotometricInterpretation}")

    # Prevents color inversion happening while saving as images
    if 'YBR' in dcm_file.PhotometricInterpretation:
        print(f"Explicitly converting color space to RGB")
        pixel_array_numpy = convert_color_space(pixel_array_numpy, "YBR_FULL", "RGB")

    cv2.imwrite(output_file_path,cv2.cvtColor(pixel_array_numpy,cv2.COLOR_RGB2BGR))


def read_input_dicom(input_file_path, filter_expression, inspect_text):
    """
    1) Read an input DICOM file
    2) Check if the DICOM headers match the specified filters
    3) Return the DICOM dataset if it matches, else None
    """
    conditions = parse_filter_string(filter_expression)

    # Read DICOM
    try:
        print(f"Reading input file: {input_file_path.name}")
        ds = dicom.dcmread(str(input_file_path), stop_before_pixels=False)

        if 'PixelData' not in ds:
            print("No pixel data in this DICOM.")
            return None

    except Exception as ex:
        print(f"Unable to read dicom file: {ex}")
        return None

    # Apply filters with verbose output
    print(f"\nApplying filter: {filter_expression}")
    match = passes_filters(ds, conditions)
    print(f"Result: {'MATCH' if match else 'NO MATCH'}\n")

    if inspect_text:
        print(extract_text_from_pixeldata(ds))

    return ds if match else None




def save_dicom(dicom_file, output_path):
    """
    Save a dicom file to an output path
    """
    print(f"Saving dicom file: {output_path.name}")
    dicom_file.save_as(str(output_path))


if __name__ == '__main__':
    main()
