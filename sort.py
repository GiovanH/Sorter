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

from PIL import Image
from PIL import ImageTk
from tkinter import filedialog
from tkinter import messagebox

import cv2
import os
import shutil

from glob import glob
from os.path import sep
from send2trash import send2trash
from tempfile import mkdtemp

import argparse
import errno
import traceback

from math import floor

import pymaybe

import snip

import sbf


IMAGEEXTS = ["png", "jpg", "gif", "bmp", "jpeg", "tif", "gifv", "jfif"]
VIDEOEXTS = ["webm", "mp4"]
_IMAGEEXTS = ["." + e for e in IMAGEEXTS]
_VIDEOEXTS = ["." + e for e in VIDEOEXTS]
MATCHEXTS = IMAGEEXTS + VIDEOEXTS

COMPLETION_KEYS = [32, 8]

spool = loom.Spool(1, belay=True)


def baseFolderName(path):
    return os.path.basename(os.path.split(path)[0])


def copy_to_clipboard(filepath):
    from io import BytesIO
    import win32clipboard
    from PIL import Image

    def send_to_clipboard(clip_type, data):
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(clip_type, data)
        win32clipboard.CloseClipboard()

    image = Image.open(filepath)

    output = BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()

    send_to_clipboard(win32clipboard.CF_DIB, data)


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
    except FileNotFoundError:
        print("WARNING! File not found: ", filename)
        return 0
    except OSError:
        print("WARNING! OS error with file: ", filename)
        return 0


# def filemove(src, dst):
#     """Move a file

#     Args:
#         src (str): Source path
#         dst (str): Destination path
#     """
#     print("{} -> {}".format(src, dst))
#     try:
#         shutil.move(src, dst)
#     except shutil.Error as e:
#         print(e.errno, errno.EEXIST, e.errno == errno.EEXIST)
#         traceback.print_exc()


trashdir = mkdtemp(prefix="srt-")
trashed_files = []
print("Opened trash directory as", trashdir)


def trash(fileToDelete, undos=None):
    """Args:
        fileToDelete (str): Path to trash
    """
    max_trash_history = 18

    # Clean trash
    if len(trashed_files) > max_trash_history:
        surplus = trashed_files[:-max_trash_history]
        really_trash_files(surplus)
        for n in surplus:
            trashed_files.remove(n)

    (folder, file) = os.path.split(fileToDelete)
    trashed_file_path = os.path.join(trashdir, file)

    spool.enqueueSeries([
        (lambda: snip.filesystem.moveFileToFile(fileToDelete, trashed_file_path)),
        (lambda: trashed_files.append((trashed_file_path, fileToDelete,))),
        (lambda: undos.append(
            lambda self: (
                print("untrashing {}".format(file)),
                snip.filesystem.moveFileToFile(trashed_file_path, fileToDelete),
                trashed_files.remove((trashed_file_path, fileToDelete,)),
            ))),
    ])


def really_trash_files(trashed_files):
    spool.flush()
    for (trashed_file_path, original_path) in trashed_files:
        spool.enqueue(target=really_trash_file, args=(trashed_file_path, original_path,))
        # spool.enqueue(target=send2trash, args=(trashed_file_path,))


