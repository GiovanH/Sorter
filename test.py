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
        ["{}: {}".format(itoa[i], context[i])
         for i in range(0, len(context))]
    )


class MainWindow():

    def __init__(self, Tk, rootpath, confident):

        self.image_index = 0

        # Store arguments.
        self.main = Tk
        self.confident = confident
        self.rootpath = rootpath

        # Initialize window
        self.initwindow(Tk)

    def initwindow(self, main):
        # Create a tk window.

        # canvas for image
        self.pic = tkinter.Canvas(main, width=256, height=256, bg="#AA0001")
        self.pic.grid(row=0, column=1, rowspan=4)

        self.text1 = tkinter.Canvas(main, width=256, height=32, bg="#00AA00")
        self.text1.grid(row=0, column=0)

        self.text2 = tkinter.Canvas(main, width=256, height=32, bg="#AAAA00")
        self.text2.grid(row=1, column=0)

        self.text3 = tkinter.Canvas(main, width=256, height=32, bg="#00AA00")
        self.text3.grid(row=2, column=0)


ap = argparse.ArgumentParser()
ap.add_argument("-r", "--root", required=True,
                help="Root folder. Should contain folders, one of which is named unsorted.")
ap.add_argument("--confident", action="store_true",
                help="In the case of rename conflicts, move the conflict out of the way.")
args = ap.parse_args()


Tk = tkinter.Tk()
MainWindow(Tk, args.root, args.confident)
Tk.mainloop()
