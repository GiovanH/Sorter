import tkinter
import glob
import argparse
import fsops


class MainWindow():

    def submit(self, event):
        oldFileName = self.filelist[self.image_index][0]
        inputName = self.entry.get()
        if inputName != "":
            extension = oldFileName.split('.')[-1]
            newFileName = "\\".join(oldFileName.split(
                "\\")[:-1]) + "\\" + self.entry.get() + "." + extension
            print({"O": oldFileName, "i": inputName, "n": newFileName})
            fsops.doFileRename(oldFileName, newFileName)
            # os.rename
            # Clear field
        self.entry.delete(0, last=tkinter.END)
        self.nextImage()

    def reloadImages(self, fileglob):
        filepaths = sum([glob.glob(a, recursive=True) for a in args.globs], [])
        self.filelist = [[d, None] for d in filepaths]
        # images
        for entry in self.filelist:
            filename = entry[0]
            try:
                image = tkinter.PhotoImage(file=filename)
                entry[1] = image
            except tkinter._tkinter.TclError:
                print("[tkinter error] Bad image: " + filename)
                self.filelist.remove(entry)
        self.image_index = -1  # We will immeditally increment this.

    def __init__(self, main, globs, confident):

        self.main = main
        self.confident = confident

        # canvas for image
        self.canvas = tkinter.Canvas(main, width=256, height=256)
        # self.canvas.grid(row=0, column=0)
        # self.button.grid(row=1, column=0)
        self.canvas.pack()

        self.entry = tkinter.Entry(main)
        self.entry.bind("<Return>", self.submit)
        self.entry.pack()

        self.globs = globs
        self.reloadImages(globs)

        # set first image on canvas
        self.image_on_canvas = self.canvas.create_image(
            128, 128, anchor=tkinter.CENTER, image=self.filelist[self.image_index][1])

        # current filename label
        self.labtxt = tkinter.StringVar()
        self.labtxt.set("NaN")
        self.lab = tkinter.Label(main, textvariable=self.labtxt)
        self.lab.pack()

        # button to change image
        self.button = tkinter.Button(main, text="Skip", command=self.nextImage)
        # self.button.grid(row=1, column=0)
        self.button.pack()

        # init
        self.nextImage()

    def nextImage(self):

        # Queue the next image
        self.image_index += 1

        # return to first image
        if self.image_index == len(self.filelist):
            self.reloadImages(self.globs)
            self.image_index = 0

        # change image
        self.canvas.itemconfig(self.image_on_canvas,
                               image=self.filelist[self.image_index][1])
        # self.canvas.coords(self.image_on_canvas, self.my_images[self.image_index].width()/2, self.my_images[self.image_index].height()/2)
        self.canvas.pack(fill="both", expand=True)
        prettyname = "...\\" + \
            "\\".join(self.filelist[self.image_index][0].split("\\")[-2:])
        self.labtxt.set(prettyname)


ap = argparse.ArgumentParser()
ap.add_argument("-g", "--globs", required=True, nargs='+',
                help="globs")
ap.add_argument("--confident", action="store_true",
                help="In the case of rename conflicts, move the conflict out of the way.")
args = ap.parse_args()

root = tkinter.Tk()
MainWindow(root, args.globs, args.confident)
root.mainloop()
