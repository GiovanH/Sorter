import tkinter as tk
from glob import glob
import argparse
import shutil
import os
import traceback
import errno
from PIL import ImageTk, Image
from tkinter import filedialog
from math import floor
from os.path import sep
from tkinter import messagebox
from send2trash import send2trash


def nop(self):
    return None


"""
TODO:
Backend:

Frontend:
Resize image to frame
Maybe a landscape layout to maximize screen space?
"""

FILL = tk.N + tk.S + tk.E + tk.W
WFILL = tk.E + tk.W

ALWAYS_RESIZE = True
IMAGEEXTS = ["png", "jpg", "gif", "bmp", "jpeg", "tif"]


def makeMappings(lst):
    vals = [i.split(sep)[-2].lower() for i in lst]
    map_prime = {vals[i]: lst[i] for i in range(0, len(lst))}
    return map_prime


def doFileRename(oldFileName, newFileName, confident=False):
    try:
        print("{} -> {}".format(oldFileName, newFileName))
        os.rename(oldFileName, newFileName)
    except FileExistsError as e:
        if confident:
            print("Renaming conflicting file", e.filename2)
            "DISPLACED_"
            bits = e.filename2.split(sep)
            doFileRename(e.filename2, sep.join(bits[:-1]) +
                         "{}DISPLACED_".format(sep) + bits[-1])
            os.rename(oldFileName, newFileName)


def imageSize(filename):
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
    print("{} -> {}".format(src, dst))
    try:
        shutil.move(src, dst)
    except shutil.Error as e:
        print(e.errno, errno.EEXIST, e.errno == errno.EEXIST)
        traceback.print_exc()


