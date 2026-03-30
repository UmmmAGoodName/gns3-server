#!/usr/bin/env python
#
# Copyright (C) 2016 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os

from pathlib import Path
from fastapi import HTTPException, status
from ..config import Config

# Module-level cache: populated on first call to get_default_project_directory().
# Stores the resolved, normalised project directory path so that subsequent calls
# skip the expanduser/normpath/makedirs syscalls on every request.
_project_directory_cache: str = None


def get_default_project_directory():
    """
    Return the default location for the project directory
    depending of the operating system
    """

    global _project_directory_cache
    if _project_directory_cache is not None:
        return _project_directory_cache

    server_config = Config.instance().settings.Server
    path = os.path.expanduser(server_config.projects_path)
    path = os.path.normpath(path)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Could not create project directory: {e}")
    _project_directory_cache = path
    return path


def is_safe_path(file_path: str, basedir: str) -> bool:
    """
    Check that file path is safe.
    (the file is stored inside directory or one of its sub-directory)
    """

    base = Path(basedir).resolve()
    test_path = (base / file_path).resolve()
    # Path.is_relative_to() performs a proper component-wise check and
    # correctly rejects sibling paths like "/base_evil/..." that would fool
    # a plain string-prefix comparison.
    return test_path != base and test_path.is_relative_to(base)


def check_path_allowed(path: str):
    """
    If the server is non local raise an error if
    the path is outside project directories

    Raise a 403 in case of error
    """

    project_directory = get_default_project_directory()
    # Use Path.is_relative_to() for a component-wise check so that sibling
    # directories (e.g. "projects_evil") are not mistaken for the project dir.
    try:
        Path(path).resolve().relative_to(Path(project_directory).resolve())
        return
    except ValueError:
        pass

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"The path {path} is not allowed")


def get_mountpoint(path: str):
    """
    Find the mount point of a path.
    """

    path = os.path.abspath(path)
    while path != os.path.sep:
        if os.path.ismount(path):
            return path
        path = os.path.abspath(os.path.join(path, os.pardir))
    return path
