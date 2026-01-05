# pl-dicom_filter

[![Version](https://img.shields.io/docker/v/fnndsc/pl-dicom_filter?sort=semver)](https://hub.docker.com/r/fnndsc/pl-dicom_filter)
[![MIT License](https://img.shields.io/github/license/fnndsc/pl-dicom_filter)](https://github.com/FNNDSC/pl-dicom_filter/blob/main/LICENSE)
[![ci](https://github.com/FNNDSC/pl-dicom_filter/actions/workflows/ci.yml/badge.svg)](https://github.com/FNNDSC/pl-dicom_filter/actions/workflows/ci.yml)

`pl-dicom_filter` is a [_ChRIS_](https://chrisproject.org/) _ds_ plugin which takes in DICOM files in its input directory and filters DICOMs based on specified criteria into its output directory.

---

## Abstract

A ChRIS plugin to filter DICOM files using filters on DICOM tags, image count thresholds, and text similarity, with optional PHI handling.

---

## Installation

`pl-dicom_filter` is a _[ChRIS](https://chrisproject.org/) plugin_, meaning it can run either within _ChRIS_ or from the command line using container technologies such as [Apptainer](https://apptainer.org/).

---

## Local Usage

To get started with local command-line usage, use [Apptainer](https://apptainer.org/)
(a.k.a. Singularity) to run `pl-dicom_filter` as a container:

```shell
apptainer exec docker://fnndsc/pl-dicom_filter dicom_filter [--args values...] input/ output/
```

To print its available options, run:

```shell
apptainer exec docker://fnndsc/pl-dicom_filter dicom_filter --help
```
| Argument                      | Default  | Description                                                      |
| ----------------------------- | -------- | ---------------------------------------------------------------- |
| `-d`, `--dicomFilter`         | `""`     | Comma-separated DICOM tags with values to filter files           |
| `-f`, `--fileFilter`          | `"dcm"`  | Input file filter glob pattern                                   |
| `-m`, `--minImgCount`         | `1`      | Minimum number of images in a series; smaller series are dropped |
| `-o`, `--outputType`          | `"dcm"`  | Output file type/extension                                       |
| `-t`, `--textFilter`          | `"txt"`  | Input text file filter (for additional filtering)                |
| `-i`, `--inspectTags`         | `None`   | Comma-separated DICOM tags to inspect; optional                  |
| `-p`, `--phiMode`             | `"skip"` | PHI handling mode: `detect`, `allow`, or `skip`                  |
| `-s`, `--similarityThreshold` | `0.95`   | Minimum similarity threshold between two text entries            |
| `-V`, `--version`             | —        | Show plugin version                                              |


## Examples

`dicom_filter` requires two positional arguments: a directory containing
input data, and a directory where to create output data.
First, create the input directory and move input data into it.

```shell
mkdir incoming/ outgoing/
mv some.dat other.dat incoming/
apptainer exec docker://fnndsc/pl-dicom_filter:latest dicom_filter [--args] incoming/ outgoing/
```

## Development

Instructions for developers.

### Building

Build a local container image:

```shell
docker build -t localhost/fnndsc/pl-dicom_filter .
```

### Running

Mount the source code `dicom_unpack.py` into a container to try out changes without rebuild.

```shell
docker run --rm -it --userns=host -u $(id -u):$(id -g) \
    -v $PWD/dicom_filter.py:/usr/local/lib/python3.11/site-packages/dicom_filter.py:ro \
    -v $PWD/in:/incoming:ro -v $PWD/out:/outgoing:rw -w /outgoing \
    localhost/fnndsc/pl-dicom_filter dicom_filter /incoming /outgoing
```

### Testing

Run unit tests using `pytest`.
It's recommended to rebuild the image to ensure that sources are up-to-date.
Use the option `--build-arg extras_require=dev` to install extra dependencies for testing.

```shell
docker build -t localhost/fnndsc/pl-dicom_filter:dev --build-arg extras_require=dev .
docker run --rm -it localhost/fnndsc/pl-dicom_filter:dev pytest
```

## Release

Steps for release can be automated by [Github Actions](.github/workflows/ci.yml).
This section is about how to do those steps manually.

### Increase Version Number

Increase the version number in `dicom_filter.py` and commit this file.

### Push Container Image

Build and push an image tagged by the version. For example, for version `1.2.3`:

```
docker build -t docker.io/fnndsc/pl-dicom_filter:1.2.3 .
docker push docker.io/fnndsc/pl-dicom_filter:1.2.3
```

### Get JSON Representation

Run [`chris_plugin_info`](https://github.com/FNNDSC/chris_plugin#usage)
to produce a JSON description of this plugin, which can be uploaded to _ChRIS_.

```shell
docker run --rm docker.io/fnndsc/pl-dicom_filter:1.2.3 chris_plugin_info -d docker.io/fnndsc/pl-dicom_filter:1.2.3 > chris_plugin_info.json
```

Instructions on how to upload the plugin to _ChRIS_ can be found here:
https://chrisproject.org/docs/tutorials/upload_plugin

