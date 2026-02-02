#Copyright 2015 Yale University - Grablab
#Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\
#The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import argparse
import json
import os
import sys
import tarfile
from urllib.request import Request, urlopen

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 30
# Some servers expect a User-Agent; optional.
DEFAULT_HEADERS = {"User-Agent": "YCB-Downloader/1.0"}


# Define an output folder
output_directory = os.path.join("asset", "ycb")

# Define a list of objects to download from
# http://ycb-benchmarks.s3-website-us-east-1.amazonaws.com/
objects_to_download = "all"
# objects_to_download = ["001_chips_can", 
#                        "002_master_chef_can",
#                        "003_cracker_box",
#                        "004_sugar_box"]

# You can edit this list to only download certain kinds of files.
# 'berkeley_rgbd' contains all of the depth maps and images from the Carmines.
# 'berkeley_rgb_highres' contains all of the high-res images from the Canon cameras.
# 'berkeley_processed' contains all of the segmented point clouds and textured meshes.
# 'google_16k' contains google meshes with 16k vertices.
# 'google_64k' contains google meshes with 64k vertices.
# 'google_512k' contains google meshes with 512k vertices.
# See the website for more details.
#files_to_download = ["berkeley_rgbd", "berkeley_rgb_highres", "berkeley_processed", "google_16k", "google_64k", "google_512k"]
files_to_download = ["berkeley_processed", "google_16k"]

# Extract all files from the downloaded .tgz, and remove .tgz files.
# If false, will just download all .tgz files to output_directory
extract = True

# Skip objects that don't have MuJoCo-compatible meshes (google_16k, tsdf, or berkeley_processed).
# When True, only objects with at least one of these will be downloaded.
skip_non_mujoco_objects = True

# Skip downloading if the .tgz or extracted folder already exists (resume-friendly).
skip_existing = True

base_url = "http://ycb-benchmarks.s3-website-us-east-1.amazonaws.com/data/"
objects_url = "https://ycb-benchmarks.s3.amazonaws.com/data/objects.json"


def fetch_objects(url):
    """ Fetches the object information before download """
    req = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        objects = json.loads(response.read())
    return objects["objects"]


def download_file(url, filename):
    """ Downloads files from a given URL """
    req = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(req, timeout=REQUEST_TIMEOUT) as u:
        file_size = int(u.getheader("Content-Length"))
        print("Downloading: {} ({:.2f} MB)".format(filename, file_size / 1_000_000))
        file_size_dl = 0
        block_sz = 65536
        with open(filename, "wb") as f:
            while True:
                buffer = u.read(block_sz)
                if not buffer:
                    break
                file_size_dl += len(buffer)
                f.write(buffer)
                pct = file_size_dl * 100.0 / file_size
                print("\r  {:>8.2f} MB  [{:5.2f}%]".format(file_size_dl / 1_000_000, pct), end="")
        print()
    

def tgz_url(object, type):
    """ Get the TGZ file URL for a particular object and dataset type """
    if type in ["berkeley_rgbd", "berkeley_rgb_highres"]:
        return base_url + "berkeley/{object}/{object}_{type}.tgz".format(object=object,type=type)
    elif type in ["berkeley_processed"]:
        return base_url + "berkeley/{object}/{object}_berkeley_meshes.tgz".format(object=object,type=type)
    else:
        return base_url + "google/{object}_{type}.tgz".format(object=object,type=type)


def extract_tgz(filename, out_dir):
    """ Extract a TGZ file (portable, no shell dependency). On empty/invalid file, remove it and skip. """
    try:
        if os.path.getsize(filename) == 0:
            print("  Warning: {} is empty, removing.".format(os.path.basename(filename)))
            os.remove(filename)
            return
        with tarfile.open(filename, "r:gz") as tf:
            # Python 3.12+: pass filter to avoid DeprecationWarning and 3.14 behavior change
            if sys.version_info >= (3, 12):
                tf.extractall(path=out_dir, filter="data")
            else:
                tf.extractall(path=out_dir)
        os.remove(filename)
    except tarfile.ReadError as e:
        print("  Warning: {} is invalid or empty ({}), removing.".format(os.path.basename(filename), e))
        if os.path.exists(filename):
            os.remove(filename)

def check_url(url):
    """ Check the validity of a URL (HEAD request). """
    try:
        request = Request(url, headers=DEFAULT_HEADERS)
        request.get_method = lambda: "HEAD"
        urlopen(request, timeout=REQUEST_TIMEOUT)
        return True
    except Exception:
        return False


# Mesh types that MuJoCo can use (object must have at least one of these).
# google_16k / tsdf = standalone tgz; berkeley_processed = tgz that contains tsdf/poisson meshes.
MUJOCO_MESH_TYPES = ["google_16k", "tsdf", "berkeley_processed"]


def object_has_mujoco_mesh(object_name):
    """ Check if the object has at least one MuJoCo-compatible mesh (google_16k, tsdf, or berkeley_processed). """
    for mesh_type in MUJOCO_MESH_TYPES:
        url = tgz_url(object_name, mesh_type)
        if check_url(url):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Download YCB dataset objects.")
    parser.add_argument(
        "-o", "--output",
        default=output_directory,
        help="Output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="Do not extract .tgz files after download",
    )
    parser.add_argument(
        "--no-skip-mujoco",
        action="store_true",
        help="Do not skip objects without MuJoCo meshes (download all)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-download even if .tgz already exists",
    )
    args = parser.parse_args()

    out_dir = args.output
    do_extract = not args.no_extract
    do_skip_mujoco = not args.no_skip_mujoco
    do_skip_existing = not args.no_skip_existing

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # Grab all the object information
    objects = fetch_objects(objects_url)

    # Filter objects to process
    to_process = []
    for obj in objects:
        if objects_to_download != "all" and obj not in objects_to_download:
            continue
        if do_skip_mujoco and not object_has_mujoco_mesh(obj):
            print("Skipping {} (no google_16k / tsdf / berkeley_processed mesh available for MuJoCo).".format(obj))
            continue
        to_process.append(obj)

    total_objects = len(to_process)
    print("Downloading {} objects to {} (extract={}, skip_existing={})".format(
        total_objects, out_dir, do_extract, do_skip_existing))

    for idx, obj in enumerate(to_process, 1):
        print("\n[{}/{}] {}".format(idx, total_objects, obj))
        for file_type in files_to_download:
            url = tgz_url(obj, file_type)
            if not check_url(url):
                continue
            filename = os.path.join(out_dir, "{}_{}.tgz".format(obj, file_type))
            if do_skip_existing and os.path.exists(filename):
                print("  Skipping {} (already exists).".format(os.path.basename(filename)))
                continue
            download_file(url, filename)
            if do_extract:
                extract_tgz(filename, out_dir)


if __name__ == "__main__":
    main()
