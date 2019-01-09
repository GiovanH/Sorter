"""sort.py 
sort images

Attributes:
    ALWAYS_RESIZE (bool): Always fill image to screen
    COMPLETION_KEYS (list): Keys that signify completion
    FILL (TYPE): Tk shortcut for all sticky directions
    IMAGEEXTS (list): Valid file extensions for images
    WFILL (TYPE): Tk shortcut for wide sticky directions
"""

import tkinter as tk
from tkinter import ttk
import loom

from PIL import ImageTk, Image
from tkinter import filedialog, messagebox

import shutil
from glob import glob
import os
from os.path import sep
from send2trash import send2trash

import traceback
import errno
import argparse
from math import floor


FILL = tk.N + tk.S + tk.E + tk.W
WFILL = tk.E + tk.W

ALWAYS_RESIZE = True
IMAGEEXTS = ["png", "jpg", "gif", "bmp", "jpeg", "tif"]

COMPLETION_KEYS = [32, 8]


def makeMappings(lst):
    """Make shortkey mappings from a list of paths
    
    Args:
        lst (list<str>): A list of folder paths
    
    Returns:
        dict: {shortkey: path for path in lst}
    """
    vals = [i.split(sep)[-2].lower() for i in lst]
    map_prime = {vals[i]: lst[i] for i in range(0, len(lst))}
    return map_prime


def doFileRename(oldFileName, newFileName, confident=False):
    """Perform a file rename operation, possibly failing.
    
    Args:
        oldFileName (str): Complete path to old file
        newFileName (str): Complete path to new file
        confident (bool, optional): Displace existing images (not clobber)
    """
    try:
        print("{} -> {}".format(oldFileName, newFileName))
        os.rename(oldFileName, newFileName)
    except FileExistsError as e:
        if confident:
            print("Renaming conflicting file", e.filename2)
            "DISPLACED_"
            (folder, file) = os.path.split(e.filename2)
            doFileRename(e.filename2, os.path.join(folder, "DISPLACED_" + file))
            os.rename(oldFileName, newFileName)


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


def filemove(src, dst):
    """Move a file
    
    Args:
        src (str): Source path
        dst (str): Destination path
    """
    print("{} -> {}".format(src, dst))
    try:
        shutil.move(src, dst)
    except shutil.Error as e:
        print(e.errno, errno.EEXIST, e.errno == errno.EEXIST)
        traceback.print_exc()


