import tkinter as tk
from glob import glob
import argparse
import shutil
import os
import traceback
import errno
from PIL import ImageTk, Image
from tkinter import filedialog

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


def makeMappings(lst):
    vals = [i.split('\\')[-2].lower() for i in lst]
    map_prime = {vals[i]: lst[i] for i in range(0, len(lst))}
    return map_prime


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


def generateContextKey(context, map_):
    map_prime = {map_[key]: key for key in map_.keys()}
    return "\n".join(
        ["{}".format(map_prime[val][0:15])
         for val in context]
    )


def filemove(src, dst):
    usubdir = dst + "unsorted\\"
    if os.path.exists(usubdir):
        dst = usubdir
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

        # Initialize data
        self.reloadDirContext()
        self.reloadImages()

        # Initialize window
        self.initwindow(Tk)

        # Initialize images
        self.nextImage()
        self.imageUpdate()

    def openDir(self):
        self.generatePaths(filedialog.askdirectory().replace("/", "\\"))

        # Initialize data
        self.reloadDirContext()
        self.reloadImages()

        # Initialize images
        self.nextImage()

    def initwindow(self, main):

        columns = 2
        inOrderList = [1 for i in range(0, columns)]
        height = 0

        # Adjust image with size of window
        # main.bind('<Configure>', lambda event: self.imageUpdate())

        def rowInOrder(col):
            nonlocal height
            inOrderList[col] += 1
            height = max(inOrderList)
            return inOrderList[col]
        # Create a tk window.

        # Header stuff
        # current filename label
        self.str_curfile = tk.StringVar(value="NaN")
        self.lab_curfile = tk.Label(main, textvariable=self.str_curfile)
        self.lab_curfile.grid(row=0, column=0, columnspan=2)

        # UI stuff
        # Backer
        # self.canvas_gui = tk.Canvas(main)
        # self.canvas_gui.grid(row=1, column=0, rowspan=4, sticky=FILL)

        # Navigation buttons
        self.lab_context_label = tk.Label(main, text="Navigation").grid(
            row=rowInOrder(1), sticky=WFILL, column=1)
        btnrow = rowInOrder(1)
        self.btn_skip = tk.Button(
            main, text="Skip", takefocus=False, command=self.nextImage)
        self.btn_skip.grid(row=btnrow, column=1, sticky=tk.E)

        self.btn_ref = tk.Button(main, takefocus=False, text="Refresh", command=(
            lambda: self.imageUpdate() and self.reloadDirContext()))
        self.btn_ref.grid(row=btnrow, column=1)

        self.btn_back = tk.Button(
            main, takefocus=False, text="Prev", command=self.prevImage)
        self.btn_back.grid(row=btnrow, column=1, sticky=tk.W)

        self.btn_ref = tk.Button(main, takefocus=False, text="Open", command=self.openDir)
        self.btn_ref.grid(row=rowInOrder(1), column=1)

        def validateCommand(event):
            GOOD = "#AAFFAA"
            BAD = "#FFAAAA"
            NORMAL = "#FFFFFF"
            if event.widget.get() == "":
                event.widget.configure(bg=NORMAL)
            else:
                try:
                    self.str_curfile.set(
                        self.getBestFolder(event.widget.get()))
                    event.widget.configure(bg=GOOD)
                except OSError:
                    self.labelFileName()
                    event.widget.configure(bg=BAD)

        # Entry text field
        self.lab_context_label = tk.Label(
            main, text="Move to folder ID:").grid(row=rowInOrder(1), column=1)
        self.entry = tk.Entry(main)
        self.entry.bind("<Return>", self.submit)
        self.entry.bind("<KeyRelease>", validateCommand)
        self.entry.grid(row=rowInOrder(1), column=1)

        # New folder button
        self.lab_newfolder = tk.Label(main, text="Move to new folder:").grid(
            row=rowInOrder(1), column=1)
        self.entry_newfolder = tk.Entry(main)
        self.entry_newfolder.bind("<Return>", self.newfolder)
        self.entry_newfolder.grid(row=rowInOrder(1), column=1)

        # context keys
        self.lab_context_label = tk.Label(
            main, text="Folder IDs:").grid(row=rowInOrder(1), column=1)

        # self.str_context = tk.StringVar()
        self.lab_context = tk.Message(
            main, anchor=tk.W, textvariable=self.str_context)
        self.lab_context.grid(row=rowInOrder(1), column=1)

        # Canvas stuff
        # canvas for image
        self.canvas = tk.Canvas(main)  # , bg="#AA0001"
        self.canvas.grid(row=1, column=0, rowspan=height, sticky=FILL)

        # Allow smart grid resizing for the canvas cell
        top = self.main.winfo_toplevel()
        top.rowconfigure(1, weight=1)
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
        filemove(oldFileName, dst)

        # Clear field
        event.widget.delete(0, last=tk.END)
        self.nextImage()

    def newfolder(self, event):
        newfoldername = event.widget.get()
        oldFileName = self.filepaths[self.image_index]
        if newfoldername == "":
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

    def generatePaths(self, rootpath):
        print("Generating paths for: {}".format(rootpath))
        if os.path.exists("{}\\unsorted".format(rootpath)):
            self.imageglob = "{}\\unsorted\\*.*".format(rootpath)
            # Path to add new folders in:
            self.contextglobs = [rootpath + '\\*\\', rootpath + '\\..\\']
        else:
            self.imageglob = "{}\\*.*".format(rootpath)
            self.contextglobs = [rootpath + '\\..\\*\\', rootpath + '\\..\\']
            rootpath += "\\..\\"
        self.rootpath = rootpath

    def reloadDirContext(self):
        self.context = sum([glob(a) for a in self.contextglobs], [])
        print(self.context)
        self.keymap = makeMappings(self.context)
        self.str_context.set(generateContextKey(self.context, self.keymap))

    def reloadImages(self):
        self.filepaths = sorted(glob(self.imageglob), key=imageSize)
        # self.filelist = []

        # # Create tk image objects and pair with paths
        # for filename in filepaths:
        #     try:
        #         print(filename)
        #         pilimage = Image.open(filename)
        #         image = ImageTk.PhotoImage(pilimage)
        #         # tk.PhotoImage(file=filename)
        # #         self.filelist.append([filename, image])
        #     except OSError as e:
        #         print("[OS error] Bad image: " + filename)
        #         traceback.print_exc()
        #     except tk._tk.TclError as e:
        #         print("[tk error] Bad image: " + filename)
        #         traceback.print_exc()
                # self.filelist.remove(entry)

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
            self.image_index = len(self.filepaths)
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
                pilimg = Image.open(filename).resize((int(width * ratio), int(height * ratio)), Image.ANTIALIAS)
                self.curimg = ImageTk.PhotoImage(pilimg)

            self.canvas.itemconfig(self.image_on_canvas, image=self.curimg)
            self.labelFileName()

    def labelFileName(self):
        prettyname = self.filepaths[self.image_index].split("\\")[-1]
        # prettyname = self.filelist[self.image_index][0]
        self.str_curfile.set(prettyname)


ap = argparse.ArgumentParser()
ap.add_argument("-r", "--root",
                help="Root folder. Should contain folders, one of which is named unsorted.")
args = ap.parse_args()


Tk = tk.Tk()
MainWindow(Tk, args.root)
Tk.mainloop()