class FileSorter():

    # Init and window management

    def __init__(self, Tk, rootpath):

        self.image_index = -1
        self.str_context = tk.StringVar()
        self.undo = []

        # Store arguments.
        self.main = Tk

        if rootpath is None:
            rootpath = filedialog.askdirectory()

        if rootpath == '':
            os.abort()
        # Validate arguments
        self.generatePaths(rootpath.replace("/", sep))

        # Initialize window
        self.initwindow(Tk)

        # Initialize data
        self.reloadDirContext()
        self.reloadImages()

        # Initialize images
        self.nextImage()
        self.imageUpdate()

    def initwindow(self, main):
        top = self.main.winfo_toplevel()
        top.bind("<Control-z>", self.doUndo)
        top.bind("<Delete>", self.delete)
        top.bind("<Right>", self.nextImage)
        top.bind("<Left>", self.prevImage)

        columns = 2
        inOrderList = [2 for i in range(0, columns)]
        height = 0

        # Helper function to increment in-order elements
        def rowInOrder(col):
            nonlocal height
            inOrderList[col] += 1
            height = max(inOrderList)
            return inOrderList[col]

        # # Header stuff # #
        # current filename label
        self.str_curfile = tk.StringVar(value="NaN")
        self.lab_curfile = tk.Label(main, textvariable=self.str_curfile)
        self.lab_curfile.grid(row=0, column=0, columnspan=2)

        # # Sidebar stuff # #
        # Backer
        # self.canvas_gui = tk.Canvas(main)
        # self.canvas_gui.grid(row=1, column=0, rowspan=4, sticky=FILL)

        # Navigation buttons
        # self.lab_context_label = tk.Label(main, text="Navigation")
        # self.lab_context_label.grid(row=rowInOrder(1), sticky=tk.W, column=1)
        self.btn_ref = tk.Button(
            main, text="Open", takefocus=False, command=self.openDir)
        self.btn_ref.grid(row=rowInOrder(1), column=1, sticky=tk.W)
        self.btn_ref = tk.Button(
            main, text="Refresh", takefocus=False, command=(
                lambda: (self.reloadDirContext(), self.imageUpdate()))
        )
        self.btn_ref.grid(row=inOrderList[1], column=1)

        self.btn_skip = tk.Button(
            main, text="Skip", takefocus=False, command=self.nextImage)
        self.btn_skip.grid(row=rowInOrder(1), column=1, sticky=tk.E)
        self.btn_back = tk.Button(
            main, text="Prev", takefocus=False, command=self.prevImage)
        self.btn_back.grid(row=inOrderList[1], column=1, sticky=tk.W)

        def highlightEntry():
            return tk.Entry(main, highlightthickness=2)

        # Entry text field
        self.lab_context_label = tk.Label(
            main, text="Move to folder ID:")
        self.lab_context_label.grid(row=rowInOrder(1), column=1, sticky=tk.W)

        self.entry = highlightEntry()
        self.entry.bind("<Return>", self.submit)
        self.entry.bind("<BackSpace>", self.backspace)
        self.entry.bind("<KeyRelease>", self.validateCommand)
        self.entry.grid(row=rowInOrder(1), column=1)

        # New folder entry
        self.lab_newfolder = tk.Label(
            main, text="Move to new folder:")
        self.lab_newfolder.grid(row=rowInOrder(1), column=1)

        self.entry_newfolder = highlightEntry()
        self.entry_newfolder.bind("<Return>", self.newfolder)
        self.entry_newfolder.grid(row=rowInOrder(1), column=1)

        # Rename
        self.lab_rename = tk.Label(main, text="Rename")
        self.lab_rename.grid(row=rowInOrder(1), column=1, sticky=tk.W)

        self.entry_rename = highlightEntry()
        self.entry_rename.grid(row=rowInOrder(1), column=1)
        self.entry_rename.bind("<Return>", self.dorename)

        # Setting checkboxes
        self.aggressive = tk.IntVar()
        self.check_aggressive = tk.Checkbutton(
            main, text="Auto", variable=self.aggressive)
        self.check_aggressive.grid(row=rowInOrder(1), column=1, sticky=tk.W)

        self.confident = tk.IntVar()
        self.check_confident = tk.Checkbutton(
            main, text="Displace", variable=self.confident)
        self.check_confident.grid(row=inOrderList[1], column=1, sticky=tk.E)

        # context keys
        self.lab_context_label = tk.Label(
            main, text="Folder IDs:")
        self.lab_context_label.grid(row=rowInOrder(1), column=1)

        # self.str_context = tk.StringVar()
        contextRow = rowInOrder(1)
        self.listbox_context = tk.Listbox(
            main, state=tk.DISABLED, takefocus=False, disabledforeground=self.lab_curfile.cget('fg'), relief=tk.GROOVE)
        self.listbox_context.grid(row=contextRow, column=1, sticky=FILL)
        top.rowconfigure(contextRow, weight=1)

        # Canvas stuff
        # canvas for image
        self.canvas = tk.Canvas(main)  # , bg="#AA0001"
        self.canvas.grid(row=1, column=0, rowspan=height, sticky=FILL)

        # Allow smart grid resizing for the canvas cell
        # top.rowconfigure(1, weight=1)
        top.columnconfigure(0, weight=1)

        # set first image on canvas, an ImageTk.PhotoImage
        self.image_on_canvas = self.canvas.create_image(
            0, 0, anchor=tk.N + tk.W)

    def openDir(self):
        newdir = filedialog.askdirectory().replace("/", sep)
        if newdir == '':
            return
        self.generatePaths(newdir)

        # Initialize data
        self.reloadDirContext()
        self.reloadImages()

        self.undo = []
        # Initialize images
        self.nextImage()

    def labelFileName(self):
        prettyname = self.filepaths[self.image_index].split(sep)[-1]
        # prettyname = self.filelist[self.image_index][0]
        self.str_curfile.set(prettyname)

    # Generators and logic

    def getBestFolder(self, entry, fast=False):
        try:
            return self.keymap[entry]
        except KeyError:
            if entry != "":
                keys = list(self.keymap.keys())
                # There is not a perfect mapping
                matches = [k.find(entry) for k in keys]
                if matches.count(0) == 1:
                    return self.keymap[keys[matches.index(0)]]
            raise EnvironmentError("Ambiguous folder selected")

    def generateContextKey(self, context, map_):
        self.listbox_context.configure(state=tk.NORMAL)
        self.listbox_context.delete(0, self.listbox_context.size())
        map_prime = {map_[key]: key for key in map_.keys()}
        for val in context:
            self.listbox_context.insert(
                tk.END, "{}".format(map_prime[val][0:15]))
        self.listbox_context.configure(state=tk.DISABLED)

    def generatePaths(self, rootpath):
        print("Generating paths for: {}".format(rootpath))
        if os.path.exists("{}{sep}unsorted".format(rootpath, sep=sep)):
            # Pull images from unsorted
            self.imagefoldername = "unsorted"
            self.imageglobs = [
                "{}{sep}unsorted{sep}*.{}".format(rootpath, ext, sep=sep) for ext in IMAGEEXTS]
            # Put images in same-level directories
            self.contextglobs = [
                '{}{sep}*{sep}'.format(rootpath, sep=sep),
                '{}{sep}..{sep}'.format(rootpath, sep=sep)
            ]
        else:
            # Pull loose images
            self.imageglobs = [
                "{}{sep}*.{}".format(rootpath, ext, sep=sep) for ext in IMAGEEXTS]
            # Put images in parent directories
            self.contextglobs = [
                '{}{sep}..{sep}*{sep}'.format(rootpath, sep=sep),
                '{}{sep}..{sep}..{sep}'.format(rootpath, sep=sep)
            ]
            rootpath += "{sep}..{sep}".format(sep=sep)
        self.rootpath = rootpath  # Where we make new folders

    def validateCommand(self, event):
        GOOD = "#AAFFAA"
        BAD = "#FFAAAA"
        NORMAL = "#FFFFFF"
        if event.widget.get() == "":
            event.widget.configure(bg=NORMAL)
            return
        try:
            self.str_curfile.set(
                self.getBestFolder(event.widget.get()))
            event.widget.configure(bg=GOOD)
            if self.aggressive.get():
                self.submit(entry=self.entry.get())
        except OSError:
            self.labelFileName()
            event.widget.configure(bg=BAD)

    def backspace(self, event):
        if event.widget.get() == "":
            self.prevImage()

    # Backend updates

    def reloadDirContext(self):
        self.context = sum([glob(a) for a in self.contextglobs], [])
        print(self.context)
        self.keymap = makeMappings(self.context)
        self.generateContextKey(self.context, self.keymap)

    def reloadImages(self):
        # self.filepaths = sorted(
        #     sum([glob(a) for a in self.imageglobs], []), key=imageSize)
        self.filepaths = sum([glob(a) for a in self.imageglobs], [])

    def nextImage(self, event=None):
        # Queue the next image
        self.image_index += 1
        self.imageUpdate()

    def prevImage(self, event=None):
        self.image_index -= 1
        self.imageUpdate()

    def imageUpdate(self):
        # Let window load

        # Wraparound
        if self.image_index < 0:
            self.image_index = len(self.filepaths) - 1
        if self.image_index >= len(self.filepaths):
            self.reloadImages()
            self.image_index = 0

        if len(self.filepaths) == 0:
            self.str_curfile.set("No more images found!")
        else:
            filename = self.filepaths[self.image_index]
            print(filename)
            try:
                self.curimg = self.makePhotoImage(filename)
            except OSError as e:
                print("[OS error] Bad image: " + filename)
                traceback.print_exc()
                self.filepaths.remove(filename)
                self.imageUpdate()
                return
            except tk.TclError as e:
                print("[tk error] Bad image: " + filename)
                traceback.print_exc()
                self.filepaths.remove(filename)
                self.imageUpdate()
                return

            self.canvas.itemconfig(self.image_on_canvas, image=self.curimg)
            self.labelFileName()

    def makePhotoImage(self, filename):
        maxwidth = self.canvas.winfo_width()
        maxheight = self.canvas.winfo_height()

        pilimg = Image.open(filename)
        self.curimg = ImageTk.PhotoImage(pilimg)

        width = self.curimg.width()
        height = self.curimg.height()
        imageIsTooBig = width > maxwidth or height > maxheight
        if (imageIsTooBig or ALWAYS_RESIZE) and not maxwidth == maxheight == 1:
            # print("Image {} is too big. [{}x{} image in {}x{} canvas]".format(
            #     filename,
            #     width,
            #     height,
            #     maxwidth,
            #     maxheight
            # ))
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
        oldFileName = self.filepaths[self.image_index]
        if event:
            entry = event.widget.get()
            if entry == "":
                self.nextImage()
                return
            widget = event.widget
        else:
            widget = self.entry
        try:
            choice = self.getBestFolder(entry)
        except EnvironmentError:
            traceback.print_exc()
            # os.mkdir(entry)
            # self.reloadDirContext(self.rootpath)
            self.str_curfile.set(
                "Invalid key: {}".format(entry))
            return
            # choice = self.context[atoi[self.entry.get()]]
        # extension = oldFileName.split('.')[-1]
        dst = choice
        usubdir = dst + "unsorted{}".format(sep)
        if os.path.exists(usubdir):
            dst = usubdir
        filemove(oldFileName, dst)
        self.filepaths.remove(oldFileName)
        self.undo.append(lambda self: filemove(
            dst + oldFileName.split(sep)[-1], oldFileName))

        # Clear field
        widget.delete(0, last=tk.END)
        self.imageUpdate()

    def delete(self, event):
        fileToDelete = self.filepaths[self.image_index]
        confirmed = messagebox.askyesno(
            "Confirm", "{}\nAre you sure you want to delete this file?\n(The file will be trashed, and semi-recoverable.)".format(fileToDelete))
        if confirmed:
            send2trash(fileToDelete)
            self.filepaths.remove(fileToDelete)
            self.imageUpdate()

    def dorename(self, event):
        entry = event.widget.get()
        if entry == "":
            self.nextImage()
            return
        oldFileName = self.filepaths[self.image_index]
        newFileName = "{}{}{}.{}".format(
            sep.join(oldFileName.split(sep)[:-1]),
            sep,
            entry,
            oldFileName.split(".")[-1]
        )
        doFileRename(oldFileName, newFileName,
                     confident=(self.confident.get() == 1))
        self.undo.append(lambda self: doFileRename(
            newFileName, oldFileName, confident=(self.confident.get() == 1)))
        self.reloadImages()
        self.imageUpdate()

        # Clear field
        event.widget.delete(0, last=tk.END)

    def newfolder(self, event):
        newfoldername = event.widget.get()
        oldFileName = self.filepaths[self.image_index]
        if newfoldername == "":
            self.nextImage()
            return
        try:
            newdir = "{}/{}".format(self.rootpath, newfoldername)
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
        if len(self.undo) == 0:
            return
        op = self.undo.pop()
        op(self)
        self.image_index -= 1
        self.reloadImages()
        self.imageUpdate()


ap = argparse.ArgumentParser()
ap.add_argument("-r", "--root",
                help="Root folder. Should contain folders, one of which is named unsorted.")
args = ap.parse_args()


Tk = tk.Tk()
FileSorter(Tk, args.root)
Tk.mainloop()
