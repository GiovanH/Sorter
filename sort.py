import os
import glob
import logging
import argparse
import random
import functools
import itertools
import re
import hashlib
import imagehash
from dataclasses import dataclass

from PIL import Image

import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter.simpledialog import askstring

import loom

import pymaybe

import filesystem
import sbf
import contentcanvas
from contentcanvas import ContentCanvas

from typing import Callable, Any, Optional, Union
import operator

# IMAGEEXTS = ["png", "jpg", "bmp", "jpeg", "tif", "jfif", "tga", "webp", "gif", "gifv"]
# VIDEOEXTS = ["webm", "mp4", "mov", "flv"]
# _IMAGEEXTS = ["*." + e for e in IMAGEEXTS]
# _VIDEOEXTS = ["*." + e for e in VIDEOEXTS]
MATCHEXTS = contentcanvas.SUPPORTED_EXTS
_MATCHEXTS = ["*." + e for e in MATCHEXTS]

MAX_TRASH_HISTORY = 32

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FolderOption:
    path: str
    label: str
    index: int


@dataclass
class UserBoolSetting:
    var: tk.BooleanVar
    label: str


@dataclass
class MatchResults:
    all: list[str]
    resolved: Optional[str]
    unique: bool

# FolderOption = collections.namedtuple("FolderOption", ["path", "label", "index"])
# UserBoolSetting = collections.namedtuple("UserBoolSetting", ["var", "label"])
# MatchResults = collections.namedtuple("MatchResults", ["all", "resolved", "unique"])


def imageSize(filepath) -> int:
    """
    Returns:
        int: Number of pixels in image
    """
    try:
        w, h = Image.open(filepath).size
        return w * h
    except FileNotFoundError:
        logger.warning("WARNING! File not found: " + filepath)
        return 0
    except OSError:
        logger.warning("WARNING! OS error with file: " + filepath)
        return 0


def md5(path) -> str:
    """Gives the md5 hash of a file on disk.
    Args:
        path (str): Path to a file

    Returns:
        str: MD5 hex digest
    """
    with open(path, 'rb') as afile:
        h = hashlib.md5()  # noqa: S324
        h.update(afile.read())
        return h.hexdigest()


@functools.lru_cache()
def fingerprintImage(image_path) -> str:
    """
    Returns:
        str: imagehash perceptual hash
    """
    try:
        image = Image.open(image_path)
        proc_hash = str(imagehash.dhash(image, hash_size=10))
    except Exception:
        logger.error("Can't fingerprint %s", image_path, exc_info=True)
        proc_hash = md5(image_path)
    return proc_hash


@functools.lru_cache()
def getMatches(query, collection, split_regex=r'[\\ /_-]', fuzzy=False) -> MatchResults:
    """
    >>> getMatches("dav ja", collection)
    MatchResults(all=[], resolved=None, unique=False)
    >>> getMatches("ri j", collection, fuzzy=True)
    MatchResults(all=['vris john'], resolved='vris john', unique=True)
    >>> getMatches("jo", collection)
    MatchResults(all=['john', 'john rose'], resolved='john', unique=False)

    >>> getMatches("john", collection).resolved
    'john'
    >>> getMatches("john", collection).all
    ['john', 'john rose']

    >>> getMatches("-john", collection).resolved
    'vris john'
    >>> getMatches("-rose", collection).resolved
    'john rose'

    >>> getMatches("jo ro", collection).resolved
    'john rose'
    """
    matches = []

    @functools.lru_cache()
    def segs(q) -> list[str]:
        return re.split(split_regex, q)

    query_segs: list[str] = segs(query)
    offsetize = bool(re.match(split_regex, query))

    # Construct list of (item, segs) tuples sorted by the length of segments
    grouped_item_segs: list[tuple[Any, list[str]]] = [(item, segs(item)) for item in collection]

    def lenSegmentsKey(is_):
        _item, item_segs = is_
        return len(item_segs)

    grouped_item_segs.sort(key=lenSegmentsKey)

    def addSegmentMatches(match_fn: Callable[[str, str], bool]):
        """Adds matches based on match_fn(theirs, ours): segmentMatches[True, False]"""
        for item, item_segs in grouped_item_segs:
            if item in matches:
                continue
            for offset in range(1 + len(item_segs) - len(query_segs)) if offsetize else [0]:
                # zipped = [*zip(item_segs, ['']*offset + query_segs)]
                zipped = [*itertools.zip_longest(
                    item_segs,
                    ([''] * offset) + query_segs,
                    fillvalue=''
                )]
                passes_test = all(match_fn(theirs, ours) for (theirs, ours) in zipped)
                # print(item, list(zipped), offset, offsetize, passes_test)
                if passes_test:
                    matches.append(item)
                    # break

    addSegmentMatches(lambda theirs, ours: theirs.startswith(ours))

    if len(matches) == 0 and fuzzy:
        addSegmentMatches(lambda theirs, ours: (ours in theirs))

    best = None
    if len(matches) > 0:
        best = matches[0]

    return MatchResults(resolved=best, all=matches, unique=(len(matches) == 1))


