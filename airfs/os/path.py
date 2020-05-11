# coding=utf-8
"""Standard library "os.path" equivalents"""

from os.path import *  # noqa
from airfs._core.functions_os_path import (  # noqa
    exists, getctime, getmtime, getsize, isabs, isdir, isfile, islink, ismount,
    relpath, samefile, splitdrive)

import os.path as _src_module
__all__ = _src_module.__all__
del _src_module