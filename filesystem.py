# File handling

import os
import re
import shutil

from binascii import crc32
from os import path

from collections import namedtuple
from tempfile import _RandomNameSequence  # type: ignore[attr-defined]
from loom import Spool

from distutils.dir_util import copy_tree
from typing import Callable

import logging
logger = logging.getLogger(__name__)


TrashEntry = namedtuple(
    typename="TrashEntry",
    field_names=["path", "crc", "orig_path"],
    defaults=[None, None, None]
)


def CRC32file(filename: str) -> str:
    """Returns the CRC32 "hash" of the file at (str) path.

    Args:
        filename (str): Path to file

    Returns:
        str: Formated CRC32, as {:08X} formatted.

    """

    buf: bytes = open(filename, 'rb').read()
    buf = (crc32(buf) & 0xFFFFFFFF)  # type: ignore[assignment]
    return "{:08X}".format(buf)  # type: ignore[str-format]


class Trash(object):
    """Acts as a proxy for deleting files.
    Allows quick undos by delaying filesystem commits.
    
    Attributes:
        queue_size (TYPE): Maximum length of the trash queue before committing disk operations
        trash_queue (list): List of files to be deleted
        verbose (bool): Print verbose output
    """
    
    def __init__(self, queue_size: int = 20, verbose=False) -> None:
        super().__init__()

        self.randomname = _RandomNameSequence()

        self.verbose: bool = verbose
        self.queue_size: int = queue_size

        self.trash_queue: list[TrashEntry] = []
        try:
            import send2trash  # noqa: PLC0415
            self._osTrash: Callable[[str], None] = send2trash.send2trash
        except ImportError:
            logger.warning("send2trash unavailible, using unsafe delete")
            self._osTrash = os.unlink

        self._spool = Spool(4, "os trash")

    def __enter__(self):
        return self

    def __exit__(self, type_, value, traceback):
        self.finish()

    def __str__(self):
        return str(self.trash_queue)

    def enforceQueueSize(self):
        while len(self.trash_queue) > self.queue_size:
            self.commitDelete(self.trash_queue[0])

    def isfile(self, path):
        if os.path.normpath(path) in [t[0] for t in self.trash_queue]:
            return False
        else:
            return os.path.isfile(path)

    def commitDelete(self, trashitem):
        crc = trashitem.crc
        path = trashitem.path

        if os.path.isdir(path):
            crc = "DIRECTORY"

            self._spool.enqueue(self._osTrash, args=(path,))
            
            if self.verbose:
                logger.info("{} --> {} --> {}".format("[SNIPTRASH]", trashitem, "[OS TRASH]"))

        elif os.path.isfile(path):
            if not CRC32file(path) == crc:
                logger.warning("File changed. Not deleting file '%s'" % path)
                return

            self._spool.enqueue(self._osTrash, args=(path,))
            
            if self.verbose:
                logger.info("{} --> {} --> {}".format("[SNIPTRASH]", trashitem, "[OS TRASH]"))

        else:
            logger.warning(f"deleted file '{path}' disappeared from disk")
        
        if trashitem in self.trash_queue:
            self.trash_queue.remove(trashitem)
        else:
            logger.warning(f"deleted file '{path}' not in trash!")

    def delete(self, path, rename=False):
        path = os.path.normpath(path)
        if path in {item.path for item in self.trash_queue}:
            logger.warning(f"attempted to delete already trashed file '{path}'")
            return False
        elif os.path.isdir(path):
            return self.deleteDir(path)
        elif not os.path.isfile(path):
            logger.warning(f"attempted to delete non-existent file '{path}'")
            return False

        if rename:
            while True:
                # tempfile.mktemp()
                renamed_path = path + ".trashed" + next(self.randomname)
                if not os.path.isfile(renamed_path):
                    break
            moveFileToFile(path, renamed_path, clobber=False, quiet=not self.verbose)
            entry = TrashEntry(
                path=renamed_path,
                crc=CRC32file(renamed_path),
                orig_path=path
            )
        else:
            entry = TrashEntry(
                path=path,
                crc=CRC32file(path)
            )
        self.trash_queue.append(entry)
        if self.verbose:
            logger.info("{} --> {}".format(entry, "[SNIPTRASH]"))
        self.enforceQueueSize()
        return True

    def deleteDir(self, path):
        path = os.path.normpath(path)
        if path in {item.path for item in self.trash_queue}:
            logger.warning(f"attempted to delete already trashed directory '{path}'")
            return False

        entry = TrashEntry(
            path=path,
            crc="DIRECTORY"
        )
        self.trash_queue.append(entry)
        if self.verbose:
            logger.info("{} --> {}".format(entry, "[SNIPTRASH]"))
        self.enforceQueueSize()
        return True

    def undo(self):
        if self.trash_queue:
            entry = self.trash_queue.pop()
            if self.verbose:
                logger.info("{} <-- {}".format(entry, "[SNIPTRASH]"))
            if entry.orig_path:
                moveFileToFile(entry.path, entry.orig_path, clobber=False, quiet=not self.verbose)
                return entry.orig_path
            else:
                return entry.path
        else:
            return False

    def flush(self):
        """Commit all trash operations
        """
        for entry in self.trash_queue.copy():
            self.commitDelete(entry)

    def finish(self):
        self.flush()
        self._spool.finish()


