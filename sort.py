import tkinter as tk
from glob import glob
import argparse
import shutil
import os
import traceback
import errno
from PIL import ImageTk, Image

"""
TODO:
Backend:

Frontend:
Resize image to frame
Maybe a landscape layout to maximize screen space?
"""

FILL = tk.N + tk.S + tk.E + tk.W
WFILL = tk.E + tk.W


def makeMappings(lst):
    vals = [i.split('\\')[-2].lower() for i in lst]
    # done = False
    # extent = 0
    # while not done:
    #     extent += 1
    #     prefixes = [var[0:extent] for var in vals]
    #     if len(set(prefixes)) == len(prefixes):
    #         done = True

    # map_prime = {prefixes[i]: lst[i] for i in range(0, len(lst))}
    map_prime = {vals[i]: lst[i] for i in range(0, len(lst))}
    print(map_prime)
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
    print("{} -> {}".format(src, dst))
    try:
        shutil.move(src, dst)
    except shutil.Error as e:
        print(e.errno, errno.EEXIST, e.errno == errno.EEXIST)
        traceback.print_exc()


class MainWindow():

    def __init__(self, Tk, rootpath, confident):

        self.image_index = -1

        # Store arguments.
        self.main = Tk
        self.confident = confident

        # Validate arguments
        self.generatePaths(rootpath)

        # Initialize data
        self.str_context = tk.StringVar()
        self.reloadDirContext()
        self.reloadImages()

        # Initialize window
        self.initwindow(Tk)

        # Initialize images
        self.nextImage()
        self.imageUpdate()

    def initwindow(self, main):

        columns = 2
        inOrderList = [1 for i in range(0, columns)]
        height = 0

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

        # context keys
        self.lab_context_label = tk.Label(main, text="Folder IDs:").grid(row=rowInOrder(1), column=1)

        # self.str_context = tk.StringVar()
        self.lab_context = tk.Message(main, anchor=tk.W, textvariable=self.str_context)
        self.lab_context.grid(row=rowInOrder(1), column=1)

        # Navigation buttons
        self.lab_context_label = tk.Label(main, text="Navigation").grid(row=rowInOrder(1), sticky=WFILL, column=1)
        btnrow = rowInOrder(1)
        self.btn_skip = tk.Button(main, text="Skip", takefocus=False, command=self.nextImage)
        self.btn_skip.grid(row=btnrow, column=1, sticky=tk.E)

        self.btn_ref = tk.Button(main, takefocus=False, text="Refresh", command=(
            lambda: self.reloadDirContext()))
        self.btn_ref.grid(row=btnrow, column=1)

        self.btn_back = tk.Button(main, takefocus=False, text="Prev", command=self.prevImage)
        self.btn_back.grid(row=btnrow, column=1, sticky=tk.W)
        
        def validateCommand(event):
            GOOD = "#AAFFAA"
            BAD = "#FFAAAA"
            NORMAL = "#FFFFFF"
            if event.widget.get() == "":
                event.widget.configure(bg=NORMAL)
            else:
                try:
                    self.str_curfile.set(self.getBestFolder(event.widget.get()))
                    event.widget.configure(bg=GOOD)
                except OSError:
                    self.labelFileName()
                    event.widget.configure(bg=BAD)

        # Entry text field
        self.lab_context_label = tk.Label(main, text="Move to folder ID:").grid(row=rowInOrder(1), column=1)
        self.entry = tk.Entry(main)
        self.entry.bind("<Return>", self.submit)
        self.entry.bind("<KeyRelease>", validateCommand)
        self.entry.grid(row=rowInOrder(1), column=1)

        # New folder button
        self.lab_newfolder = tk.Label(main, text="Move to new folder:").grid(row=rowInOrder(1), column=1)
        self.entry_newfolder = tk.Entry(main)
        self.entry_newfolder.bind("<Return>", self.newfolder)
        self.entry_newfolder.grid(row=rowInOrder(1), column=1)

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
            0, 0, anchor=tk.N + tk.W,
            image=self.filelist[self.image_index][1])

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
        oldFileName = self.filelist[self.image_index][0]
        entry = event.widget.get()
        if entry == "":
            self.nextImage()
            return
        try:
            print(entry, self.keymap)
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
        oldFileName = self.filelist[self.image_index][0]
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
        if os.path.exists("{}unsorted".format(rootpath)):
            self.imageglob = "{}unsorted\\*.*".format(rootpath)
            # Path to add new folders in:
            self.contextglobs = [rootpath + '*\\', rootpath + '..\\']
        else:
            self.imageglob = "{}*.*".format(rootpath)
            self.contextglobs = [rootpath + '..\\*\\', rootpath + '..\\']
            rootpath += "..\\"
        self.rootpath = rootpath

    def reloadDirContext(self):
        self.context = sum([glob(a) for a in self.contextglobs], [])
        print(self.context)
        self.keymap = makeMappings(self.context)
        self.str_context.set(generateContextKey(self.context, self.keymap))

    def reloadImages(self):
        # Initialize a filelist of [path, image] pairs.
        filepaths = glob(self.imageglob)

        filepaths = sorted(filepaths, key=imageSize)
        self.filelist = []

        # Create tk image objects and pair with paths
        for filename in filepaths:
            try:
                print(filename)
                image = ImageTk.PhotoImage(Image.open(filename))
                # tk.PhotoImage(file=filename)
                self.filelist.append([filename, image])
            except OSError as e:
                print("[OS error] Bad image: " + filename)
                traceback.print_exc()
            except tk._tk.TclError as e:
                print("[tk error] Bad image: " + filename)
                traceback.print_exc()
                # self.filelist.remove(entry)

    def nextImage(self):
        # Queue the next image
        self.image_index += 1
        self.imageUpdate()

    def prevImage(self):
        self.image_index -= 1
        self.imageUpdate()

    def imageUpdate(self):
        # Wraparound
        if self.image_index < 0:
            self.image_index = len(self.filelist)
        if self.image_index >= len(self.filelist):
            self.reloadImages()
            self.image_index = 0

        if len(self.filelist) == 0:
            self.str_curfile.set("No more images found!")
        else:
            filename = self.filelist[self.image_index][0]
            print(self.filelist[self.image_index])
            print(filename)
            img = self.filelist[self.image_index][1]

            maxwidth = self.canvas.winfo_width()
            maxheight = self.canvas.winfo_height()
            imageIsTooBig = img.width() > maxwidth or img.height() > maxheight
            if imageIsTooBig: 
                print("Image {} is too big. [{}x{} image in {}x{} canvas]".format(
                    self.filelist[self.image_index][0],
                    img.width(),
                    img.height(),
                    maxwidth,
                    maxheight
                ))

            self.canvas.itemconfig(self.image_on_canvas,
                                   image=img)

            self.labelFileName()

    def labelFileName(self):
        prettyname = self.filelist[self.image_index][0].split("\\")[-1]
        # prettyname = self.filelist[self.image_index][0]
        self.str_curfile.set(prettyname)


ap = argparse.ArgumentParser()
ap.add_argument("-r", "--root", required=True,
                help="Root folder. Should contain folders, one of which is named unsorted.")
ap.add_argument("--confident", action="store_true",
                help="In the case of rename conflicts, move the conflict out of the way.")
args = ap.parse_args()


Tk = tk.Tk()
MainWindow(Tk, args.root, args.confident)
Tk.mainloop()
