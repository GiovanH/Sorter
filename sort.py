import tkinter
from glob import glob
import argparse
import shutil
import os
import traceback
from PIL import ImageTk, Image

"""
TODO:
Backend:
Create new folders!

Frontend:
Resize image to frame
Maybe a landscape layout to maximize screen space?
Better display for choices. Align left.
Don't have to press enter to submit.
"""

itoa = list('abcdefghijklmnopqrstuvwxyz')
atoi = {itoa[i]: i for i in range(0, len(itoa))}


def generateContextKey(context):
    return "\n".join(
        ["{}: {}".format(itoa[i], context[i].split('\\')[-2])
         for i in range(0, len(context))]
    )


class MainWindow():

    def __init__(self, Tk, rootpath, confident):

        self.image_index = 0

        # Store arguments.
        self.main = Tk
        self.confident = confident
        self.rootpath = rootpath

        # Validate arguments
        self.validatepath(rootpath)

        # Initialize data
        self.reloadDirContext(rootpath)
        self.reloadImages(rootpath)

        # Initialize window
        self.initwindow(Tk)

        # Initialize images
        self.nextImage()

    def reloadDirContext(self, rootpath):
        self.context = glob(rootpath + '/*/')

    def initwindow(self, main):
        # Create a tk window.

        # canvas for image
        self.canvas = tkinter.Canvas(main)
        # self.canvas.grid(row=0, column=0)
        # self.btn_skip.grid(row=1, column=0)
        self.canvas.grid(row=0, column=1, rowspan=5)

        # set first image on canvas, an ImageTk.PhotoImage
        self.image_on_canvas = self.canvas.create_image(
            128, 128, anchor=tkinter.CENTER, image=self.filelist[self.image_index][1])

        # Entry text field
        self.entry = tkinter.Entry(main)
        self.entry.bind("<Return>", self.submit)
        self.entry.grid(row=4, column=0)

        # current filename label
        self.str_curfile = tkinter.StringVar(value="NaN")
        self.lab_curfile = tkinter.Label(main, textvariable=self.str_curfile)
        self.lab_curfile.grid(row=1, column=0)

        # context keys
        self.str_context = tkinter.StringVar(value=generateContextKey(self.context))
        self.lab_context = tkinter.Message(
            main, anchor=tkinter.W, textvariable=self.str_context)
        self.lab_context.grid(row=2, column=0)

        # button to skip image
        self.btn_skip = tkinter.Button(main, text="Skip", command=self.nextImage)
        self.btn_skip.grid(row=3, column=0)

    def validatepath(self, rootpath):
        # Check for the unsorted directory.
        p = "{}/unsorted".format(rootpath)
        assert(os.path.exists(p))

    def submit(self, event):
        oldFileName = self.filelist[self.image_index][0]
        entry = self.entry.get()
        if entry == "":
            self.nextImage()
            return
        try:
            choice = self.context[atoi[entry]]
        except KeyError:
            # os.mkdir(entry)
            # self.reloadDirContext(self.rootpath)
            self.str_curfile.set("Invalid integer: {}".format(self.entry.get()))
            return
            # choice = self.context[atoi[self.entry.get()]]
        # extension = oldFileName.split('.')[-1]
        dst = choice
        print({"SRC": oldFileName, "DST": dst})
        shutil.move(oldFileName, dst)

        # Clear field
        self.entry.delete(0, last=tkinter.END)
        self.nextImage()

    def reloadImages(self, fileglob):
        # Initialize a filelist of [path, image] pairs.
        filepaths = glob("{}\\unsorted/*.*".format(self.rootpath))
        self.filelist = [[d, None] for d in filepaths]

        # Create tkinter image objects and pair with paths
        for entry in self.filelist:
            filename = entry[0]
            try:
                image = ImageTk.PhotoImage(Image.open(filename))
                # tkinter.PhotoImage(file=filename)
                entry[1] = image
            except tkinter._tkinter.TclError as e:
                print("[tkinter error] Bad image: " + filename)
                traceback.print_exc()
                self.filelist.remove(entry)

    def nextImage(self):
        # Queue the next image
        self.image_index += 1

        # return to first image if we should
        if self.image_index >= len(self.filelist):
            self.reloadImages(self.rootpath)
            self.image_index = 0

        if len(self.filelist) == 0:
            self.str_curfile.set("No more images found!")
        else:
            # change image on canvas
            self.canvas.itemconfig(self.image_on_canvas,
                                   image=self.filelist[self.image_index][1])
            # self.canvas.coords(self.image_on_canvas, self.my_images[self.image_index].width()/2, self.my_images[self.image_index].height()/2)
            # self.canvas.grid(row=0, column=0)

            # Label image
            prettyname = self.filelist[self.image_index][0].split("\\")[-1]
            # prettyname = self.filelist[self.image_index][0]
            self.str_curfile.set(prettyname)


ap = argparse.ArgumentParser()
ap.add_argument("-r", "--root", required=True,
                help="Root folder. Should contain folders, one of which is named unsorted.")
ap.add_argument("--confident", action="store_true",
                help="In the case of rename conflicts, move the conflict out of the way.")
args = ap.parse_args()


Tk = tkinter.Tk()
MainWindow(Tk, args.root, args.confident)
Tk.mainloop()