def easySlug(string, repl="-", directory=False):
    if directory:
        return re.sub(r"^\.|\.+$", "", easySlug(string, repl=repl, directory=False))
    else:
        return re.sub(r"[\\\\/:*?\"<>|\t]|\ +$", repl, string)


def userProfile(subdir=""):
    user_profile = os.environ.get("userprofile") or os.path.expanduser("~")
    return os.path.join(user_profile, subdir)


def renameFileOnly(source, destination, clobber=False, quiet=False, preserve_extension=True):
    """Renames file `source` to file `destination`.

    Args:
        source (str): Source path
        destination (str): Destination FILENAME
        clobber (bool, optional): Error instead of overwriting existing files.
        quiet (bool, optional): Print progress to screen

    Returns:
        str: Destination path
    """

    old_dir, old_name = path.split(source)
    new_dir, new_name = path.split(destination)

    assert (new_dir in ("", old_dir)), "Destination should not be a new path!"

    if preserve_extension:
        old_name_base, old_ext = path.splitext(old_name)
        new_name_base, new_ext = path.splitext(new_name)

        if new_ext not in ("", old_ext):
            logger.warning("WARNING: New name should not have a new extension while preserve_extension is True!")

        new_name = new_name_base + new_ext + old_ext

    real_destination = path.join(old_dir, new_name)
    return opFileToFile(shutil.move, source, real_destination, clobber, quiet)


def opFileToDir(op, source, destination, clobber, quiet):
    if not clobber:
        (srcdir, srcfile) = path.split(source)
        new_file_name = path.join(destination, srcfile)
        nfiles = [new_file_name]
    else:
        nfiles = []
    _safetyChecks(yfiles=[source], yfolders=[destination], nfiles=nfiles)
    _pathsExistCheck(source_file=source, destination_dir=destination)
    return _doFileOp(op, source, destination, quiet)


def opFileToFile(op, source, destination, clobber, quiet):
    assert source != destination, "Paths are the same! " + source
    nfiles = [destination] if not clobber else []
    yfiles = [source]
    destination_dir = path.split(destination)[0]
    _safetyChecks(yfiles=yfiles, nfiles=nfiles)
    _pathsExistCheck(source_file=source, destination_dir=destination_dir)
    return _doFileOp(op, source, destination, quiet)


def opDirToParent(op, source, destination, clobber, quiet):
    _safetyChecks(yfolders=[source, destination])
    return _doFileOp(op, source, destination, quiet)


def opDirWithMerge(op, source, destination, clobber, quiet):
    nfolders = [destination] if not clobber else []
    _safetyChecks(yfolders=[source], nfolders=nfolders)
    return _doFileOp(op, source, destination, quiet)


def _pathsExistCheck(source_file, destination_dir):
    """Raises an error if source_file is bigger than destination_dir's free space
    
    Args:
        source_file (str): Path to source file
        destination_dir (str): Path to destination *directory*.
    
    Raises:
        OSError: If there is not enough free space
    """

    file_size = path.getsize(source_file)
    free_space = shutil.disk_usage(destination_dir).free
    if free_space <= file_size:
        raise OSError("Not enough space for operation!")