def trash(file):
    """Args:
        file (str): Path to trash
    """
    print("Trashing {}".format(file))
    send2trash(file)
    print("Trashed {}".format(file))


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
        keymap (TYPE): Description
        keymap_keys (TYPE): Description
        lab_curfile (TYPE): Description
        rootpath (TYPE): Description
        str_context (tk.Stringvar): Description
        str_curfile (tk.Stringvar): Description
        undo (list): Stack of functions to process via ctrl+z
    """
    
    def __init__(self, rootpath, *args, **kwargs):
        """File sorter main window
        
        Passthrough to tk.Tk
        Args:
            rootpath (TYPE): Description
            *args: Description
            **kwargs: Description
        """
        super(FileSorter, self).__init__(*args, **kwargs)

        self.image_index = 0
        self.str_context = tk.StringVar()
        self.undo = []

        self.initwindow()

        self.openDir(rootpath)

        self.bind("<Control-z>", self.doUndo)
        self.bind("<Delete>", self.delete)
        self.bind("<Right>", self.nextImage)
        self.bind("<Left>", self.prevImage)

        self.mainloop()
    
    def initwindow(self):
        """Initialize widgets for the window
        """

        # # Header stuff # #
        # current filename label
        self.str_curfile = tk.StringVar(value="NaN")
        self.lab_curfile = tk.Label(textvariable=self.str_curfile)
        self.lab_curfile.grid(row=0, column=0, columnspan=2)

        # Canvas stuff
        self.canvas = tk.Canvas()
        self.canvas.grid(column=0, row=1, sticky=FILL)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, minsize=160)
        self.rowconfigure(1, weight=1)

        # set first image on canvas, an ImageTk.PhotoImage
        self.image_on_canvas = self.canvas.create_image(
            0, 0, anchor=tk.N + tk.W)

        self.frame_sidebar = SidebarFrame(self)
        self.frame_sidebar.config(bd=3, relief=tk.RIDGE)
        self.frame_sidebar.grid(row=1, column=1, sticky="NSEW")

    def openDir(self, newdir=None):
        """Open a new directory and prepare window
        
        Args:
            newdir (str, optional): Path of new directory. If blank, prompts user.
        """
        if not newdir:
            newdir = os.path.realpath(filedialog.askdirectory())
            if newdir == '':
                os.abort()
        self.generatePaths(newdir)

        # Initialize data
        self.reloadDirContext()
        self.reloadImages()

        self.undo = []
        # Initialize images
        self.nextImage()

    def labelFileName(self):
        """Generate a user-friendly filename for the header
        """
        prettyname = os.path.split(self.filepaths[self.image_index])[1]
        self.str_curfile.set(prettyname)

    # Generators and logic
    def getBestFolder(self, entry, fast=False):
        """Wrapper around getBestFolders to find a single best folder.
        
        Args:
            entry (str): Shortcode, search term
            fast (bool, optional): Use fast algorithm
        
        Returns:
            TYPE: Description
        
        Raises:
            EnvironmentError: If there is more than one acceptable folder
        """
        gbf = self.getBestFolders(entry, fast=fast)
        if len(gbf) == 1:
            return self.keymap[self.keymap_keys[gbf[0]]]
        else:
            raise EnvironmentError("Ambiguous folder selected, could be any of: {}".format(gbf))

    def getBestFolders(self, entry, fast=False):
        """Finds folders that match the search term
        
        Args:
            entry (str): Shortcode, search term
            fast (bool, optional): Use fast algorithm
        
        Returns:
            list<int>: List of valid match INDEXES. Indexes reference self.keymap_keys
        """
        if self.keycache.get(entry) is not None:
            return [self.keycache.get(entry)]

        if entry in self.keymap_keys:
            return [self.keymap_keys.index(entry)]

        if entry != "":
            keys = self.keymap_keys
            # There is not a perfect mapping
            matchindices = [k.find(entry) for k in keys]
            matches = [i for i in range(0, len(matchindices)) if matchindices[i] == 0]
            if len(matches) == 1:
                self.keycache[entry] = matches[0]    # Learn.
                print("Learning: {} : {}".format(entry, matches[0]))
            return matches

    def generateContextKey(self):
        """Generate and refresh the sidebar listbox
        """
        self.frame_sidebar.listbox_context.configure(state=tk.NORMAL)
        self.frame_sidebar.listbox_context.delete(0, self.frame_sidebar.listbox_context.size())
        for val in self.keymap_keys:
            self.frame_sidebar.listbox_context.insert(
                tk.END, "{}".format(val[0:15]))
        # self.frame_sidebar.listbox_context.configure(state=tk.DISABLED)

    def highlightListboxItems(self, matches):
        """Highlight specific items in the listbox
        
        Args:
            matches (list): List of indexes to highlight
        """
        self.frame_sidebar.listbox_context.configure(state=tk.NORMAL)
        self.frame_sidebar.listbox_context.selection_clear(0, tk.END)
        if len(matches) == 0:
            self.frame_sidebar.listbox_context.configure(state=tk.DISABLED)
            return
        for index in matches:
            self.frame_sidebar.listbox_context.selection_set(index)

    def generatePaths(self, rootpath):
        """Generate imageglobs and contextglobs for a root path
        
        Args:
            rootpath (str): Root path to search
        """
        print("Generating paths for: {}".format(rootpath))
        # Pull loose images
        self.imageglobs = [            
            os.path.join(rootpath, "*." + ext) for ext in IMAGEEXTS]

        if os.path.exists(os.path.join(rootpath, "unsorted")):
            # Put images in same-level directories
            self.contextglobs = [
                os.path.join(rootpath, "*" + sep),
                os.path.join(rootpath, ".." + sep)
            ]

            # Pull images from unsorted too
            self.imageglobs += [
                os.path.join(rootpath, "unsorted", "*." + ext) for ext in IMAGEEXTS]
        else:
            # Put images in parent directories
            self.contextglobs = [
                os.path.join(rootpath, "..", "*" + sep),
                os.path.join(rootpath, "..", ".." + sep)
            ]
            rootpath = os.path.join(rootpath, "..")
        self.rootpath = rootpath  # Where we make new folders

    # def backspace(self, event):
    #     if event.widget.get() == "":
    #         self.prevImage()

    # Backend updates

    def reloadDirContext(self):
        """Reload globs, keys, and context for our directory.
        """
        self.context = sum([glob(a) for a in self.contextglobs], [])
        self.keymap = makeMappings(self.context)
        self.keymap_keys = list(self.keymap.keys())  # Constant order
        self.keycache = {}
        self.generateContextKey()

    def reloadImages(self):
        """Reload filepaths, rescan for images.
        """
        self.filepaths = sum([glob(a) for a in self.imageglobs], [])

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

    def imageUpdate(self):
        """Update the display to match the current image index. 
        Image indexes wrap around here.
        """

        # Wraparound image indicies
        if self.image_index < 0:
            self.image_index = len(self.filepaths) - 1
        if self.image_index >= len(self.filepaths):
            self.reloadImages()
            self.image_index = 0

        if len(self.filepaths) == 0:
            return self.str_curfile.set("No more images found!")

        filename = self.filepaths[self.image_index]

        maxwidth = self.canvas.winfo_width()
        maxheight = self.canvas.winfo_height()
        # Let window load
        if maxwidth == maxheight == 1:
            return self.canvas.after(100, self.imageUpdate)

        try:
            self.curimg = self.makePhotoImage(filename, maxwidth, maxheight)
        except OSError as e:
            print("[OS error] Bad image: " + filename)
            traceback.print_exc()
            self.filepaths.remove(filename)
            return self.imageUpdate()
        except tk.TclError as e:
            print("[tk error] Bad image: " + filename)
            traceback.print_exc()
            self.filepaths.remove(filename)
            return self.imageUpdate()

        self.canvas.itemconfig(self.image_on_canvas, image=self.curimg)
        self.labelFileName()

    def makePhotoImage(self, filename, maxwidth, maxheight):
        """Make a resized photoimage given a filepath
        
        Args:
            filename (str): Path to an image file
            maxwidth (TYPE): Maximum width of canvas
            maxheight (TYPE): Maximum height of canvas
        
        Returns:
            ImageTk.PhotoImage
        """
        pilimg = Image.open(filename)
        self.curimg = ImageTk.PhotoImage(pilimg)

        width = self.curimg.width()
        height = self.curimg.height()
        imageIsTooBig = width > maxwidth or height > maxheight
        if (imageIsTooBig or ALWAYS_RESIZE):
            ratio = min(maxwidth / width, maxheight / height)
            method = Image.ANTIALIAS
            if ratio > 1:
                ratio = floor(ratio)
                method = Image.LINEAR
            pilimg = Image.open(filename).resize(
                (int(width * ratio), int(height * ratio)), method)

        return ImageTk.PhotoImage(pilimg)

    # Disk action

    def submit(self, event=False, entry=""):
        """Processing when the user submits the "move" entry
        
        Args:
            event (bool, optional): Tk triggerinv event.
            entry (str, optional): Text of entry, if no triggering event.
        """

        oldFileName = self.filepaths[self.image_index]
        if event:
            entry = event.widget.get()
            if entry == "":
                self.nextImage()
                return
            widget = event.widget
        else:
            widget = self.frame_sidebar.entry
        try:
            choice = self.getBestFolder(entry)
        except EnvironmentError:
            traceback.print_exc()
            self.str_curfile.set(
                "Invalid key: {}".format(entry))
            return
        dst = choice
        usubdir = os.path.join(dst, "unsorted")
        if os.path.exists(usubdir):
            dst = usubdir
        filemove(oldFileName, dst)
        (folder, file) = os.path.split(oldFileName)
        self.filepaths.remove(oldFileName)
        self.undo.append(lambda self: filemove(
            os.path.join(dst, file), oldFileName))

        # Clear field
        widget.delete(0, last=tk.END)

        # If auto, pause to prevent error
        if self.frame_sidebar.aggressive.get():
            widget.config(state='disabled')
            widget.after(600, lambda: (widget.config(
                state='normal'), widget.delete(0, last=tk.END)))

        self.imageUpdate()

    def delete(self, event):
        """Delete the currently selected file
        
        Args:
            event: Tk triggering event
        """
        fileToDelete = self.filepaths[self.image_index]
        confirmed = messagebox.askyesno(
            "Confirm", "{}\nAre you sure you want to delete this file?\n(The file will be trashed, and semi-recoverable.)".format(fileToDelete))
        if confirmed:
            loom.thread(
                name="rm {}".format(fileToDelete),
                target=trash, args=(fileToDelete,))
            # send2trash(fileToDelete)
            self.filepaths.remove(fileToDelete)
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
        oldFileName = self.filepaths[self.image_index]
        (folder, file) = os.path.split(oldFileName)
        extension = file.split(".")[-1]
        newFileName = os.path.join(folder, entry + "." + extension)
        # newFileName = "{}{}{}.{}".format(
        #     sep.join(oldFileName.split(sep)[:-1]),
        #     sep,
        #     entry,
        # )
        loom.thread(
            name="{} -> {}".format(oldFileName, newFileName),
            target=doFileRename, args=(oldFileName, newFileName,), kwargs={'confident': (self.frame_sidebar.confident.get() == 1)})
        doFileRename(oldFileName, newFileName,
                     confident=self.frame_sidebar.confident.get())
        self.undo.append(lambda self: doFileRename(
            newFileName, oldFileName, confident=self.frame_sidebar.confident.get()))
        self.reloadImages()
        self.imageUpdate()

        # Clear field
        event.widget.delete(0, last=tk.END)

    def newfolder(self, event):
        """Create a new folder
        
        Args:
            event (TYPE): Tk triggering event
        """
        newfoldername = event.widget.get()
        oldFileName = self.filepaths[self.image_index]
        if newfoldername == "":
            self.nextImage()
            return
        try:
            newdir = os.path.join(self.rootpath, newfoldername)
            os.mkdir(newdir)
            self.reloadDirContext()
            filemove(oldFileName, newdir)
            self.filepaths.remove(oldFileName)
            self.image_index -= 1
            self.nextImage()
        except Exception:
            traceback.print_exc()

        # Clear field
        event.widget.delete(0, last=tk.END)

    def doUndo(self, event):
        """Process an undo operation, handling the stack. 
        
        Args:
            event: Tk triggering event
        """
        if len(self.undo) == 0:
            return
        op = self.undo.pop()
        op(self)
        self.reloadImages()
        self.imageUpdate()


class SidebarFrame(tk.Frame):

    """Frame that manages the sidebar and user input
    """
    
    # Init and window management

    def __init__(self, parent, *args, **kwargs):
        """Args:
            parent (tk): Tk parent widget
            *args: Passthrough
            **kwargs: Passthrough
        """
        tk.Frame.__init__(self, *args, **kwargs)

        linkedFunctions = [
            "getBestFolders",
            "getBestFolder",
            "labelFileName",
            "str_curfile",
            "nextImage",
            "prevImage",
            "openDir",
            "submit",
            "newfolder",
            "dorename",
            "imageUpdate",
            "reloadDirContext",
            "highlightListboxItems"
        ]
        for f in linkedFunctions:
            self.__setattr__(f, parent.__getattribute__(f))

        # Initialize window
        self.initwindow()

    def initwindow(self):
        """Initialize widgets
        """
        inOrderRow = 0

        def rowInOrder():
            """Helper function to increment in-order elements"""
            nonlocal inOrderRow
            inOrderRow += 1
            return inOrderRow

        btn_ref = ttk.Button(self, text="Open", takefocus=False, command=self.openDir)
        btn_ref.grid(row=rowInOrder(), sticky=tk.W)
        btn_ref = ttk.Button(self, text="Refresh", takefocus=False, command=(
            lambda: (self.reloadDirContext(), self.imageUpdate()))
        )
        btn_ref.grid(row=inOrderRow, sticky=tk.E)
        
        # self.btn_clear = ttk.Button(
        #     text="Clear", takefocus=False, command=(
        #         lambda: (self.generatePaths("/dev/null"), self.reloadDirContext(), self.imageUpdate()))
        # )
        # self.btn_clear.grid(row=inOrderRow, sticky=tk.E)

        btn_back = ttk.Button(self, text="Prev", takefocus=False, command=self.prevImage)
        btn_back.grid(row=rowInOrder(), sticky=tk.W)
        btn_skip = ttk.Button(self, text="Skip", takefocus=False, command=self.nextImage)
        btn_skip.grid(row=inOrderRow, sticky=tk.E)

        def highlightEntry(parent):
            """Quick factory for entries that highlight"""
            return tk.Entry(parent, highlightthickness=2, takefocus=True)

        # Entry text field
        lab_context_label = ttk.Label(self, text="Move to folder ID:")
        lab_context_label.grid(row=rowInOrder())

        self.entry = highlightEntry(self)
        self.entry.bind("<Return>", self.submit)
        self.entry.bind("<KeyRelease>", self.processEntryInput)
        self.entry.grid(row=rowInOrder(), sticky="WE")
        self.entry.focus()

        # New folder entry
        lab_newfolder = ttk.Label(self, text="Move to new folder:")
        lab_newfolder.grid(row=rowInOrder())

        self.entry_newfolder = highlightEntry(self)
        self.entry_newfolder.bind("<Return>", self.newfolder)
        self.entry_newfolder.grid(row=rowInOrder(), sticky="WE")

        # Setting checkboxes
        self.aggressive = tk.BooleanVar()
        check_aggressive = tk.Checkbutton(
            self, text="Auto", takefocus=False, variable=self.aggressive)
        check_aggressive.grid(row=rowInOrder(), sticky=tk.W)

        self.confident = tk.BooleanVar()
        check_confident = tk.Checkbutton(
            self, text="Displace", takefocus=False, variable=self.confident)
        check_confident.grid(row=inOrderRow, sticky=tk.E)

        # Rename
        lab_rename = ttk.Label(self, text="Rename")
        lab_rename.grid(row=rowInOrder())

        self.entry_rename = highlightEntry(self)
        self.entry_rename.grid(row=rowInOrder(), sticky="WE")
        self.entry_rename.bind("<Return>", self.dorename)

        # context keys
        lab_context_label = ttk.Label(self, text="Folder IDs:")
        lab_context_label.grid(row=rowInOrder())

        # self.str_context = tk.StringVar()
        self.listbox_context = tk.Listbox(
            self, state=tk.DISABLED, takefocus=False, relief=tk.GROOVE)
        self.listbox_context.grid(row=rowInOrder(), sticky=FILL)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(inOrderRow, weight=1)

    def processEntryInput(self, event):
        """Process entry input, handling element styling and possible automatic submission.
        
        Args:
            event (TYPE): Tk entry event
        """
        GOOD = "#AAFFAA"
        BAD = "#FFAAAA"
        NORMAL = "#FFFFFF"

        fieldGet = event.widget.get()
        if event.keycode == 32:
            fieldGet = fieldGet[:-1]  # Delete space character

        if fieldGet == "":
            event.widget.configure(bg=NORMAL)
            self.highlightListboxItems([])
            return
        bestFolders = self.getBestFolders(fieldGet)
        self.highlightListboxItems(bestFolders)
        if len(bestFolders) == 1:
            self.str_curfile.set(self.getBestFolder(fieldGet))
            event.widget.configure(bg=GOOD)
            if self.aggressive.get():
                self.submit(entry=fieldGet)
        else:
            self.labelFileName()
            event.widget.configure(bg=BAD)


def run_threaded():
    """Run the program with threading support
    """
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("-r", "--root",
                        help="Root folder. Should contain folders, one of which is named unsorted.")
        args = ap.parse_args()

        FileSorter(args.root)
    except (Exception, KeyboardInterrupt) as e:
        # Postmortem on uncaught exceptions
        traceback.print_exc()

    # Cleanup
    loom.threadWait(1, 1)


if __name__ == "__main__":
    run_threaded()
