#!/usr/bin/env python

from pathlib import Path
from typing import Callable, Any, Iterable, Iterator
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from difflib import SequenceMatcher
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter
from pydicom.pixel_data_handlers import convert_color_space
from chris_plugin import chris_plugin, PathMapper
import pydicom as dicom
import cv2
import json
from pydicom.pixel_data_handlers import convert_color_space
import numpy as np
import re
import os
import sys
from PIL import Image

__version__ = '1.2.8'

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
parser.add_argument('-m', '--minImgCount', default=1, type=int,
                    help='A configurable threshold—any series with fewer images is dropped.')
parser.add_argument('-V', '--version', action='version',
                    version=f'%(prog)s {__version__}')
parser.add_argument('-o', '--outputType', default='dcm', type=str,
                    help='output file type(extension only)')
parser.add_argument('-t', '--textFilter', default='txt',
                    help='Input text file filter')
parser.add_argument('-i', '--inspectTags',nargs="?", default=None, const="", type=str,
                    help='Comma separated DICOM tags')
parser.add_argument('-p', '--phiMode', default="skip",
                    help='PHI handling modes: detect, allow, or skip')


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
    """
    Checks DICOM dataset `ds` against a list of `conditions`.
    """

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

def split_text(text, max_len=50):
    """
    Splits text into lines of at most `max_len` characters, preserving words.
    """
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        # Check if adding this word exceeds max_len
        if len(current_line) + len(word) + 1 <= max_len:
            if current_line:
                current_line += " " + word
            else:
                current_line = word
        else:
            lines.append(current_line)
            current_line = word

    # Add the last line
    if current_line:
        lines.append(current_line)

    return lines

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


def read_input_dicom(input_file_path, filter_expression, inspect_text, inspect_tags, phi_mode):
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

    # -------------------------------------------------------------------------
    # PHI detection (conditional)
    # -------------------------------------------------------------------------
    """
    PHI handling modes (phi_mode):
        - "detect" → detect PHI and fail if present
        - "skip"   → skip PHI detection
        - "allow"  → allow PHI even if detected
    """
    if inspect_text and phi_mode != "skip":
        text = inspect_text.read_text(encoding="utf-8").split()
        phi_found = detect_phi(text, ds, inspect_tags)
        match phi_mode:
            case "detect":
                if phi_found:
                    print("  -> PHI detected, skipping dataset")
                    return None
            case "allow":
                if phi_found:
                    print("  -> PHI detected, but allowed (passing dataset)")
                    return ds if match else None
                return None

    return ds if match else None

