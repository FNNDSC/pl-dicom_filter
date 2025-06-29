#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter
from pydicom.pixel_data_handlers import convert_color_space
from chris_plugin import chris_plugin, PathMapper
import pydicom as dicom
import cv2
import json
from pflog import pflog
from pydicom.pixel_data_handlers import convert_color_space
import numpy as np
__version__ = '1.2.5'

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
parser.add_argument('-V', '--version', action='version',
                    version=f'%(prog)s {__version__}')
parser.add_argument('-t', '--outputType', default='dcm', type=str,
                    help='output file type(extension only)')
parser.add_argument('-e', '--exclude', default=False, action="store_true",
                    help='True means filter out, False means filter in.')
parser.add_argument(  '--pftelDB',
                    dest        = 'pftelDB',
                    default     = '',
                    type        = str,
                    help        = 'optional pftel server DB path')


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
@pflog.tel_logTime(
            event       = 'dicom_filter',
            log         = 'Filter dicom files'
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

    # Typically it's easier to think of programs as operating on individual files
    # rather than directories. The helper functions provided by a ``PathMapper``
    # object make it easy to discover input files and write to output files inside
    # the given paths.
    #
    # Refer to the documentation for more options, examples, and advanced uses e.g.
    # adding a progress bar and parallelism.
    mapper = PathMapper.file_mapper(inputdir, outputdir, glob=f"**/*.{options.fileFilter}",fail_if_empty=False)
    for input_file, output_file in mapper:
        # Read each input file from the input directory that matches the input filter specified
        dcm_img = read_input_dicom(input_file, options.dicomFilter, options.exclude)

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





def read_input_dicom(input_file_path, filters, exclude):
    """
    1) Read an input dicom file
    2) Check if the dicom headers match the specified filters
    3) Return the dicom data set
    """
    ds = None
    d_filter = json.loads(filters)
    try:
        print(f"Reading input file : {input_file_path.name}")
        ds = dicom.dcmread(str(input_file_path))
    except Exception as ex:
        print(f"unable to read dicom file: {ex} \n")
        return None

    for key, value in d_filter.items():
        try:
            print(f"expected: {value} found: {ds.data_element(key)} exclude: {exclude} \n")
            if value in str(ds.data_element(key)):
                continue
            else:
                if exclude:
                    return ds
                print(f"file: {input_file_path.name} doesn't match filter criteria")
                return None
        except Exception as ex:
            print(f"Exception : {ex}")
            return None

    if exclude:
        print(f"file: {input_file_path.name} matches filter criteria")
        return None
    return ds


def save_dicom(dicom_file, output_path):
    """
    Save a dicom file to an output path
    """
    print(f"Saving dicom file: {output_path.name}")
    dicom_file.save_as(str(output_path))


if __name__ == '__main__':
    main()