def really_trash_file(trashed_file_path, original_path):
    try:
        snip.filesystem.moveFileToFile(trashed_file_path, original_path)
        path_to_trash = original_path
    except Exception as e:
        print(vars())
        print("Can't un-temp file ", trashed_file_path)
        path_to_trash = trashed_file_path
        # raise
    try:
        send2trash(path_to_trash)
        print("{} -> [trash]".format(path_to_trash))
    except Exception as e:
        print("{} -x> [trash]".format(path_to_trash))
        print(vars())
        print("Can't trash un-temp'd file. Putting it back. ")
        snip.filesystem.moveFileToFile(path_to_trash, trashed_file_path)


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
    if not isImage(image_path):
        proc_hash = md5(image_path)
    else:
        image = Image.open(image_path)
        proc_hash = str(imagehash.dhash(image, hash_size=10))
        # Compress:
        # proc_hash = proc_hash.decode("hex").encode("base64")
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
        image_on_canvas (TYPE): Description
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

    def __init__(self, rootpath, match_extensions, *args, **kwargs):
        """File sorter main window

        Passthrough to tk.Tk
        Args:
            rootpath (TYPE): Description
            *args: Description
            **kwargs: Description
        """
        super(FileSorter, self).__init__(*args, **kwargs)

        self.image_index = 0
        self.photoImageCache = {}
        self.str_context = tk.StringVar()
        self.undo = []
        self.filepaths = []
        self.match_extensions = match_extensions

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
                ("Image Height", lambda f: pymaybe.maybe(Image.open(f).size[1]).or_else(0),),
                ("Image Width", lambda f: pymaybe.maybe(Image.open(f).size[0]).or_else(0),),
                ("Procedural hash", fingerprintImage,)
            ]
            for (order, orderb) in [
                ("asc", False,), ("desc", True,)
            ]
        }

        # ool = list("abcdefghijkzmnozqrzstzwzya")

        # for key in self.sortkeys.keys():
        #     print(key)
        #     print(self.sortkeys[key](ool))

        self.sorter = sorted

        self.lastwh = tuple()
        self.onResizeCallback = None

        self.initwindow()

        self.openDir(snip.filesystem.userProfile("Downloads"))

        self.mainloop()

    # Windowing and GUI

    def onResize(self, event):
        wh = (self.canvas.winfo_width(), self.canvas.winfo_height())
        if wh == self.lastwh:
            # Window has not been resized, just moved.
            return
        else:
            print(self.lastwh, "->", wh)
            self.lastwh = wh

        # Clear waiting callbacks
        if self.onResizeCallback:
            self.after_cancel(self.onResizeCallback)

        def orc():
            self.photoImageCache.clear()
            print("resized, reloading")
            self.imageUpdate()
        self.onResizeCallback = self.after(25, orc)
        # self.onResizeCallback = self.after_idle(orc)

    def initwindow(self):
        """Initialize widgets for the window
        """

        self.bind("<Delete>", self.askDelete)
        self.bind("<Right>", self.nextImage)
        self.bind("<Left>", self.prevImage)

        self.bind("<Configure>", self.onResize)

        self.bind("<Control-w>", self.quicksave)
        self.bind("<Control-d>", self.fastDelete)
        self.bind("<Control-z>", self.doUndo)

        # self.bind("<Up>", self.keepImage)
        # self.bind("<Down>", self.fastDelete)
        self.bind("<End>", self.doUndo)

        # # Header stuff # #
        # current filename label
        self.str_curfile = tk.StringVar(value="No Images Found")
        self.lab_curfile = tk.Label(textvariable=self.str_curfile, font=("Helvetica", 22))
        self.lab_curfile.grid(row=0, column=1)

        # Canvas stuff
        self.canvas = tk.Canvas(takefocus=True)
        self.canvas.grid(column=1, row=1, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # create a menu
        popup = tk.Menu(self, tearoff=0)
        popup.add_command(label="Copy to clipboard", command=lambda: copy_to_clipboard(self.currentImagePath))  # , command=next) etc...
        popup.add_command(label="Save a copy", command=self.save_a_copy)
        popup.add_command(label="Save a copy (quick)", command=self.quicksave)
        popup.add_separator()

        def do_popup(event):
            # display the popup menu
            try:
                popup.tk_popup(event.x_root, event.y_root, 0)
            finally:
                # make sure to release the grab (Tk 8.0a1 only)
                popup.grab_release()

        self.canvas.bind("<Button-3>", do_popup)

        # self.canvas.bind("<Button-1>", lambda event: self.canvas.focus_set())

        self.canvas.bind("<f>", self.nextImage)
        self.canvas.bind("<s>", self.prevImage)

        self.canvas.bind("<d>", self.fastDelete)
        self.canvas.bind("<e>", self.keepImage)
        self.canvas.bind("<w>", self.quicksave)

        self.canvas.bind("<a>", self.doUndo)

        # set first image on canvas, an ImageTk.PhotoImage
        self.image_on_canvas = self.canvas.create_image(
            0, 0, anchor=tk.N + tk.W)

        self.frame_sidebar = sbf.SidebarFrame(
            self,
            submitCallback=self.submit
        )
        self.frame_sidebar.config(bd=3, relief=tk.RIDGE)
        self.frame_sidebar.grid(row=0, rowspan=2, column=0, sticky="NSEW")

        self.columnconfigure(0, minsize=160)

    def quicksave(self, event=None):
        downloads = snip.filesystem.userProfile("Downloads")
        snip.filesystem.copyFileToDir(self.currentImagePath, downloads)
        self.bell()

    def labelFileName(self):
        """Generate a user-friendly filename for the header
        """
        filepath = self.currentImagePath
        if filepath is None:
            self.str_curfile.set("No images.")
        else:
            prettyname = filepath
            __, fileext = os.path.splitext(filepath)
            if fileext.lower() in _IMAGEEXTS:
                try:
                    (w, h) = Image.open(filepath).size
                    prettyname = "{} [{w}x{h}]".format(
                        os.path.split(filepath)[1],
                        **vars()
                    )
                except OSError:
                    pass  # Fallback to filepath
            prettyname += " [{}]".format(snip.string.bytes_to_string(os.path.getsize(filepath)))
            self.str_curfile.set(prettyname)

    def promptLooseCleanup(self, rootpath, destpath):
        assert os.path.isdir(rootpath)
        assert os.path.isdir(destpath)
        loose_files = [
            f for f in glob(os.path.join(rootpath, "*.*"))
            if os.path.splitext(f)[1].lower() in self.match_extensions
        ]
        num_loose_files = len(loose_files)
        if num_loose_files == 0:
            return
        can_do_cleanup = messagebox.askyesno(
            title="Clean up directory?",
            message="""Move {num_loose_files} files into single directory?\nFiles in: {rootpath}\nNew folder: {destpath}\n\nFiles to move: {flist}""".format(flist=", ".join(loose_files[:30]), **locals())
        )
        if can_do_cleanup:
            for oldfile in loose_files:
                snip.filesystem.moveFileToDir(oldfile, destpath)

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
        self.generatePaths(newdir)

        self.undo.clear()

        # Double check recycle bin
        global trashdir
        if not os.path.isdir(trashdir):
            global trashed_files
            trashdir = mkdtemp(prefix="srt-")
            trashed_files = []
            print("Opened new trash directory as", trashdir)

        # Initialize data
        self.reloadDirContext()

        # Initialize images
        self.image_index = 0
        self.reloadImages()

        self.frame_sidebar.progbar_prog.configure(maximum=len(self.filepaths))

    def reloadDirContext(self):
        """Reload globs, keys, and context for our directory.
        """
        context = sum([glob(a) for a in self.contextglobs], [])
        self.folders_by_name = {baseFolderName(path.lower()): path for path in context}
        self.folder_names = list(self.folders_by_name.keys())  # Constant order
        self.keycache = {}
        self.populateContextKeyFrame()
        self.reloadImages()

    def reloadImages(self):
        """Reload filepaths, rescan for images.
        """
        print("Reloading, sorting")
        self.filepaths = self.sorter(sum([glob(a) for a in self.imageglobs], []))
        self.imageUpdate()

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
            traceback.print_exc()
            self.str_curfile.set(
                "Invalid key: {}".format(entry))
            return

        destination_dir = choice
        usubdir = os.path.join(destination_dir, "unsorted")
        if os.path.exists(usubdir):
            destination_dir = usubdir

        # (old_dir, file_name) = os.path.split(old_file_path)
        # spool.enqueueSeries([
        #     (lambda: snip.moveFileToDir(old_file_path, destination_dir)),
        #     (lambda: self.undo.append(
        #         lambda self: snip.moveFileToFile(os.path.join(destination_dir, file_name), old_file_path))),
        # ])

        (old_file_dir, old_file_name) = os.path.split(old_file_path)
        new_file_path = os.path.join(destination_dir, old_file_name)

        spool.enqueueSeries([
            (lambda: snip.filesystem.moveFileToFile(old_file_path, new_file_path)),
            (lambda: self.undo.append(
                lambda self: (
                    snip.filesystem.moveFileToFile(new_file_path, old_file_path),
                ))),
        ])

        # filemove(old_file_name, dst)
        self.filepaths.remove(old_file_path)
        # self.undo.append(lambda self: filemove(
        #     os.path.join(dst, file), old_file_name))

        # Clear field
        self.frame_sidebar.reFocusEntry()

        # If auto, pause to prevent error
        if self.frame_sidebar.aggressive.get():
            widget.bell()
            widget.config(state='disabled')
            widget.after(600, lambda: (widget.config(
                state='normal'), widget.delete(0, last=tk.END)))

        self.imageUpdate()

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

        fuzzy = self.frame_sidebar.fuzzy.get()

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
                print("Learning: {} : {}".format(entry, matches[0]))
            elif fuzzy:
                matches = [i for i in range(0, len(matchindices)) if matchindices[i] != -1]
                if len(matches) == 1:
                    self.keycache[entry] = matches[0]    # Learn.
                    print("Learning: {} : {}".format(entry, matches[0]))
            if indexOnly:
                return matches
            else:
                return [(self.folder_names[index], self.folders_by_name.get(self.folder_names[index])) for index in matches]

    def generatePaths(self, rootpath):
        """Generate imageglobs and contextglobs for a root path

        Args:
            rootpath (str): Root path to search
        """
        print("Generating paths for: {}".format(rootpath))
        # Pull loose images
        self.imageglobs = [
            os.path.join(rootpath, "*" + ext) for ext in self.match_extensions]

        print(self.imageglobs)

        subdirectory_unsorted = os.path.join(rootpath, "unsorted")

        if os.path.exists(subdirectory_unsorted):
            # Put images in same-level directories
            self.contextglobs = [
                os.path.join(rootpath, "*" + sep),
                os.path.join(rootpath, ".." + sep)
            ]

            # Pull images from unsorted too
            self.imageglobs += [
                os.path.join(subdirectory_unsorted, "*" + ext) for ext in self.match_extensions]

            self.promptLooseCleanup(rootpath, subdirectory_unsorted)

        else:
            # Put images in parent directories
            self.contextglobs = [
                os.path.join(rootpath, "..", "*" + sep),
                os.path.join(rootpath, "..", ".." + sep)
            ]
            rootpath = os.path.join(rootpath, "..")
        print(self.contextglobs)
        self.newFolderRoot = rootpath  # Where we make new folders

    # def backspace(self, event):
    #     if event.widget.get() == "":
    #         self.prevImage()

    # Backend updates

    def reSort(self):
        # self.reloadDirContext()
        self.canvas.itemconfig(self.image_on_canvas, state="hidden")
        self.update_idletasks()
        print("(Re)sorting")
        self.filepaths = self.sorter(self.filepaths)
        self.image_index = 0
        self.imageUpdate()
        self.canvas.itemconfig(self.image_on_canvas, state="normal")

    def nextImage(self, event=None):
        """Show the next image

        Args:
            event (optional): tk triggering event
        """
        self.image_index += 1
        self.imageUpdate()

    def prevImage(self, event=None):
        """Show the previous image

        Args:
            event (optional): tk triggering event
        """
        self.image_index -= 1
        self.imageUpdate()

    def imageUpdate(self, event=None):
        """Update the display to match the current image index.
        Image indexes wrap around here.
        """
        print("I: {}/{}".format(self.image_index, len(self.filepaths)))
        self.frame_sidebar.progbar_seek.configure(maximum=len(self.filepaths))
        self.frame_sidebar.var_progbar_seek.set(self.image_index + 1)
        self.frame_sidebar.var_progbar_prog.set(len(self.filepaths))

        if len(self.filepaths) == 0:
            self.image_index = 0
            self.str_curfile.set("No more images found!")
            self.canvas.itemconfig(self.image_on_canvas, image=None)
            return

        # Wraparound image indicies
        prev_index = self.image_index
        self.image_index = self.image_index % len(self.filepaths)
        if self.image_index != prev_index:
            print("Wrapped, reloading...")
            print("W: {}/{}".format(self.image_index, len(self.filepaths)))
            if self.frame_sidebar.auto_reload.get():
                self.reloadImages()

        print("F: {}/{}".format(self.image_index, len(self.filepaths)))
        filename = self.currentImagePath

        maxwidth = self.canvas.winfo_width()
        maxheight = self.canvas.winfo_height()
        # Let window load
        if maxwidth == maxheight == 1:
            return self.after(200, self.imageUpdate)

        try:
            self.curimg = self.makePhotoImage(filename, maxwidth, maxheight)
        except (OSError, SyntaxError, tk.TclError) as e:
            print("[{}] Bad image: ".format(e) + filename)
            traceback.print_exc()
            self.filepaths.remove(filename)
            return self.imageUpdate()

        self.canvas.itemconfig(self.image_on_canvas, image=self.curimg)
        self.labelFileName()
        self.update_idletasks()
        loom.thread(target=lambda: self.loadPhotoImage(maxwidth, maxheight))

    def loadPhotoImage(self, *args, **kwargs):
        try:
            self.makePhotoImage(
                self.filepaths[(self.image_index - 1) % len(self.filepaths)],
                *args,
                **kwargs
            )
            self.makePhotoImage(
                self.filepaths[(self.image_index + 1) % len(self.filepaths)],
                *args,
                **kwargs
            )
        except (MemoryError, tk.TclError, ZeroDivisionError):
            print(self.photoImageCache)
            print(hex(id(self.photoImageCache)))
            print(len(self.photoImageCache))
            self.photoImageCache.clear()
            # for loc in locals():
            #     print(loc, ":", locals().get(loc))
            raise

    def makePhotoImage(self, filename, maxwidth, maxheight, ALWAYS_RESIZE=True, stepsize=4):
        """Make a resized photoimage given a filepath

        Args:
            filename (str): Path to an image file
            maxwidth (TYPE): Maximum width of canvas
            maxheight (TYPE): Maximum height of canvas

        Returns:
            ImageTk.PhotoImage
        """
        # pilimg = Image.open(filename)
        pilimg = self.photoImageCache.get(filename)

        if not pilimg:
            (filename_, fileext) = os.path.splitext(filename)
            canResize = True

            try:
                if fileext.lower() in _IMAGEEXTS:
                    pilimg = Image.open(filename)
                elif fileext.lower() in _VIDEOEXTS:
                    capture = cv2.VideoCapture(filename)
                    capture.grab()
                    flag, frame = capture.retrieve()
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pilimg = Image.fromarray(frame)
                else:
                    raise OSError("Exception reading image")
            except OSError:
                pilimg = Image.open("fallback.png")

            imageIsTooBig = pilimg.width > maxwidth or pilimg.height > maxheight
            if (imageIsTooBig and canResize) or ALWAYS_RESIZE:
                ratio = min(maxwidth / pilimg.width, maxheight / pilimg.height)
                method = Image.ANTIALIAS

                if not imageIsTooBig:
                    stepratio = floor(ratio * stepsize) / stepsize
                    if stepratio != 0:
                        ratio = stepratio
                        method = Image.LINEAR
                    # else:
                    #     print("Warning: stepratio =", stepratio, "with ratio", ratio, "and stepsize", stepsize)
                try:
                    pilimg = pilimg.resize(
                        (int(pilimg.width * ratio), int(pilimg.height * ratio)), method)
                except OSError as e:
                    print("OS error resizing file", filename)
                    # loc = None
                    # for loc in locals():
                    #     print(loc, ":", locals().get(loc))
                    try:
                        return ImageTk.PhotoImage(pilimg)
                    except SyntaxError as e2:
                        print("Corrupt image")
                        raise
                    except (MemoryError, tk.TclError):
                        print("Corrupt image, I think?")
                        print(filename)
                        messagebox.showwarning("Bad image", traceback.format_exc())
                        self.filepaths.remove(filename)
                        self.imageUpdate()

            self.photoImageCache[filename] = pilimg
            loom.thread(target=self.pruneImageCache, name="pruneImageCache")
        return ImageTk.PhotoImage(pilimg)

    def pruneImageCache(self, max_memory_entries=30):
        while len(self.photoImageCache) > max_memory_entries:
            self.photoImageCache.pop(list(self.photoImageCache.keys())[0])
        assert len(self.photoImageCache) <= max_memory_entries

    # Disk action

    def keepImage(self, event=None):
        keepdir = os.path.join("keep", os.path.split(self.rootpath)[1])
        self.moveToFolder(new_folder_name=keepdir)

    def save_a_copy(self):
        newFileName = filedialog.asksaveasfilename(
            initialfile=os.path.basename(self.currentImagePath)
        )
        snip.filesystem.copyFileToFile(self.currentImagePath, newFileName)

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
        fileToDelete = self.currentImagePath
        confirmed = preconfirmed or messagebox.askyesno(
            "Confirm", "{}\nAre you sure you want to delete this file?\n(The file will be trashed, and semi-recoverable.)".format(fileToDelete))
        if confirmed:
            self.filepaths.remove(fileToDelete)
            trash(fileToDelete, undos=self.undo)
            self.photoImageCache.pop(fileToDelete)
            self.imageUpdate()

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

        try:
            # if os.path.exists(newFileName):
            #     raise FileExistsError()
            # print("{} -> {}".format(old_file_path, newFileName))
            (old_file_dir, old_file_name) = os.path.split(old_file_path)
            conflicting_file_path = os.path.join(old_file_dir, entry + os.path.splitext(old_file_path)[1])

            snip.filesystem.renameFileOnly(old_file_path, entry)
            # os.rename(old_file_path, newFileName)
        except FileExistsError as e:
            if self.frame_sidebar.confident.get():
                print("Renaming conflicting file", e.filename2)
                snip.filesystem.renameFileOnly(conflicting_file_path, entry + "_displaced")
                snip.filesystem.renameFileOnly(old_file_path, entry)
            else:
                traceback.print_exc()
        finally:
            self.undo.append(
                lambda s: snip.filesystem.renameFileOnly(
                    conflicting_file_path,
                    old_file_name
                ))

            self.photoImageCache.pop(old_file_path)

            if self.frame_sidebar.auto_reload.get():
                self.reloadImages()
            # self.nextImage()

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

            spool.enqueueSeries([
                (lambda: snip.filesystem.moveFileToDir(old_file_path, newdir)),
                (lambda: self.undo.append(
                    lambda self: (snip.filesystem.moveFileToFile(
                        os.path.join(newdir, old_filename), old_file_path))))
            ])

            self.photoImageCache.pop(old_file_path)
            # spool.enqueue(
            #     name="{} -> {}".format(old_file_path, newdir),
            #     target=filemove, args=(old_file_path, newdir,))
            # # doFileRename(old_file_path, newFileName,
            # #              confident=self.frame_sidebar.confident.get())
            # spool.enqueue(
            #     name="Push move undo",
            #     target=self.undo.append,
            #     args=(lambda self: doFileRename(
            #         os.path.join(newdir, os.path.split(old_file_path)[1]), old_file_path),
            #     )
            # )

            self.filepaths.remove(old_file_path)
            self.image_index -= 1
            self.nextImage()
        except Exception:
            traceback.print_exc()
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
        # print("doundo")
        if len(self.undo) == 0:
            return

        spool.finish(resume=True)

        op = self.undo.pop()
        op(self)
        # print("doneundo")
        if self.frame_sidebar.auto_reload.get():
            self.reloadImages()
        # print("imagereload done")
        self.imageUpdate()


def run_threaded():
    """Run the program with threading support
    """

    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("-r", "--root",
                        help="Root folder. Should contain folders, one of which can be named unsorted.")
        ap.add_argument(
            "-e", "--extensions", nargs='+', default=MATCHEXTS,
            help="Substrings in the path to penalize during file sorting.")
        args = ap.parse_args()

        spool.start()
        FileSorter(args.root, ["." + e for e in args.extensions])
    except (Exception, KeyboardInterrupt) as e:
        # Postmortem on uncaught exceptions
        traceback.print_exc()

    # Cleanup
    really_trash_files(trashed_files)
    # glob(os.path.join(trashdir, "*"), recursive=True):
    spool.finish()  # We must wait for previous jobs to finish

    # loom.threadWait(1, 1)


if __name__ == "__main__":
    run_threaded()
