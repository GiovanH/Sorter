"""sort.py
sort images

Attributes:
    COMPLETION_KEYS (list): Keys that signify completion
    FILL (TYPE): Tk shortcut for all sticky directions
    IMAGEEXTS (list): Valid file extensions for images
    WFILL (TYPE): Tk shortcut for wide sticky directions
"""

import tkinter as tk

from snip import loom
from snip.stream import TriadLogger

from PIL import Image
from tkinter import filedialog
from tkinter import messagebox

import os

import glob

import argparse
import traceback

import pymaybe

import snip
import random

import sbf
from snip.tkit.contentcanvas import ContentCanvas


IMAGEEXTS = ["png", "jpg", "gif", "bmp", "jpeg", "tif", "gifv", "jfif", "tga", "pdn", "psd"]
VIDEOEXTS = ["webm", "mp4", "mov"]
_IMAGEEXTS = ["*." + e for e in IMAGEEXTS]
_VIDEOEXTS = ["*." + e for e in VIDEOEXTS]
MATCHEXTS = IMAGEEXTS + VIDEOEXTS
_MATCHEXTS = _IMAGEEXTS + _VIDEOEXTS


COMPLETION_KEYS = [32, 8]

MAX_TRASH_HISTORY = 32

logger = TriadLogger(__name__)


def baseFolderName(path):
    return os.path.basename(os.path.split(path)[0])


def imageSize(filename):
    """Get the number of pixels in an image

    Args:
        filename (str): Path to file

    Returns:
        int: Number of pixels in image
    """
    try:
        w, h = Image.open(filename).size
        return w * h
    except OSError:
        logger.warning("WARNING! OS error with file: ", filename)
        return 0
    except FileNotFoundError:
        logger.warning("WARNING! File not found: ", filename)
        return 0


def md5(path):
    import hashlib
    """Gives the md5 hash of a file on disk.
    Args:
        path (str): Path to a file
    
    Returns:
        str: MD5 hex digest
    """
    with open(path, 'rb') as afile:
        h = hashlib.md5()
        h.update(afile.read())
        return h.hexdigest()


def isImage(filename):
    """
    Args:
        filename (str): Path to a file

    Returns:
        bool: True if the path points to an image, else False.
    """
    try:
        return os.path.splitext(filename)[1].lower() in _IMAGEEXTS
    except IndexError:
        # No extension
        return False


def isVideo(filename):
    """
    Args:
        filename (str): Path to a file

    Returns:
        bool: True if the path points to an video, else False.
    """
    try:
        return os.path.splitext(filename)[1].lower() in _VIDEOEXTS
    except IndexError:
        # No extension
        return False


def fingerprintImage(image_path):
    import imagehash
    try:
        image = Image.open(image_path)
        proc_hash = str(imagehash.dhash(image, hash_size=10))
        # Compress:
        # proc_hash = proc_hash.decode("hex").encode("base64")
    except:
        logger.error("Can't fingerprint %s", image_path, exc_info=True)
        proc_hash = md5(image_path)
    return proc_hash