class FileSorter(tk.Tk):  # noqa: PLR0904

    """Summary

    Attributes:
        canvas (TYPE): Large image canvas tkwidget
        context_folders (list<FolderOptions>): Folders that are target options, shown in sidebar
        contextglobs (list<str>): Globs that select context folders

        filepaths (list<str>): List of filepaths being processed
        frame_sidebar (TYPE): Sidebarframe tk widget
        image_ext_globs (TYPE): File globs to filter what files we process
        image_index (int): Current index

        imageglobs (TYPE): Full glob w/ path to select files
        newFolderRoot (TYPE): Folder that contains any new folders

        rootpath (TYPE): The current root path of the program
        settings ({key: (tk.BooleanVar, Str)}): User-configurable runtime settings

        sorter (callable): The current sorting function used to order the file list
        sortkeys (TYPE): List of sorting options, passed to sidebarframe

        spool (TYPE): Description
        str_curfile (tk.Stringvar): Stringvar for the pretty formatted current file
        trash (TYPE): Description
        undo (list): Stack of functions to process via ctrl+z
    """

    def __init__(self, rootpath, image_ext_globs, *args, **kwargs) -> None:
        """File sorter main window
        Passthrough to tk.Tk

        Args:
            rootpath (str): Starting root path
            image_ext_globs (str): Starting fileglobs to match
        """
        super(FileSorter, self).__init__(*args, **kwargs)

        try:
            self.image_index: int = 0
            self.undo: list[Callable] = []
            self.filepaths: list[str] = []
            self.image_ext_globs: list[str] = image_ext_globs

            self.prev_query: Optional[str] = None

            self.contextglobs: list[str] = []
            self.context_folders: list[FolderOption]
            self.working_root_path: str
            self.rootpath: str

            self.spool = loom.Spool(1, "Sort misc")
            self.trash = filesystem.Trash(verbose=True, queue_size=MAX_TRASH_HISTORY)

            def userBoolSettingFactory(label, **kwargs):
                return UserBoolSetting(var=tk.BooleanVar(**kwargs), label=label)

            self.settings = {
                "fuzzy": userBoolSettingFactory("Fuzzy search"),
                "recursive": userBoolSettingFactory("Include subdirs as candidates (recursive)"),
                "makedirs": userBoolSettingFactory("Make new folders from main entry"),
                "parent_dirs": userBoolSettingFactory("Use parent directories"),
                "confident": userBoolSettingFactory("Displace rename conflicts"),
                "aggressive": userBoolSettingFactory("Automatically process on unambigious input"),
                "auto_reload": userBoolSettingFactory("Reload on change", value=True)
            }
            self.settings["parent_dirs"].var.trace("w", lambda *a: self.reloadDirContext())  # noqa: ARG005
            self.settings["recursive"].var.trace("w", lambda *a: self.reloadDirContext())  # noqa: ARG005

            self.sortkeys: dict[str, Callable] = {
                "{}, {}".format(name, order): (
                    lambda items, keyfunc=keyfunc, orderb=orderb: sorted(items, key=keyfunc, reverse=orderb)
                )
                for (name, keyfunc) in [
                    ("Alphabetical", str.lower),
                    ("Integers", lambda f: next(map(int, re.findall(r'\d+', os.path.splitext(os.path.split(f)[1])[0])))),
                    ("File size", os.path.getsize),
                    ("Last modified", os.path.getmtime),
                    ("File type", lambda f: os.path.splitext(f)[1]),
                    ("Image Dimensions", imageSize),
                    ("Image Height", lambda f: pymaybe.maybe(Image.open(f)).size[1].or_else(0)),  # type: ignore
                    ("Image Width", lambda f: pymaybe.maybe(Image.open(f)).size[0].or_else(0)),  # type: ignore
                    ("Procedural hash", fingerprintImage),
                    ("Random", lambda f: random.random())  # noqa: ARG005
                ]
                for (order, orderb) in [
                    ("asc", False), ("desc", True)
                ]
            }

            self.sorter: Callable = sorted

            self.initwindow()
            self.openDir(rootpath)

            self.mainloop()

        except KeyboardInterrupt:
            logger.warning("Window loop aborted")
            self.destroy()

    # Windowing and GUI

    def destroy(self) -> None:
        """Summary
        """
        self.spool.finish()
        self.trash.finish()
        super().destroy()

    def initwindow(self) -> None:
        """Initialize widgets for the window
        """

        self.geometry("860x600")

        # # Header stuff # #
        # current filename label
        self.str_curfile = tk.StringVar(value="No Images Found")
        lab_curfile = tk.Label(textvariable=self.str_curfile, height=2)
        lab_curfile.grid(row=0, column=1)

        self.str_keepdir = tk.StringVar(value="keep")

        # Canvas stuff
        self.canvas = ContentCanvas(self, takefocus=True)
        self.canvas.grid(column=1, row=1, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # self.canvas.bind("<Button-1>", lambda event: self.canvas.focus_set())

        self.bind("<Delete>", self.askDelete)
        self.bind("<Right>", self.nextImage)
        self.bind("<Left>", self.prevImage)

        # self.bind("<Configure>", self.onResize)

        self.bind("<Control-w>", self.canvas.quicksave)
        self.bind("<Control-d>", self.fastDelete)
        self.bind("<Control-z>", self.doUndo)

        # self.bind("<Up>", self.keepImage)
        # self.bind("<Down>", self.fastDelete)
        # self.bind("<End>", self.doUndo)

        self.canvas.bind("<f>", self.nextImage)
        self.canvas.bind("<s>", self.prevImage)

        self.canvas.bind("<d>", self.fastDelete)
        self.canvas.bind("<e>", self.keepImage)
        self.canvas.bind("<w>", self.canvas.quicksave)

        self.canvas.bind("<a>", self.doUndo)

        self.frame_sidebar = sbf.SidebarFrame(
            self,
            submit_callback=self.submit
        )
        self.frame_sidebar.config(bd=3, relief=tk.RIDGE)
        self.frame_sidebar.grid(row=0, rowspan=2, column=0, sticky="NSEW")

        self.columnconfigure(0, minsize=160)

    def updateLabelFileName(self) -> None:
        """Generate a user-friendly filename for the header and set str_curfile.
        """
        if self.currentImagePath is None:
            self.str_curfile.set("No image.")
            return

        prettyname = self.canvas.getInfoLabel()

        self.str_curfile.set(prettyname)

    def promptLooseCleanup(self, rootpath: str, destpath: str) -> None:
        """Check if there are files in rootpath, and offer to move them to destpath.
        """
        if not (os.path.isdir(rootpath) and os.path.isdir(destpath)):
            raise ValueError("Cleanup paths are not directories")

        imageglobs = [os.path.join(glob.escape(rootpath), ext) for ext in self.image_ext_globs]
        all_globs: list[str] = functools.reduce(operator.iadd, [glob.glob(a) for a in imageglobs], [])
        loose_files = list(filter(self.trash.isfile, all_globs))

        num_loose_files = len(loose_files)
        if num_loose_files == 0:
            return

        can_do_cleanup = messagebox.askyesno(
            title="Clean up directory?",
            message="""Move {num_loose_files} files into single directory?\nFiles in: {rootpath}\nNew folder: {destpath}\n\nFiles to move: {flist}""".format(flist=", ".join(loose_files[:30]), **locals())
        )

        if can_do_cleanup:
            for oldfile in loose_files:
                try:
                    filesystem.moveFileToDir(oldfile, destpath)
                except FileExistsError:
                    pass

    def updateContextListFrame(self) -> None:
        """Generate and refresh the sidebar listbox"""
        # Reset and clear
        self.frame_sidebar.listbox_context.configure(state=tk.NORMAL)
        self.frame_sidebar.listbox_context.delete(0, self.frame_sidebar.listbox_context.size())
        # Populate with new values from folder_names
        for opt in self.context_folders:
            self.frame_sidebar.listbox_context.insert(
                tk.END, "{}".format(opt.label[0:32]))

    # Context and context manipulation

    def changeMatchGlobs(self, newmatchglobs: Union[None, str] = None) -> None:
        """Summary

        Args:
            newmatchglobs (None, optional): Description
        """
        logger.debug(self.image_ext_globs)
        if not newmatchglobs:

            newmatchglobs = askstring("Filter", "Enter new globs seperated by ', '", initialvalue=", ".join(self.image_ext_globs))
            if not isinstance(newmatchglobs, str):
                return

        logger.debug(newmatchglobs)

        self.image_ext_globs = newmatchglobs.split(", ")
        self.reloadDirContext()
        self.imageUpdate()

    @property
    def currentImagePath(self) -> Optional[str]:
        if len(self.filepaths) == 0:
            return None
        self.image_index = self.image_index % len(self.filepaths)
        return self.filepaths[self.image_index]

    def openDir(self, newdir=None) -> None:
        """Open a new directory and prepare window

        Args:
            newdir (str, optional): Path of new directory. If blank, prompts user.

        Returns:
            TYPE: Description
        """
        if not newdir:
            self.update_idletasks()  # Bug with tkinter: the mainloop must loop before calling filedialog
            newdir = filedialog.askdirectory(initialdir=self.rootpath)
            # Check for "cancel" state
            if newdir is None or newdir == '':  # noqa: PLC1901
                return
            newdir = os.path.realpath(newdir)
            try:
                if os.path.relpath(newdir) == '.':
                    return
            except ValueError:
                # No shared base, ignore
                pass

        self.working_root_path = newdir
        self.rootpath = newdir
        # self.generatePaths(newdir)

        self.undo.clear()

        # Initialize images
        self.image_index = 0
        # self.deleted_images_count = 0

        # Initialize data
        self.reloadDirContext()

        self.frame_sidebar.progbar_prog.configure(maximum=(len(self.filepaths) - 1))
        # Just reloaded, so current length is max
        self.frame_sidebar.progbar_seek.configure(to=len(self.filepaths))

    def reloadDirContext(self) -> None:
        """Reload globs, keys, and context for our directory.
        """
        self.generatePaths(self.rootpath)

        dir_path_enum: enumerate[str] = enumerate(sorted(
            functools.reduce(operator.iadd, [glob.glob(a, recursive=True) for a in self.contextglobs], [])
        ))
        self.context_folders = [
            FolderOption(
                index=i,
                path=dir_path,
                label=os.path.relpath(
                    dir_path.lower(),
                    self.working_root_path
                ).replace('\\', '/')
            )
            for i, dir_path in
            dir_path_enum
        ]
        self.updateContextListFrame()
        self.resortImageList()

    def resortImageList(self) -> None:
        """Reload filepaths, rescan for images.
        """
        logger.info("Resorting image list")

        self.filepaths = self.sorter(
            filter(
                self.trash.isfile,  # Only non-deleted paths, according to our trash
                functools.reduce(operator.iadd, [glob.glob(a) for a in self.imageglobs], [])
            )
        )

        self.imageUpdate("Resorted image list")

    # Generators and logic

    def doRepeat(self) -> None:
        if self.prev_query:
            self.submit(entry=self.prev_query)
        else:
            raise ValueError("No prev_query defined!")

    def submit(self, event: Optional[Any] = None, entry: Optional[str] = "") -> None:
        """Processing when the user submits the "move" entry

        Args:
            event (bool, optional): Tk triggerinv event.
            entry (str, optional): Text of entry, if no triggering event.

        Returns:
            TYPE: Description
        """

        if event:
            entry = event.widget.get()
            widget = event.widget
        else:
            widget = self.frame_sidebar.entry
            # assert isinstance(entry, str)

        if entry == "" or entry is None:  # noqa: PLC1901
            self.nextImage()
            return

        if not isinstance(entry, str):
            raise ValueError(entry)

        if not isinstance(self.currentImagePath, str):
            raise ValueError("Not currently vising an image")

        old_file_path: str = self.currentImagePath

        try:
            best_folder: FolderOption = self.getBestFolder(entry)
        except EnvironmentError:
            if self.settings["makedirs"].var.get():
                self.moveToFolder(new_folder_name=entry)
                self.frame_sidebar.strv_prev_query.set(value=entry)
                self.prev_query = entry
                # TODO: Logic not clean here?
                widget.delete(0, last=tk.END)
            else:
                logger.error("Bad key %s", entry, exc_info=True)
                self.str_curfile.set(
                    "Invalid key: {}".format(entry))
            return

        destination_dir: str = best_folder.path
        self.frame_sidebar.strv_prev_query.set(best_folder.label)
        self.prev_query = best_folder.label

        # If the destination has an "unsorted" folder, move there instead.
        usubdir = os.path.join(destination_dir, "unsorted")
        if os.path.exists(usubdir):
            destination_dir = usubdir

        if not os.path.isdir(destination_dir):
            logger.error(f"In an invalid state: {destination_dir} is not a directory")
            self.reloadDirContext()
            return
        old_index = self.filepaths.index(old_file_path)

        def doMove() -> None:
            (_old_file_dir, old_file_name) = os.path.split(old_file_path)
            new_file_path: str = os.path.join(destination_dir, old_file_name)

            filesystem.moveFileToFile(old_file_path, destination_dir)

            def _undo(self) -> None:
                filesystem.moveFileToFile(new_file_path, old_file_path)
                self.filepaths.insert(old_index, old_file_path)
            self.undo.append(_undo)

        self.spool.enqueue(doMove)

        self.filepaths.remove(old_file_path)

        # Clear field
        self.frame_sidebar.reFocusEntry()

        # If auto, pause to prevent user error
        if self.settings["aggressive"].var.get():
            widget.bell()
            widget.config(state='disabled')
            widget.after(600, lambda: (widget.config(
                state='normal'), widget.delete(0, last=tk.END)))

        self.imageUpdate("Submit")

    def getBestFolder(self, entry) -> FolderOption:
        """Wrapper around getBestFolders to find a single best folder.

        Args:
            entry (str): Shortcode, search term
            indexOnly (bool, optional): Description

        Returns:
            TYPE: Description

        Raises:
            EnvironmentError: If there is more than one acceptable folder
        """
        best_folder_list: list[FolderOption] = self.getBestFolders(entry)
        if len(best_folder_list) == 1:
            return best_folder_list[0]
        else:
            raise EnvironmentError(f"Ambiguous folder selected, could be any of: {best_folder_list}")

    def getBestFolders(self, entry: str) -> list[FolderOption]:
        """Finds folders that match the search term

        Args:
            entry (str): Shortcode, search term
            indexOnly (bool, optional): Description

        Returns:
            list<int>: List of valid match INDEXES. Indexes reference self.folder_names
        """
        query: str = entry.lower()

        folder_names = tuple(opt.label for opt in self.context_folders)

        # Exact match
        if query in folder_names:
            return [self.context_folders[folder_names.index(query)]]

        if query != "":  # noqa: PLC1901
            # There is not a perfect mapping
            return [
                self.context_folders[folder_names.index(result)]
                for result in
                getMatches(query, folder_names, fuzzy=self.settings["fuzzy"].var.get()).all
            ]

        return []

    def generatePaths(self, root_path) -> None:
        """Generate imageglobs and contextglobs for a root path, setting
            self.imageglobs
            self.contextglobs
            self.newFolderRoot

        Args:
            root_path (str): Root path to search
        """
        logger.info("Generating paths for: {}".format(root_path))
        logger.info(f"Filtering to files with extensions {self.image_ext_globs}")

        # Pull loose images
        self.imageglobs = [
            os.path.join(glob.escape(root_path), ext)
            for ext in self.image_ext_globs
        ]

        # print("Image Globs:", self.imageglobs)

        subdirectory_unsorted = os.path.join(root_path, "unsorted")
        parent_path = os.path.join(root_path, "..")

        if os.path.exists(subdirectory_unsorted):
            self.promptLooseCleanup(root_path, subdirectory_unsorted)

        # Put images in same-level directories
        has_sub_dirs = glob.glob(os.path.join(root_path, "*", ""))
        working_root_path = (root_path if has_sub_dirs else parent_path)
        self.working_root_path = working_root_path

        # Candidate folders: folders in root_path
        self.contextglobs = [
            os.path.join(glob.escape(root_path), "*", "")
        ]

        # Candidate folders: "up" folder (of root OR parent)
        # self.contextglobs.append(
        #     os.path.join(glob.escape(working_root_path), "..", "")
        # )

        if self.settings["parent_dirs"].var.get() or not has_sub_dirs:
            self.contextglobs.append(os.path.join(glob.escape(parent_path), "*", ""))

        # Pull images from unsorted too
        self.imageglobs += [
            os.path.join(subdirectory_unsorted, ext)
            for ext in self.image_ext_globs
        ]

        # We don't want unsorted in here
        if self.settings["recursive"].var.get():
            self.contextglobs.append(
                os.path.join(glob.escape(working_root_path), "*", "*", "")
            )
            if self.settings["parent_dirs"].var.get():
                self.contextglobs.append(
                    os.path.join(glob.escape(parent_path), "*", "*", "")
                )

        logger.info("Context globs: %s", self.contextglobs)
        self.newFolderRoot = working_root_path  # Where we make new folders

    def nextImage(self, event=None) -> None:  # noqa: ARG002
        """Show the next image
        """
        self.image_index += 1
        self.imageUpdate("Next image")

    def prevImage(self, event=None) -> None:  # noqa: ARG002
        """Show the previous image
        """
        self.image_index -= 1
        self.imageUpdate("Prev image")

    def gotoImage(self, index) -> None:
        """Go to an image (based on a seek event)
        """
        self.image_index = int(float(index))
        self.imageUpdate("Seek")

    def imageUpdate(self, event=None) -> None:  # noqa: ARG002
        """Update widgets to reflect a new selected image
        """

        if len(self.filepaths) == 0:
            self.image_index = 0
            self.str_curfile.set("No more images found!")
            self.canvas.clear()
            return

        # Wraparound image indicies
        self.image_index = self.image_index % len(self.filepaths)

        while self.currentImagePath is not None and not self.canvas.setFile(self.currentImagePath):
            self.filepaths.remove(self.currentImagePath)

        self.updateLabelFileName()
        self.frame_sidebar.var_progbar_seek.set(self.image_index)
        self.frame_sidebar.var_progbar_prog.set(len(self.filepaths))

        # Preloading
        start = (self.image_index - 4) % len(self.filepaths)
        end = (self.image_index + 8) % len(self.filepaths)

        # Wraparound
        if start > end:
            self.canvas.preloadImage(self.filepaths[start:len(self.filepaths)])
            self.canvas.preloadImage(self.filepaths[0:end])
        else:
            self.canvas.preloadImage(self.filepaths[start:end])

    # Disk action

    def keepImage(self, event=None) -> None:  # noqa: ARG002
        """Summary

        Args:
            event (None, optional): Description
        """
        keepdir = os.path.join(self.str_keepdir.get(), os.path.split(self.rootpath)[1])
        print("keepimage", keepdir)
        self.spool.enqueue(self.moveToFolder, (), {"new_folder_name": keepdir})

    def addUnsortedToBase(self) -> None:
        os.makedirs(os.path.join(self.rootpath, "Unsorted"))
        self.openDir(os.path.realpath(self.rootpath))

    def askDelete(self, event) -> None:  # noqa: ARG002
        self.delete()

    def fastDelete(self, event) -> None:  # noqa: ARG002
        self.delete(preconfirmed=True)

    def delete(self, preconfirmed=False) -> None:
        """Delete the currently selected file

        Args:
            preconfirmed (bool, optional): Description
        """
        if self.currentImagePath is None:
            raise ValueError("Cannot delete; no image selected!")

        file_to_delete: str = self.currentImagePath

        confirmed = preconfirmed or messagebox.askyesno(
            "Confirm", "{}\nAre you sure you want to delete this file?\n(The file will be trashed, and semi-recoverable.)".format(file_to_delete))
        if confirmed:
            old_index = self.filepaths.index(file_to_delete)
            self.filepaths.remove(file_to_delete)

            self.trash.delete(file_to_delete)
            # self.deleted_images_count += 1

            def _undo(self):
                """Summary
                """
                self.trash.undo()
                self.canvas.markCacheDirty(file_to_delete)
                self.filepaths.insert(old_index, file_to_delete)
                # self.deleted_images_count -= 1
                # self.prevImage()
            self.undo.append(_undo)

            # spool.enqueue(trash, (file_to_delete,), dict(undos=self.undo))
            self.canvas.markCacheDirty(file_to_delete)
            self.imageUpdate("File deleted")

    def doPrefixRename(self, event) -> None:
        entry = event.widget.get()
        if entry == "":  # noqa: PLC1901
            self.nextImage()
            return

        if self.currentImagePath is None:
            raise ValueError("Cannot do prefix rename; no image selected!")

        old_file_path: str = self.currentImagePath
        _old_file_dir, old_file_name = os.path.split(old_file_path)
        old_plain, _old_ext = os.path.splitext(old_file_name)

        self._dorename(entry + '_' + old_plain)
        event.widget.delete(0, last=tk.END)

    def dorename(self, event) -> None:
        """Rename current file."""
        entry = event.widget.get()
        if entry == "":  # noqa: PLC1901
            self.nextImage()
            return

        self._dorename(entry)
        event.widget.delete(0, last=tk.END)

    def _dorename(self, new_file_name) -> None:
        """Rename current file to new_file_name
        """
        if self.currentImagePath is None:
            raise ValueError("Cannot rename; no image selected!")

        old_file_path: str = self.currentImagePath
        _old_filename, old_ext = os.path.splitext(old_file_path)

        (old_file_dir, old_file_name) = os.path.split(old_file_path)
        output_file_path = os.path.join(old_file_dir, new_file_name + old_ext)
        if os.path.isfile(output_file_path):
            if self.settings["confident"].var.get():
                logger.info("Renaming conflicting file '%s'", output_file_path)
                filesystem.renameFileOnly(output_file_path, new_file_name + "_displaced")
            else:
                stem, _ext = os.path.splitext(new_file_name)
                style = f"{stem} (<#>)"
                i = 0
                while os.path.isfile(output_file_path):
                    i += 1
                    new_file_name = style.replace('<#>', str(i))
                    output_file_path = os.path.join(old_file_dir, new_file_name + old_ext)
                    if i > 100:  # noqa: PLR2004
                        raise EnvironmentError("Too many renames")
                if os.path.isfile(output_file_path):
                    raise FileExistsError(output_file_path)
        try:
            logger.info(f"{old_file_path} -> {new_file_name}")
            filesystem.renameFileOnly(old_file_path, new_file_name)
            self.undo.append(
                lambda s: filesystem.renameFileOnly(  # noqa: ARG005
                    output_file_path,
                    old_file_name
                ))

            self.canvas.markCacheDirty(old_file_path)

            if self.settings["auto_reload"].var.get():
                self.resortImageList()

        except FileExistsError:
            logger.error("Can't rename file %s: file exists", old_file_path, exc_info=True)

    def moveToFolder(self, event=None, new_folder_name="") -> None:
        """Move the current image to a folder, which can be new.
        """
        if event:
            new_folder_name = event.widget.get()

        if self.currentImagePath is None:
            raise ValueError("Cannot move; no image selected!")

        old_file_path: str = self.currentImagePath
        if new_folder_name == "":  # noqa: PLC1901
            self.nextImage()
            self.frame_sidebar.reFocusEntry()
            return
        try:
            newdir: str = os.path.join(self.newFolderRoot, new_folder_name)
            if not os.path.isdir(newdir):
                os.makedirs(newdir, exist_ok=True)
                self.reloadDirContext()

            _old_folder, old_filename = os.path.split(old_file_path)
            filesystem.moveFileToDir(old_file_path, newdir)

            # self.deleted_images_count += 1
            # TODO: Technically, this undo should decrement the deleted images count? Requires a rewrite.
            self.undo.append(
                lambda self: filesystem.moveFileToFile(  # noqa: ARG005
                    os.path.join(newdir, old_filename), old_file_path
                )
            )

            self.frame_sidebar.strv_prev_query.set(new_folder_name)
            self.prev_query = new_folder_name

            self.canvas.markCacheDirty(old_file_path)

            self.filepaths.remove(old_file_path)
            self.image_index -= 1
            self.nextImage()

        except Exception:
            logger.error("Can't move to folder", exc_info=True)
            raise

        # Clear field
        if event:
            event.widget.delete(0, last=tk.END)

        # self.frame_sidebar.reFocusEntry()

    def doUndo(self, event) -> None:  # noqa: ARG002
        """Process an undo operation, handling the stack.
        """
        if len(self.undo) == 0:
            return

        self.spool.finish(resume=True)

        op = self.undo.pop()
        op(self)
        self.imageUpdate("Undo operation")


def main() -> None:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument(
            "-b", "--base",
            help="Root folder. Should contain folders, one of which can be named unsorted.",
            default=filesystem.userProfile("Downloads"))
        ap.add_argument(
            "-e", "--extensions", nargs='+', default=_MATCHEXTS,
            help="Substrings in the path to penalize during file sorting.")
        args = ap.parse_args()

        FileSorter(args.base, args.extensions)
    except (Exception, KeyboardInterrupt):
        # Postmortem on uncaught exceptions
        logger.error("Uncaught exception", exc_info=True)
    finally:
        # Cleanup
        os.abort()


if __name__ == "__main__":
    main()
