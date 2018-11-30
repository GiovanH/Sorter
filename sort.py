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
    vals = [i.split('\\')[-2].lower() for i in lst]
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
            bits = e.filename2.split("\\")
            doFileRename(e.filename2, "\\".join(bits[:-1]) +
                         "\\DISPLACED_" + bits[-1])
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


class MainWindow():

    def __init__(self, Tk, rootpath):

        self.image_index = -1
        self.str_context = tk.StringVar()

        # Store arguments.
        self.main = Tk

        if rootpath is None:
            rootpath = filedialog.askdirectory().replace("/", "\\")

        if rootpath == '':
            os.abort()
        # Validate arguments
        self.generatePaths(rootpath)

        # Initialize window
        self.initwindow(Tk)

        # Initialize data
        self.reloadDirContext()
        self.reloadImages()

        # Initialize images
        self.nextImage()
        self.imageUpdate()

    def generateContextKey(self, context, map_):
        self.listbox_context.configure(state=tk.NORMAL)
        self.listbox_context.delete(0, self.listbox_context.size())
        map_prime = {map_[key]: key for key in map_.keys()}
        for val in context:
            self.listbox_context.insert(
                tk.END, "{}".format(map_prime[val][0:15]))
        self.listbox_context.configure(state=tk.DISABLED)

    def labelFileName(self):
        prettyname = self.filepaths[self.image_index].split("\\")[-1]
        # prettyname = self.filelist[self.image_index][0]
        self.str_curfile.set(prettyname)

    def openDir(self):
        newdir = filedialog.askdirectory().replace("/", "\\")
        if newdir == '':
            return
        self.generatePaths(newdir)

        # Initialize data
        self.reloadDirContext()
        self.reloadImages()

        self.undo = nop
        # Initialize images
        self.nextImage()

    def initwindow(self, main):
        top = self.main.winfo_toplevel()
        top.bind("<Control-z>", self.undo)

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
        self.lab_context_label = tk.Label(main, text="Navigation")
        self.lab_context_label.grid(row=rowInOrder(1), sticky=tk.W, column=1)
        self.btn_ref = tk.Button(
            main, text="Open", takefocus=False, command=self.openDir)
        self.btn_ref.grid(row=inOrderList[1], column=1, sticky=tk.E)

        self.btn_skip = tk.Button(
            main, text="Skip", takefocus=False, command=self.nextImage)
        self.btn_skip.grid(row=rowInOrder(1), column=1, sticky=tk.E)
        self.btn_ref = tk.Button(
            main, text="Refresh", takefocus=False, command=(
                lambda: (self.reloadDirContext(), self.imageUpdate()))
        )
        self.btn_ref.grid(row=inOrderList[1], column=1)
        self.btn_back = tk.Button(
            main, text="Prev", takefocus=False, command=self.prevImage)
        self.btn_back.grid(row=inOrderList[1], column=1, sticky=tk.W)

        def validateCommand(event):
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
            except OSError:
                self.labelFileName()
                event.widget.configure(bg=BAD)

        def myEntry():
            return tk.Entry(main, highlightthickness=2)

        # Entry text field
        self.lab_context_label = tk.Label(
            main, text="Move to folder ID:")
        self.lab_context_label.grid(row=rowInOrder(1), column=1)
        self.entry = myEntry()
        self.entry.bind("<Return>", self.submit)
        self.entry.bind("<KeyRelease>", validateCommand)
        self.entry.grid(row=rowInOrder(1), column=1)

        # New folder entry
        self.lab_newfolder = tk.Label(
            main, text="Move to new folder:")
        self.lab_newfolder.grid(row=rowInOrder(1), column=1)
        self.entry_newfolder = myEntry()
        self.entry_newfolder.bind("<Return>", self.newfolder)
        self.entry_newfolder.grid(row=rowInOrder(1), column=1)

        # Rename label and check
        self.lab_rename = tk.Label(main, text="Rename")
        self.lab_rename.grid(row=rowInOrder(1), column=1, sticky=tk.W)
        self.confident = tk.IntVar()
        self.check_confident = tk.Checkbutton(
            main, text="Displace", variable=self.confident)
        self.check_confident.grid(row=inOrderList[1], column=1, sticky=tk.E)
        
        # Rename entry
        self.entry_rename = myEntry()
        self.entry_rename.grid(row=rowInOrder(1), column=1)
        self.entry_rename.bind("<Return>", self.dorename)
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

    def submit(self, event):
        oldFileName = self.filepaths[self.image_index]
        entry = event.widget.get()
        if entry == "":
            self.nextImage()
            return
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
        usubdir = dst + "unsorted\\"
        if os.path.exists(usubdir):
            dst = usubdir
        filemove(oldFileName, dst)
        print(dst + "\\" + oldFileName.split("\\")[-1], oldFileName)
        self.undo = lambda self: filemove(dst + oldFileName.split("\\")[-1], oldFileName)

        # Clear field
        event.widget.delete(0, last=tk.END)
        self.nextImage()

    def dorename(self, event):
        entry = event.widget.get()
        if entry == "":
            self.nextImage()
            return
        oldFileName = self.filepaths[self.image_index]
        newFileName = "{}\\{}.{}".format(
            "\\".join(oldFileName.split("\\")[:-1]),
            entry,
            oldFileName.split(".")[-1]
        )
        doFileRename(oldFileName, newFileName,
                     confident=(self.confident.get() == 1))
        self.undo = lambda self: doFileRename(newFileName, oldFileName, confident=(self.confident.get() == 1))
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
            self.nextImage()
        except Exception:
            traceback.print_exc()

        # Clear field
        event.widget.delete(0, last=tk.END)

    def undo(self, event):
        self.undo(self)
        self.undo = nop
        self.image_index -= 1
        self.reloadImages()
        self.imageUpdate()

    def generatePaths(self, rootpath):
        print("Generating paths for: {}".format(rootpath))
        if os.path.exists("{}\\unsorted".format(rootpath)):
            # Dive into unsorted
            self.imageglobs = [
                "{}\\unsorted\\*.{}".format(rootpath, ext) for ext in IMAGEEXTS]
            # Path to add new folders in:
            self.contextglobs = [rootpath + '\\*\\', rootpath + '\\..\\']
        else:
            self.imageglobs = [
                "{}\\*.{}".format(rootpath, ext) for ext in IMAGEEXTS]
            self.contextglobs = [rootpath + '\\..\\*\\', rootpath + '\\..\\']
            rootpath += "\\..\\"
        self.rootpath = rootpath  # Where we make new folders

    def reloadDirContext(self):
        self.context = sum([glob(a) for a in self.contextglobs], [])
        print(self.context)
        self.keymap = makeMappings(self.context)
        self.generateContextKey(self.context, self.keymap)

    def reloadImages(self):
        # self.filepaths = sorted(
        #     sum([glob(a) for a in self.imageglobs], []), key=imageSize)
        self.filepaths = sum([glob(a) for a in self.imageglobs], [])

    def nextImage(self):
        # Queue the next image
        self.image_index += 1
        self.imageUpdate()

    def prevImage(self):
        self.image_index -= 1
        self.imageUpdate()

    def imageUpdate(self):
        # Let window load
        maxwidth = self.canvas.winfo_width()
        maxheight = self.canvas.winfo_height()

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
                pilimg = Image.open(filename)
                self.curimg = ImageTk.PhotoImage(pilimg)
            except OSError as e:
                print("[OS error] Bad image: " + filename)
                traceback.print_exc()
                self.filepaths.remove(filename)
                self.imageUpdate()
                return
            except tk._tk.TclError as e:
                print("[tk error] Bad image: " + filename)
                traceback.print_exc()
                self.filepaths.remove(filename)
                self.imageUpdate()
                return

            width = self.curimg.width()
            height = self.curimg.height()
            imageIsTooBig = width > maxwidth or height > maxheight
            if (imageIsTooBig or ALWAYS_RESIZE) and not maxwidth == maxheight == 1:
                print("Image {} is too big. [{}x{} image in {}x{} canvas]".format(
                    filename,
                    width,
                    height,
                    maxwidth,
                    maxheight
                ))
                ratio = min(maxwidth / width, maxheight / height)
                method = Image.ANTIALIAS
                if ratio > 1:
                    ratio = floor(ratio)
                    method = Image.LINEAR
                pilimg = Image.open(filename).resize(
                    (int(width * ratio), int(height * ratio)), method)

                self.curimg = ImageTk.PhotoImage(pilimg)

            self.canvas.itemconfig(self.image_on_canvas, image=self.curimg)
            self.labelFileName()


ap = argparse.ArgumentParser()
ap.add_argument("-r", "--root",
                help="Root folder. Should contain folders, one of which is named unsorted.")
args = ap.parse_args()


Tk = tk.Tk()
MainWindow(Tk, args.root)
Tk.mainloop()