class FileSorter(tk.Tk):

    """Summary

    Attributes:
        canvas (TYPE): Description
        context (TYPE): Description
        contextglobs (TYPE): Description
        curimg (TYPE): Description
        filepaths (TYPE): Description
        frame_sidebar (TYPE): Description
        image_index (int): Description
        imageglobs (TYPE): Description
        keycache (dict): Description
        folders_by_name (TYPE): Description
        folder_names (TYPE): Description
        lab_curfile (TYPE): Description
        rootpath (TYPE): Description
        str_context (tk.Stringvar): Description
        str_curfile (tk.Stringvar): Description
        undo (list): Stack of functions to process via ctrl+z
    """

    def __init__(self, rootpath, match_fileglobs, *args, **kwargs):
        """File sorter main window

        Passthrough to tk.Tk
        Args:
            rootpath (TYPE): Description
            *args: Description
            **kwargs: Description
        """
        super(FileSorter, self).__init__(*args, **kwargs)

        try:
            self.image_index = 0
            self.str_context = tk.StringVar()
            self.undo = []
            self.filepaths = []
            self.match_fileglobs = match_fileglobs

            self.spool = loom.Spool(1, "Sort misc", belay=True)
            self.trash = snip.filesystem.Trash(verbose=True)

            self.settings = {
                "fuzzy": (tk.BooleanVar(), "Fuzzy search"),
                "parent_dirs": (tk.BooleanVar(), "Use parent directories"),
                "confident": (tk.BooleanVar(), "Displace rename conflicts"),
                "aggressive": (tk.BooleanVar(), "Automatically process on unambigious input"),
                "auto_reload": (tk.BooleanVar(value=True), "Reload on change")
            }
            self.settings["parent_dirs"][0].trace("w", lambda *a: self.reloadDirContext())

            self.sortkeys = {
                "{}, {}".format(name, order): (
                    lambda items, keyfunc=keyfunc, orderb=orderb: sorted(items, key=keyfunc, reverse=orderb)
                )
                for (name, keyfunc) in [
                    ("Alphabetical", str.lower,),
                    ("Integers", lambda f: int(os.path.splitext(os.path.split(f)[1])[0]) if os.path.splitext(os.path.split(f)[1])[0].isnumeric() else -1),
                    ("File size", os.path.getsize,),
                    ("Last modified", os.path.getmtime,),
                    ("File type", lambda f: os.path.splitext(f)[1],),
                    ("Image Dimensions", imageSize,),
                    ("Image Height", lambda f: pymaybe.maybe(Image.open(f)).size[1].or_else(0),),
                    ("Image Width", lambda f: pymaybe.maybe(Image.open(f)).size[0].or_else(0),),
                    ("Procedural hash", fingerprintImage,),
                    ("Random", lambda f: random.random())
                ]
                for (order, orderb) in [
                    ("asc", False,), ("desc", True,)
                ]
            }

            self.sorter = sorted

            self.lastwh = tuple()
            self.onResizeCallback = None

            self.initwindow()

            self.openDir(rootpath)

            self.mainloop()
        except KeyboardInterrupt:
            logger.warning("Window init aborted")
            self.destroy()

    # Windowing and GUI

    def destroy(self):
        self.spool.finish()
        self.trash.finish()
        super().destroy()

    def initwindow(self):
        """Initialize widgets for the window
        """

        self.geometry("860x600")

        # # Header stuff # #
        # current filename label
        self.str_curfile = tk.StringVar(value="No Images Found")
        self.lab_curfile = tk.Label(textvariable=self.str_curfile, height=2)
        self.lab_curfile.grid(row=0, column=1)

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
        self.bind("<End>", self.doUndo)

        self.canvas.bind("<f>", self.nextImage)
        self.canvas.bind("<s>", self.prevImage)

        self.canvas.bind("<d>", self.fastDelete)
        self.canvas.bind("<e>", self.keepImage)
        self.canvas.bind("<w>", self.canvas.quicksave)

        self.canvas.bind("<a>", self.doUndo)

        self.frame_sidebar = sbf.SidebarFrame(
            self,
            submitCallback=self.submit
        )
        self.frame_sidebar.config(bd=3, relief=tk.RIDGE)
        self.frame_sidebar.grid(row=0, rowspan=2, column=0, sticky="NSEW")

        self.columnconfigure(0, minsize=160)

    def labelFileName(self):
        """Generate a user-friendly filename for the header
        """
        if self.currentImagePath is None:
            self.str_curfile.set("No image.")
            return

        prettyname = self.currentImagePath
        __, fileext = os.path.splitext(self.currentImagePath)
        try:
            filename = os.path.split(self.currentImagePath)[1]
            filesize = snip.strings.bytes_to_string(os.path.getsize(self.currentImagePath))
            try:
                frames = snip.image.framesInImage(self.currentImagePath)
                w, h = Image.open(self.currentImagePath).size
                prettyname = f"{filename} [{frames}f]\n{filesize} [{w}x{h}px]"
            except OSError:
                prettyname = f"{filename}\n{filesize}"
        except OSError:
            logger.error("OS error while getting file info", exc_info=True)
            pass
        self.str_curfile.set(prettyname)

    def promptLooseCleanup(self, rootpath, destpath):
        assert os.path.isdir(rootpath)
        assert os.path.isdir(destpath)
        imageglobs = [os.path.join(glob.escape(rootpath), ext) for ext in self.match_fileglobs]
        loose_files = list(filter(self.trash.isfile, sum([glob.glob(a) for a in imageglobs], [])))
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
                    snip.filesystem.moveFileToDir(oldfile, destpath)
                except FileExistsError:
                    pass

    def populateContextKeyFrame(self):
        """Generate and refresh the sidebar listbox
        """
        self.frame_sidebar.listbox_context.configure(state=tk.NORMAL)
        self.frame_sidebar.listbox_context.delete(0, self.frame_sidebar.listbox_context.size())
        for val in self.folder_names:
            self.frame_sidebar.listbox_context.insert(
                tk.END, "{}".format(val[0:15]))
        # self.frame_sidebar.listbox_context.configure(state=tk.DISABLED)

    # Context and context manipulation

    def changeMatchGlobs(self, newmatchglobs=None):
        logger.debug(self.match_fileglobs)
        if not newmatchglobs:
            from tkinter.simpledialog import askstring
            newmatchglobs = askstring("Filter", "Enter new globs seperated by ', '", initialvalue=", ".join(self.match_fileglobs))

        logger.debug(newmatchglobs)

        self.match_fileglobs = newmatchglobs.split(", ")
        self.reloadDirContext()
        self.imageUpdate()


    @property
    def currentImagePath(self):
        if len(self.filepaths) == 0:
            return None
        self.image_index = self.image_index % len(self.filepaths)
        return self.filepaths[self.image_index]

    def openDir(self, newdir=None):
        """Open a new directory and prepare window

        Args:
            newdir (str, optional): Path of new directory. If blank, prompts user.
        """
        if not newdir:
            self.update_idletasks()  # Bug with tkinter: the mainloop must loop before calling filedialog
            newdir = os.path.realpath(filedialog.askdirectory(initialdir=self.rootpath))
            try:
                if os.path.relpath(newdir) == '.':
                    return
            except ValueError:
                # No shared base
                pass
        self.rootpath = newdir
        # self.generatePaths(newdir)

        self.undo.clear()

        # Initialize images
        self.image_index = 0

        # Initialize data
        self.reloadDirContext()

        # self.resortImageList() #  done in reloadDirContext

        self.frame_sidebar.progbar_prog.configure(maximum=len(self.filepaths))

    def reloadDirContext(self):
        """Reload globs, keys, and context for our directory.
        """
        self.generatePaths(self.rootpath)

        context = sum([glob.glob(a) for a in self.contextglobs], [])
        self.folders_by_name = {baseFolderName(path.lower()): path for path in context}
        self.folder_names = list(self.folders_by_name.keys())  # Constant order
        self.keycache = {}
        self.populateContextKeyFrame()
        self.resortImageList()

    def resortImageList(self):
        """Reload filepaths, rescan for images.
        """
        logger.info("Resorting image list")
        self.filepaths = self.sorter(filter(self.trash.isfile, sum([glob.glob(a) for a in self.imageglobs], [])))
        self.imageUpdate("Resorted image list")

    # Generators and logic

    def submit(self, event=False, entry=""):
        """Processing when the user submits the "move" entry

        Args:
            event (bool, optional): Tk triggerinv event.
            entry (str, optional): Text of entry, if no triggering event.
        """

        old_file_path = self.currentImagePath
        if event:
            entry = event.widget.get()
            widget = event.widget
        else:
            widget = self.frame_sidebar.entry

        if entry == "":
            self.nextImage()
            return

        try:
            (short, choice) = self.getBestFolder(entry)
        except EnvironmentError:
            logger.error("Bad key %s", entry, exc_info=True)
            self.str_curfile.set(
                "Invalid key: {}".format(entry))
            return

        destination_dir = choice
        usubdir = os.path.join(destination_dir, "unsorted")
        if os.path.exists(usubdir):
            destination_dir = usubdir

        if not os.path.isdir(destination_dir):
            logger.error("In an invalid state:", destination_dir, "is not a directory")
            self.reloadDirContext()
            return
        old_index = self.filepaths.index(old_file_path)
        
        def doMove():
            (old_file_dir, old_file_name) = os.path.split(old_file_path)
            new_file_path = os.path.join(destination_dir, old_file_name)
            
            snip.filesystem.moveFileToFile(old_file_path, destination_dir)

            def _undo():
                snip.filesystem.moveFileToFile(new_file_path, old_file_path)
                self.filepaths.insert(old_index, old_file_path)
            self.undo.append(_undo)

        self.spool.enqueue(doMove)

        self.filepaths.remove(old_file_path)

        # Clear field
        self.frame_sidebar.reFocusEntry()

        # If auto, pause to prevent error
        if self.settings["aggressive"][0].get():
            widget.bell()
            widget.config(state='disabled')
            widget.after(600, lambda: (widget.config(
                state='normal'), widget.delete(0, last=tk.END)))

        self.imageUpdate("Submit")

    def getBestFolder(self, entry, indexOnly=False):
        """Wrapper around getBestFolders to find a single best folder.

        Args:
            entry (str): Shortcode, search term
            fuzzy (bool, optional): Use fuzzy algorithm

        Returns:
            TYPE: Description

        Raises:
            EnvironmentError: If there is more than one acceptable folder
        """
        gbf = self.getBestFolders(entry, indexOnly=indexOnly)
        if len(gbf) == 1:
            return gbf[0]
        else:
            raise EnvironmentError("Ambiguous folder selected, could be any of: {}".format(gbf))

    def getBestFolders(self, entry, indexOnly=False):
        """Finds folders that match the search term

        Args:
            entry (str): Shortcode, search term
            fast (bool, optional): Use fast algorithm

        Returns:
            list<int>: List of valid match INDEXES. Indexes reference self.folder_names
        """
        entry = entry.lower()

        fuzzy = self.settings["fuzzy"][0].get()

        if self.keycache.get(entry) is not None:
            cachedIndex = self.keycache.get(entry)
            if indexOnly:
                return [cachedIndex]
            else:
                return [(self.folder_names[cachedIndex], self.folders_by_name.get(self.folder_names[cachedIndex]))]

        if entry in self.folder_names:
            if indexOnly:
                return [self.folder_names.index(entry)]
            else:
                return [(entry, self.folders_by_name.get(entry))]

        if entry != "":
            keys = self.folder_names
            # There is not a perfect mapping
            matchindices = [k.find(entry) for k in keys]
            matches = [i for i in range(0, len(matchindices)) if matchindices[i] == 0]
            if len(matches) == 1:
                self.keycache[entry] = matches[0]    # Learn.
                logger.debug("Learning: {} : {}".format(entry, matches[0]))
            elif fuzzy:
                matches = [i for i in range(0, len(matchindices)) if matchindices[i] != -1]
                if len(matches) == 1:
                    self.keycache[entry] = matches[0]    # Learn.
                    logger.debug("Learning: {} : {}".format(entry, matches[0]))
            if indexOnly:
                return matches
            else:
                return [(self.folder_names[index], self.folders_by_name.get(self.folder_names[index])) for index in matches]

    def generatePaths(self, rootpath):
        """Generate imageglobs and contextglobs for a root path

        Args:
            rootpath (str): Root path to search
        """
        logger.info("Generating paths for: {}".format(rootpath))
        # Pull loose images
        self.imageglobs = [
            os.path.join(glob.escape(rootpath), ext) for ext in self.match_fileglobs]

        # print("Image Globs:", self.imageglobs)

        subdirectory_unsorted = os.path.join(rootpath, "unsorted")

        parentpath = os.path.join(rootpath, "..")
        
        if os.path.exists(subdirectory_unsorted):
            self.promptLooseCleanup(rootpath, subdirectory_unsorted)

        # Put images in same-level directories

        has_sub_dirs = glob.glob(os.path.join(rootpath, "*", ""))

        self.contextglobs = [
            os.path.join(glob.escape(rootpath), "*", "")
        ]

        if has_sub_dirs:
            self.contextglobs.append(os.path.join(glob.escape(rootpath), "..", ""))
        else:
            self.contextglobs.append(os.path.join(glob.escape(parentpath), "..", ""))

        if self.settings["parent_dirs"][0].get() or not has_sub_dirs:
            self.contextglobs.append(os.path.join(glob.escape(parentpath), "*", ""))

        # Pull images from unsorted too
        self.imageglobs += [
            os.path.join(subdirectory_unsorted, ext) for ext in self.match_fileglobs]

        logger.debug("Context globs: %s", self.contextglobs)
        if has_sub_dirs:
            self.newFolderRoot = rootpath  # Where we make new folders
        else:
            self.newFolderRoot = parentpath  # Where we make new folders

    def nextImage(self, event=None):
        """Show the next image

        Args:
            event (optional): tk triggering event
        """
        self.image_index += 1
        self.imageUpdate("Next image")

    def prevImage(self, event=None):
        """Show the previous image

        Args:
            event (optional): tk triggering event
        """
        self.image_index -= 1
        self.imageUpdate("Prev image")

    def gotoImage(self, index):
        """Show the previous image

        Args:
            event (optional): tk triggering event
        """
        self.image_index = int(float(index))
        self.imageUpdate("Seek")

    def imageUpdate(self, event=None):
        # print(
        #     "Image Update: {}/{} (Cause: {})".format(
        #         self.image_index, 
        #         len(self.filepaths), 
        #         event
        #     )
        # )

        if len(self.filepaths) == 0:
            self.image_index = 0
            self.str_curfile.set("No more images found!")
            self.canvas.clear()
            return

        # Wraparound image indicies
        prev_index = self.image_index
        self.image_index = self.image_index % len(self.filepaths)
        # if self.image_index != prev_index:
        #     print("Wrapped, reloading...")
        #     print("W: {}/{}".format(self.image_index, len(self.filepaths) - 1))

        while not self.canvas.setFile(self.currentImagePath):
            self.filepaths.remove(self.currentImagePath)
            
        self.labelFileName()
        self.frame_sidebar.var_progbar_seek.set(self.image_index)
        self.frame_sidebar.progbar_seek.configure(to=len(self.filepaths) - 1)
        self.frame_sidebar.var_progbar_prog.set(len(self.filepaths))

        # Preloading
        start = (self.image_index - 4) % len(self.filepaths)
        end = (self.image_index + 8) % len(self.filepaths)
        # Wraparound
        if start > end:
            # print(start, ":", len(self.filepaths))
            self.canvas.preloadImage(self.filepaths[start:len(self.filepaths)])
            # print(0, ":", end)
            self.canvas.preloadImage(self.filepaths[0:end])
        else:
            # print(start, ":", end)
            self.canvas.preloadImage(self.filepaths[start:end])

    # Disk action

    def keepImage(self, event=None):
        keepdir = os.path.join("keep", os.path.split(self.rootpath)[1])
        self.spool.enqueue(self.moveToFolder, (), dict(new_folder_name=keepdir))

    def addUnsortedToBase(self):
        os.makedirs(os.path.join(self.rootpath, "Unsorted"))
        self.openDir(os.path.realpath(self.rootpath))

    def askDelete(self, event):
        self.delete()

    def fastDelete(self, event):
        self.delete(preconfirmed=True)

    def delete(self, preconfirmed=False):
        """Delete the currently selected file
        """
        file_to_delete = self.currentImagePath
        confirmed = preconfirmed or messagebox.askyesno(
            "Confirm", "{}\nAre you sure you want to delete this file?\n(The file will be trashed, and semi-recoverable.)".format(file_to_delete))
        if confirmed:
            old_index = self.filepaths.index(file_to_delete)
            self.filepaths.remove(file_to_delete)

            self.trash.delete(file_to_delete)

            def _undo(self):
                self.trash.undo()
                self.canvas.markCacheDirty(file_to_delete)
                self.filepaths.insert(old_index, file_to_delete)
                # self.prevImage()
            self.undo.append(_undo)

            # spool.enqueue(trash, (file_to_delete,), dict(undos=self.undo))
            self.canvas.markCacheDirty(file_to_delete)
            self.imageUpdate("File deleted")

    def dorename(self, event):
        """Rename current file.

        Args:
            event (TYPE): Tk triggering event
        """

        entry = event.widget.get()
        if entry == "":
            self.nextImage()
            return

        old_file_path = self.currentImagePath

        new_file_name = entry + os.path.splitext(old_file_path)[1]

        (old_file_dir, old_file_name) = os.path.split(old_file_path)
        conflicting_file_path = os.path.join(old_file_dir, new_file_name)
        if os.path.isfile(conflicting_file_path):
            if self.settings["confident"][0].get():
                logger.info("Renaming conflicting file '%s'", conflicting_file_path)
                snip.filesystem.renameFileOnly(conflicting_file_path, entry + "_displaced")
            else:
                return
        try:
            snip.filesystem.renameFileOnly(old_file_path, entry)
            self.undo.append(
                lambda s: snip.filesystem.renameFileOnly(
                    conflicting_file_path,
                    old_file_name
                ))

            self.canvas.markCacheDirty(old_file_path)

            if self.settings["auto_reload"][0].get():
                self.resortImageList()

        except FileExistsError:
            logger.error("Can't rename file %s: file exists", old_file_path, exc_info=True)
        finally:
            # Clear field
            event.widget.delete(0, last=tk.END)
        # self.frame_sidebar.reFocusEntry()

    def moveToFolder(self, event=None, new_folder_name=""):
        """Move the current image to a folder, which can be new.

        Args:
            event (TYPE): Tk triggering event
        """
        if event:
            new_folder_name = event.widget.get()
        old_file_path = self.currentImagePath
        if new_folder_name == "":
            self.nextImage()
            self.frame_sidebar.reFocusEntry()
            return
        try:
            newdir = os.path.join(self.newFolderRoot, new_folder_name)
            if not os.path.isdir(newdir):
                os.makedirs(newdir, exist_ok=True)
                self.reloadDirContext()
            # filemove(old_file_path, newdir)

            old_folder, old_filename = os.path.split(old_file_path)
            snip.filesystem.moveFileToDir(old_file_path, newdir)
            self.undo.append(
                lambda self: snip.filesystem.moveFileToFile(
                    os.path.join(newdir, old_filename), old_file_path)
            )

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

    def doUndo(self, event):
        """Process an undo operation, handling the stack.

        Args:
            event: Tk triggering event
        """
        if len(self.undo) == 0:
            return

        self.spool.finish(resume=True)

        op = self.undo.pop()
        op(self)
        # if self.settings["auto_reload"][0].get():
        #     self.resortImageList()
        self.imageUpdate("Undo operation")


def run_threaded():
    """Run the program with threading support
    """

    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("-b", "--base",
                        help="Root folder. Should contain folders, one of which can be named unsorted.",
                        default=snip.filesystem.userProfile("Downloads"))
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
    run_threaded()
