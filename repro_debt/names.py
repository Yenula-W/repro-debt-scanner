"""Static name tables: stdlib modules, import->distribution names, builtins."""
from __future__ import annotations

import builtins
import re
import sys

_STDLIB_FALLBACK = """
__future__ _thread abc aifc argparse array ast asynchat asyncio asyncore atexit audioop base64 bdb binascii
binhex bisect builtins bz2 cProfile calendar cgi cgitb chunk cmath cmd code codecs codeop collections colorsys
compileall concurrent configparser contextlib contextvars copy copyreg crypt csv ctypes curses dataclasses
datetime dbm decimal difflib dis distutils doctest email encodings ensurepip enum errno faulthandler fcntl
filecmp fileinput fnmatch fractions ftplib functools gc getopt getpass gettext glob graphlib grp gzip hashlib
heapq hmac html http imaplib imghdr imp importlib inspect io ipaddress itertools json keyword lib2to3 linecache
locale logging lzma mailbox mailcap marshal math mimetypes mmap modulefinder msilib msvcrt multiprocessing
netrc nis nntplib numbers operator optparse os ossaudiodev pathlib pdb pickle pickletools pipes pkgutil
platform plistlib poplib posix posixpath pprint profile pstats pty pwd py_compile pyclbr pydoc queue quopri
random re readline reprlib resource rlcompleter runpy sched secrets select selectors shelve shlex shutil signal
site smtpd smtplib sndhdr socket socketserver spwd sqlite3 sre_compile sre_constants sre_parse ssl stat
statistics string stringprep struct subprocess sunau symtable sys sysconfig syslog tabnanny tarfile telnetlib
tempfile termios textwrap threading time timeit tkinter token tokenize tomllib trace traceback tracemalloc tty
turtle turtledemo types typing unicodedata unittest urllib uu uuid venv warnings wave weakref webbrowser
winreg winsound wsgiref xdrlib xml xmlrpc zipapp zipfile zipimport zlib zoneinfo ntpath nturl2path
"""

STDLIB = set(getattr(sys, "stdlib_module_names", ())) | set(_STDLIB_FALLBACK.split())

# import name -> acceptable distribution names (normalized)
IMPORT_TO_DIST = {
    "sklearn": ["scikit-learn", "sklearn"],
    "skimage": ["scikit-image"],
    "cv2": ["opencv-python", "opencv-python-headless", "opencv-contrib-python", "opencv"],
    "PIL": ["pillow", "pil"],
    "yaml": ["pyyaml", "yaml"],
    "bs4": ["beautifulsoup4"],
    "Bio": ["biopython"],
    "mpl_toolkits": ["matplotlib", "basemap", "cartopy"],
    "pylab": ["matplotlib"],
    "IPython": ["ipython", "jupyter", "notebook", "jupyterlab", "ipykernel"],
    "ipywidgets": ["ipywidgets", "jupyter"],
    "torch": ["torch", "pytorch"],
    "torchvision": ["torchvision"],
    "tensorflow": ["tensorflow", "tensorflow-gpu", "tensorflow-cpu", "tensorflow-macos"],
    "dateutil": ["python-dateutil"],
    "dotenv": ["python-dotenv"],
    "Crypto": ["pycryptodome", "pycrypto"],
    "attr": ["attrs"],
    "google": ["protobuf", "google-cloud-storage", "google-api-python-client", "google"],
    "jwt": ["pyjwt"],
    "magic": ["python-magic"],
    "serial": ["pyserial"],
    "usb": ["pyusb"],
    "zmq": ["pyzmq"],
    "lxml": ["lxml"],
    "Levenshtein": ["python-levenshtein", "levenshtein"],
    "MySQLdb": ["mysqlclient"],
    "psycopg2": ["psycopg2", "psycopg2-binary"],
    "OpenSSL": ["pyopenssl"],
    "fitz": ["pymupdf"],
    "docx": ["python-docx"],
    "pptx": ["python-pptx"],
    "umap": ["umap-learn"],
    "community": ["python-louvain"],
    "igraph": ["python-igraph", "igraph"],
    "osgeo": ["gdal"],
    "netCDF4": ["netcdf4"],
    "tables": ["tables", "pytables"],
    "pkg_resources": ["setuptools"],
    "setuptools": ["setuptools"],
    "statsmodels": ["statsmodels"],
    "nibabel": ["nibabel"],
    "anndata": ["anndata"],
    "scanpy": ["scanpy"],
    "mne": ["mne"],
    "tifffile": ["tifffile"],
    "imageio": ["imageio"],
    "rpy2": ["rpy2"],
    "pyarrow": ["pyarrow"],
    "jax": ["jax", "jaxlib"],
    "absl": ["absl-py"],
    "tqdm": ["tqdm"],
    "wx": ["wxpython"],
    "gi": ["pygobject"],
    "win32api": ["pywin32"],
    "pygraphviz": ["pygraphviz"],
    "graphviz": ["graphviz"],
    "sentencepiece": ["sentencepiece"],
    "Image": ["pillow"],
}

# Packages that ship inside another very common one; importing them is fine if the parent is declared.
PROVIDED_BY = {
    "pkg_resources": ["setuptools", "pip"],
    "mpl_toolkits": ["matplotlib"],
    "pylab": ["matplotlib"],
    "IPython": ["jupyter", "notebook", "jupyterlab", "ipykernel", "ipywidgets", "ipython"],
    "matplotlib": ["seaborn", "matplotlib-base"],
    "numpy": ["pandas", "scipy", "scikit-learn", "matplotlib", "numpy-base"],
    "six": [],
}

R_BASE = {
    "base", "stats", "utils", "graphics", "grDevices", "methods", "datasets", "tools", "parallel",
    "grid", "splines", "stats4", "tcltk", "compiler",
}

BUILTINS = set(dir(builtins)) | {
    "get_ipython", "display", "In", "Out", "_", "__", "___", "_i", "_ii", "_iii", "exit", "quit",
    "__file__", "__name__", "__doc__", "__builtins__", "__spec__", "__loader__", "__package__",
}


def norm_dist(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def import_candidates(top: str) -> list:
    cands = [norm_dist(top)] + [norm_dist(c) for c in IMPORT_TO_DIST.get(top, [])]
    cands += [norm_dist(c) for c in PROVIDED_BY.get(top, [])]
    return cands