def _safetyChecks(yfiles=[], yfolders=[], nfiles=[], nfolders=[]):

    for file in yfiles:
        if not path.isfile(file):
            raise FileNotFoundError(file)
    for folder in yfolders:
        if not path.isdir(folder):
            raise FileNotFoundError(folder)
    for file in nfiles:
        if path.isfile(file):
            raise FileExistsError(file)
    for folder in nfolders:
        if path.isdir(folder):
            raise FileExistsError(folder)


def _doFileOp(op, source: str, destination: str, quiet):
    try:
        result = op(source, destination)
        if not quiet:
            logger.info("{} --> {}".format(source, destination))
        return result
    except Exception:
        if not quiet:
            logger.error("{} -x> {}".format(source, destination), exc_info=True)
        raise


def copyFileToDir(source: str, destination: str, clobber=False, quiet=False):
    """Copies file `source` to folder `destination`.

    Args:
        source (str): Source path
        destination (str): Destination path
        clobber (bool, optional): Error instead of overwriting existing files.
        print (bool, optional): Print progress to screen

    Returns:
        str: Destination path
    """
    return opFileToDir(shutil.copy2, source, destination, clobber, quiet)


def copyFileToFile(source: str, destination: str, clobber=False, quiet=False):
    """Copies file `source` to file `destination`.

    Args:
        source (str): Source path
        destination (str): Destination path
        clobber (bool, optional): Error instead of overwriting existing files.
        print (bool, optional): Print progress to screen

    Returns:
        str: Destination path
    """
    return opFileToFile(shutil.copy2, source, destination, clobber, quiet)


def copyDirToParent(source: str, destination: str, clobber=False, quiet=False):
    """Copies directory `source` to `destination`. `source` will become a subfolder of `destination`.

    Args:
        source (str): Source path
        destination (str): Destination path
        clobber (bool, optional): Error instead of overwriting existing files.
        print (bool, optional): Print progress to screen

    Returns:
        str: Destination path
    """
    return opDirToParent(shutil.copy2, source, destination, clobber, quiet)


def copyDirWithMerge(source: str, destination: str, clobber=False, quiet=False):
    """Copies directory `source` to `destination`. If `destination` is a directory, the two are merged.

    Args:
        source (str): Source path
        destination (str): Destination path
        clobber (bool, optional): Error instead of overwriting existing files.
        print (bool, optional): Print progress to screen

    Returns:
        list: Destination paths
    """
    return opDirWithMerge(copy_tree, source, destination, clobber, quiet)


def _copyTreeAndRemove(source: str, destination: str):
    """Summary

    Args:
        source (TYPE): Description
        destination (TYPE): Description
    """
    result = copy_tree(source, destination)
    os.unlink(source)
    return result


def moveFileToDir(source: str, destination: str, clobber=False, quiet=False):
    """Moves file `source` to folder `destination`.

    Args:
        source (str): Source path
        destination (str): Destination path
        clobber (bool, optional): Error instead of overwriting existing files.
        quiet (bool, optional): Print progress to screen

    Returns:
        str: Destination path
    """
    return opFileToDir(shutil.move, source, destination, clobber, quiet)


def moveFileToFile(source: str, destination: str, clobber=False, quiet=False):
    """Moves file `source` to file `destination`.

    Args:
        source (str): Source path
        destination (str): Destination path
        clobber (bool, optional): Error instead of overwriting existing files.
        quiet (bool, optional): Print progress to screen

    Returns:
        str: Destination path
    """
    return opFileToFile(shutil.move, source, destination, clobber, quiet)


def moveDirToParent(source: str, destination: str, clobber=False, quiet=False):
    """Moves directory `source` to `destination`. `source` will become a subfolder of `destination`.

    Args:
        source (str): Source path
        destination (str): Destination path
        clobber (bool, optional): Error instead of overwriting existing files.
        quiet (bool, optional): Print progress to screen

    Returns:
        str: Destination path
    """
    return opDirToParent(shutil.move, source, destination, clobber, quiet)


def moveDirWithMerge(source: str, destination: str, clobber=False, quiet=False):
    """Moves directory `source` to `destination`. If `destination` is a directory, the two are merged.

    Args:
        source (str): Source path
        destination (str): Destination path
        clobber (bool, optional): Error instead of overwriting existing files.
        quiet (bool, optional): Print progress to screen

    Returns:
        list: Destination paths
    """
    return opDirWithMerge(_copyTreeAndRemove, source, destination, clobber, quiet)

