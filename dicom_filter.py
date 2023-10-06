#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter

from chris_plugin import chris_plugin, PathMapper
import pydicom as dicom
import cv2
import json

__version__ = '0.0.5'

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


# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin
@chris_plugin(
    parser=parser,
    title='My ChRIS plugin',
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

    # Typically it's easier to think of programs as operating on individual files
    # rather than directories. The helper functions provided by a ``PathMapper``
    # object make it easy to discover input files and write to output files inside
    # the given paths.
    #
    # Refer to the documentation for more options, examples, and advanced uses e.g.
    # adding a progress bar and parallelism.
    mapper = PathMapper.file_mapper(inputdir, outputdir, glob=f"**/*.{options.fileFilter}")
    for input_file, output_file in mapper:
        # The code block below is a small and easy example of how to use a ``PathMapper``.
        # It is recommended that you put your functionality in a helper function, so that
        # it is more legible and can be unit tested.
        print(f"Reading input file from {str(input_file)}")
        image_file = convert_to_image(str(input_file), options.dicomFilter)
        if image_file is None:
            continue
        output_file = str(output_file).replace('dcm', 'png')
        print(f"Saving output file as {str(output_file)}")
        cv2.imwrite(output_file, image_file)


def convert_to_image(dcm_file, filters):
    """

    """
    ds = None
    d_filter = json.loads(filters)
    try:
        ds = dicom.dcmread(dcm_file)
    except Exception as ex:
        print(f"unable to read dicom file: {ex}")
        return None
    for key, value in d_filter.items():
        if value in str(ds.data_element(key)):
            continue
        else:
            print(f"file: {dcm_file} doesn't match filter criteria")
            print(f"expected: {value} found: {ds.data_element(key)}")
            return None
    pixel_array_numpy = ds.pixel_array
    return pixel_array_numpy


def pass_filter(tags, filter, dicom):
    """

    """
    pass


if __name__ == '__main__':
    main()