def similarity(a, b):
    """Returns a similarity ratio between 0 and 1."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def detect_phi(text, ds, tags, threshold=0.80):
    """
    Detects possible PHI in `text` by comparing it against the extracted
    DICOM text & dates, using exact, substring, and similarity matching.
    """
    all_text_and_dates = extract_text_and_dates(ds, tags)

    flagged = False

    for word in text:  # split input text into tokens
        for dicom_tag, dicom_val in all_text_and_dates:

            # Split the DICOM value into words (whitespace-separated)
            dicom_words = dicom_val.split()

            # --- Exact match ---
            if word.lower() in (w.lower() for w in dicom_words):
                print(f"\n[PHI - EXACT MATCH] Found: '{word}' | DICOM Tag: {dicom_tag} | Value: '{dicom_val}'")
                flagged = True
                continue

            # --- Similarity (fuzzy) match ---
            for w in dicom_words:
                score = similarity(word, w)  # similarity can be difflib or fuzzywuzzy
                if score >= threshold:
                    print(
                        f"\n[PHI - SIMILARITY {score:.2f}] Found: '{word}' ≈ '{w}' | DICOM Tag: {dicom_tag} | Value: '{dicom_val}'")
                    flagged = True
                    break  # stop checking other words in this DICOM field

    return flagged

def extract_text_and_dates(ds: Dataset, tags=None):
    """
    Extract full text, dates (MM/DD/YYYY), and PN names (First Last) from a DICOM dataset.

    Optional:
        tags (str): comma-separated list of DICOM tags to extract.
                    Supports keywords (e.g. "PatientName") or hex (e.g. "00100010").

    If tags is None → extract from all fields.

    Returns:
        List of tuples: [(tag_or_keyword, full_value), ...]
    """
    results = set()

    # ---------------------------------------------------------------------
    # Parse user-provided tags
    # ---------------------------------------------------------------------
    allowed_tags = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        allowed_tags = set()

        for t in tag_list:
            # Keyword (e.g., "PatientName")
            if t.isalpha():
                allowed_tags.add(t)

            # Hex tag (e.g., "00100010")
            else:
                try:
                    hex_tag = int(t, 16)
                    allowed_tags.add(hex_tag)
                except Exception:
                    pass

    # ---------------------------------------------------------------------
    # Helper functions
    # ---------------------------------------------------------------------
    def convert_dicom_date(d):
        try:
            return datetime.strptime(str(d), "%Y%m%d").strftime("%m/%d/%Y")
        except Exception:
            return None

    def dicom_name_to_first_last(pn_value):
        if not pn_value:
            return ""
        parts = str(pn_value).split("^")
        last = parts[0] if len(parts) > 0 else ""
        first = parts[1] if len(parts) > 1 else ""
        return f"{first} {last}".strip() if first and last else first or last

    # ---------------------------------------------------------------------
    # Processing logic with tag filtering
    # ---------------------------------------------------------------------
    def process_element(elem):
        """Checks tag filter before processing."""
        tag_num = elem.tag
        tag_name = elem.keyword

        # If tag filtering is enabled
        if allowed_tags is not None:
            if (tag_name not in allowed_tags) and (tag_num not in allowed_tags):
                return  # Skip this field

        process_value(elem.VR, elem.value, tag_name or str(tag_num))

    def process_value(vr, value, tag):
        if value is None or value == "":
            return

        # Sequence
        if vr == "SQ" and isinstance(value, Sequence):
            for item in value:
                traverse(item)
            return

        # Multi-value
        if isinstance(value, (list, dicom.multival.MultiValue)):
            # Join multiple values into one string
            combined = " ".join(str(v) for v in value)
            results.add((tag, combined))
            return

        # Person Name
        if vr == "PN":
            name = dicom_name_to_first_last(value)
            if name:
                results.add((tag, name))
            return

        # Date
        if vr == "DA":
            formatted = convert_dicom_date(value)
            if formatted:
                results.add((tag, formatted))
            return

        # Text VRs
        if vr in {"LO", "LT", "SH", "ST", "UT", "AE", "CS", "UC"}:
            results.add((tag, str(value)))
            return

        # Fallback string → treat as text
        if isinstance(value, str):
            results.add((tag, value))

    def traverse(dataset: Dataset):
        for elem in dataset:
            process_element(elem)

    traverse(ds)
    return list(results)



def tokenize_strings(strings):
    """
    Tokenizes a list or set of strings into a flat list of words.

    - Lowercases all text
    - Splits on whitespace
    """
    tokens = []

    for s in strings:
        if not s:
            continue

        cleaned = s.lower()

        # Split into words
        words = cleaned.split()

        # Add to token list
        tokens.extend(words)

    return tokens


def save_dicom(dicom_file, output_path):
    """
    Save a dicom file to an output path
    """
    print(f"Saving dicom file: {output_path.name}")
    dicom_file.save_as(str(output_path))


def zipper_mapper(mapper1, mapper2, fill_value=None):
    """
    Yields:
    (map1_input, map2_input, map1_output, map2_output)

    - Matches on basename of input file
    - mapper2 may be empty
    - Missing values filled with fillvalue
    """
    # Build index for mapper2 (safe even if empty)
    index2 = {
        inp.stem: (inp, out)
        for inp, out in mapper2
    }

    for in1, out1 in mapper1:
        base = in1.stem

        if base in index2:
            in2, out2 = index2[base]
        else:
            in2, out2 = fill_value, fill_value

        yield (in1, in2, out1)

def check_setup_and_map(inputdir, outputdir, options):
    """
    Check the input file space
    If textInspect option is specified, accurately zip both the mappers
    to yield a single mapper
    """
    dcm_mapper = PathMapper.file_mapper(inputdir, outputdir, glob=f"**/*.{options.fileFilter}", fail_if_empty=False)

    # Exit if minimum image count is not met
    if len(dcm_mapper) < options.minImgCount:
        print(
            f"Total no. of images found ({len(dcm_mapper)}) is less than specified ({options.minImgCount}). Exiting analysis..")
        sys.exit()
    print(f"Total no. of images found: {len(dcm_mapper)}")

    text_mapper = PathMapper.file_mapper(inputdir, outputdir, glob=f"**/*.{options.textFilter}", fail_if_empty=False)

    return zipper_mapper(dcm_mapper, text_mapper, fill_value=None)



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

    mapper = check_setup_and_map(inputdir, outputdir, options)

    for input_file, input_txt_file, output_file in mapper:
        # Read each input file from the input directory that matches the input filter specified
        dcm_img = read_input_dicom(input_file, options.dicomFilter, input_txt_file, options.inspectTags, options.phiMode)

        # check if a valid image file is returned
        if dcm_img is None:
            continue

        # Save the file in o/p directory in the specified o/p type\
        if options.outputType == "dcm":
            save_dicom(dcm_img, output_file)
        else:
            save_as_image(dcm_img, output_file, options.outputType)
        print("\n\n")


if __name__ == '__main__':
    main()
