import tkinter as tk

from io import BytesIO
from PIL import Image
from PIL import ImageDraw
from PIL import UnidentifiedImageError
from PIL import ImageTk
from PIL import ExifTags
import cv2

import os
import subprocess
from threading import Lock
from tkinter import filedialog
import collections
import math
import zipfile
import threading

import typing
import functools

import filesystem
import loom

import logging
logger = logging.getLogger(__name__)

# from snip.stream import TriadLogger
# logger = TriadLogger(__name__)

IMAGEEXTS = ["png", "jpg", "gif", "bmp", "jpeg", "tif", "gifv", "jfif"]
VIDEOEXTS = ["webm", "mp4", "mov", "webp"]
_IMAGEEXTS = ["." + e for e in IMAGEEXTS]
_VIDEOEXTS = ["." + e for e in VIDEOEXTS]


def framesInImage(im):
    try:
        im = Image.open(im)
    except OSError:
        return 1
    try:
        while True:
            frames = im.tell()
            im.seek(frames + 1)
    except EOFError:
        return frames + 1


def autoRotate(image):

    orientationflags = [key for key in ExifTags.TAGS.keys() if ExifTags.TAGS[key] == 'Orientation']
    try:
        for orientation in orientationflags:
            exif = dict(image._getexif().items())
            if not exif.get(orientation):
                continue

            if exif[orientation] == 3:
                return image.rotate(180, expand=True)
            elif exif[orientation] == 6:
                return image.rotate(270, expand=True)
            elif exif[orientation] == 8:
                return image.rotate(90, expand=True)
    except (KeyError, AttributeError):
        pass

    return image


def bytes_to_string(bytes, units=['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB'], sep="", base=1024):
    """ Returns a human readable string reprentation of bytes."""
    # Adapted from a comment by "Mr. Me" on github.
    if bytes < base:
        return "{:0.2f}{}{}".format(bytes, sep, units[0])
    else:
        return bytes_to_string(bytes / base, units[1:], sep=sep)


def send_to_clipboard(clip_type, data) -> None:
    import win32clipboard
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(clip_type, data)
    win32clipboard.CloseClipboard()


def copy_imdata_to_clipboard(filepath) -> None:
    import win32clipboard

    image = Image.open(filepath)

    output = BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()

    send_to_clipboard(win32clipboard.CF_DIB, data)


def copy_text_to_clipboard(text) -> None:
    import win32clipboard
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_TEXT)
    win32clipboard.CloseClipboard()


class ContentCanvas(tk.Canvas):
    def __init__(self, *args, **kwargs):
        """Args:
            parent (tk): Tk parent widget
            *args: Passthrough
            **kwargs: Passthrough
        """
        tk.Canvas.__init__(self, *args, **kwargs)

        self.photoImageCaches = collections.defaultdict(dict)
        self.photoImageCache = self.photoImageCaches[(0, 0)]
        self.textCache = {}

        self.preloaderLock = Lock()
        self.spool = loom.Spool(8, "ContentCanvas")

        self.current_file = ""

        self.resize_after = None

        # Initialize window
        self.initwindow()

    def destroy(self):
        # self.spool.finish()
        self.spool.cancel()
        super().destroy()

    def initwindow(self) -> None:
        # set first image on canvas, an ImageTk.PhotoImage
        self.photoimage = self.create_image(
            0, 0, anchor="nw")

        self.text = self.create_text(10, 10, anchor="nw")

        self.bind("<Configure>", self.onResize)

        # create a menu
        popup = tk.Menu(self, tearoff=0)
        try:
            import win32clipboard
            popup.add_command(label="Copy image", command=lambda: copy_imdata_to_clipboard(self.current_file))  # , command=next) etc...
            popup.add_command(label="Copy path", command=lambda: copy_text_to_clipboard(self.current_file))  # , command=next) etc...
        except ImportError:
            logger.error("Clipboard support ('win32clipboard') not available.")
        popup.add_separator()
        popup.add_command(label="Open", command=lambda: os.startfile(self.current_file))
        popup.add_command(label="Open file location", command=self.open_file_location)
        popup.add_separator()
        popup.add_command(label="Save a copy", command=self.save_a_copy)
        popup.add_command(label="Save a copy (quick)", command=self.quicksave)

        def do_popup(event):
            # display the popup menu
            try:
                popup.tk_popup(event.x_root, event.y_root, 0)
            finally:
                # make sure to release the grab (Tk 8.0a1 only)
                popup.grab_release()

        self.bind("<Button-3>", do_popup)

    def open_file_location(self) -> None:
        windir: str = os.getenv('WINDIR')  # type: ignore[assignment]
        FILEBROWSER_PATH = os.path.join(windir, 'explorer.exe')
        path = os.path.normpath(self.current_file)

        if os.path.isdir(path):
            subprocess.run([FILEBROWSER_PATH, path])
        elif os.path.isfile(path):
            subprocess.run([FILEBROWSER_PATH, '/select,', os.path.normpath(path)])

    def save_a_copy(self) -> None:
        newFileName = filedialog.asksaveasfilename(
            initialfile=os.path.basename(self.current_file)
        )
        filesystem.copyFileToFile(self.current_file, newFileName)
        logger.info(f"{self.current_file} -> {newFileName}")

    def quicksave(self, event=None) -> None:
        downloads = filesystem.userProfile("Pictures")
        filesystem.copyFileToDir(self.current_file, downloads)
        logger.info(f"{self.current_file} -> {downloads}")
        self.bell()

    def onResize(self, configure_event):
        # self.markAllDirty()
        # We don't need to mark text dirty
        # logger.debug("Clearing photoimage cache (window resized)")
        # self.photoImageCache.clear()
        def _resizeafter_callback():
            dimensions = (self.winfo_width(), self.winfo_height())
            self.photoImageCache = self.photoImageCaches[dimensions]
            # logger.debug(f"Switching to cache for size {dimensions}")
            self.setFile(self.current_file)
            # If this was done after a resize, cancel that biz.
            self.resize_after = None

        if self.current_file:
            if self.resize_after:
                self.after_cancel(self.resize_after)
            self.resize_after = self.after(100, _resizeafter_callback)

    def markCacheDirty(self, entry: str):
        # logger.debug(f"Removing dirtied cache item {entry}")
        self.photoImageCache.pop(entry, None)
        self.textCache.pop(entry, None)

    def markAllDirty(self):
        # logger.debug("Clearing photoimage cache (all dirty)")
        self.photoImageCache.clear()
        self.textCache.clear()

    def clear(self):
        self.itemconfig(self.photoimage, image=None)
        self.itemconfig(self.photoimage, state="hidden")
        self.itemconfig(self.text, text=None, state="hidden")

    def setFile(self, filepath) -> bool:
        """Update the display to match the current image index.
        """

        normpath = os.path.normpath(filepath)

        if normpath == ".":
            return False

        self.current_file = normpath

        # try:
        #     self.curimg = self.makePhotoImage(filepath)
        # except (OSError, SyntaxError, tk.TclError) as e:
        #     print("[{}] Bad image: ".format(e) + filepath)
        #     traceback.print_exc()
        #     return False

        return self.configureForFile(filepath)

    def configureForFile(self, filepath) -> bool:
        # logger.debug(f"Configuring canvas for new filepath '{filepath}'")
        text = "No selection."

        if not filepath:
            return False

        if not os.path.isfile(filepath):
            return False

        self.curimg: typing.Optional[ImageTk.PhotoImage] = None

        (filename_, fileext) = os.path.splitext(filepath)
        if fileext.lower() in _IMAGEEXTS or fileext.lower() in _VIDEOEXTS:
            self.curimg = self.makePhotoImage(filepath)
            self.itemconfig(self.photoimage, image=self.curimg, state="normal")
            self.itemconfig(self.text, text=None, state="hidden")
        else:
            text = self.makeTextData(filepath)
            self.itemconfig(self.text, text=text, state="normal")
            self.itemconfig(self.photoimage, image="", state="hidden")
            self.curimg = None
        return True

    def preloadImage(self, filepaths) -> None:
        if len(filepaths) > 20:
            return
        for filepath in filepaths:
            if filepath not in self.photoImageCache.keys():
                # print("Path", filepath, "missing from cache", self.photoImageCache.keys())
                def _do():
                    self.spool.enqueue(
                        target=self.makePhotoImage,
                        args=(
                            filepath,
                            self.winfo_width(),
                            self.winfo_height(),
                        )
                    )
                self.after_idle(_do)

    def makeTextData(self, filepath) -> str:
        text = self.textCache.get(filepath, "")
        if not text:
            text += f"\nPath:\t{filepath}"
            text += f"\nSize:\t{bytes_to_string(os.path.getsize(filepath))}"

            filename, fileext = os.path.splitext(filepath)
            if fileext.lower() == ".pdf":
                try:
                    # from pdfminer.pdfparser import PDFParser
                    # from pdfminer.pdfdocument import PDFDocument

                    # def decodePdfVal(value):
                    #     try:
                    #         if "decode" in dir(value):
                    #             return value.decode(errors="replace")
                    #         elif "resolve" in dir(value):
                    #             return value.resolve().decode(errors="replace")
                    #     except Exception as e:
                    #         print(e)
                    #         return value
                    import pikepdf

                    with pikepdf.open(filepath) as pdf:
                        for key, value in pdf.docinfo.items():
                            try:
                                text += f"\n{key}:\t{value}"
                            except NotImplementedError:
                                text += f"\n{key}:\t{value!r}"

                except ImportError:
                    text += f"\nImportError: pikepdf not installed"
                except Exception as e:
                    text += f"\npikepdf {type(e)}: {e}"

            if fileext.lower() == ".zip":
                with zipfile.ZipFile(filepath, 'r') as fp:
                    text += "\n" + "\n".join(fp.namelist())

            if os.name == "nt":
                try:
                    from snip.win32_fileprops import property_sets
                    for name, properties in property_sets(filepath):
                        text += f"\nWin32 {name}"
                        for key, value in properties.items():
                            if value:
                                text += f"\n\t{key}:\t{value}"
                except ImportError as e:
                    text += f"\n{e}"

            try:
                with open(filepath, "r") as fp:
                    text += f"\n{fp.read(5000)}"  # 5 kb
            except Exception as e:
                print(e)
                pass

        self.textCache[filepath] = text
        return text

    # def makePhotoImage(self, filename, ALWAYS_RESIZE=True, stepsize=4):
    #     with snip.math.timer("makePhotoImage {}".format(filename)):
    #         _makePhotoImage(self, filename, ALWAYS_RESIZE, stepsize)

    # def _makePhotoImage(self, filename, ALWAYS_RESIZE=True, stepsize=4):

    def placeholderImage(self) -> Image.Image:
        pilimg = Image.new('RGB', (10, 10), color=(0, 0, 0))
        ImageDraw.Draw(pilimg).text((2, 0), "?", fill=(255, 255, 255))
        return pilimg

    def getInfoLabel(self) -> str:
        if self.current_file == "":
            return "No file"

        prettyname = self.current_file
        if not os.path.isfile(self.current_file):
            prettyname += " (Not Found)"
            return prettyname

        return self.getInfoLabelForFile(self.current_file)

    @functools.lru_cache()
    def getInfoLabelForFile(self, filepath) -> str:
        __, fileext = os.path.splitext(filepath)
        prettyname: str = filepath  # Fallback 2
        try:
            filename: str = os.path.split(filepath)[1]
            filesize: str = bytes_to_string(os.path.getsize(filepath))

            prettyname = f"{filename}\n{filesize}"  # Fallback 1

            (filename_, fileext) = os.path.splitext(filename)

            # Get initial image
            if fileext.lower() in _IMAGEEXTS:
                frames = 1  # framesInImage(filepath)
                w, h = Image.open(filepath).size
                if frames > 1:
                    prettyname = f"{filename} [{frames}f]\n{filesize} [{w}x{h}px]"
                else:
                    prettyname = f"{filename}\n{filesize} [{w}x{h}px]"

            elif fileext.lower() in _VIDEOEXTS:
                capture = cv2.VideoCapture(filepath)
                capture.grab()
                flag, frame = capture.retrieve()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pilimg = Image.fromarray(frame)

                w, h = pilimg.size
                frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

                prettyname = f"{filename} [{frames}f]\n{filesize} [{w}x{h}px]"

            else:
                raise OSError(f"Exception reading image '{filepath}'")

        except (OSError, cv2.error, UnidentifiedImageError):
            logger.error("OS error while getting file info", exc_info=True)
            pass
        return prettyname

    def makePhotoImage(self, filename, ALWAYS_RESIZE=True, stepsize=4) -> typing.Optional[ImageTk.PhotoImage]:
        """Make a resized photoimage given a filepath

        Args:
            filename (str): Path to an image file
            maxwidth (TYPE): Maximum width of canvas
            maxheight (TYPE): Maximum height of canvas

        Returns:
            ImageTk.PhotoImage
        """
        # pilimg = Image.open(filename)

        maxwidth = self.winfo_width()
        maxheight = self.winfo_height()
        # Let window load
        if maxwidth <= 1 or maxheight <= 1:
            self.after(200, self.makePhotoImage, filename, ALWAYS_RESIZE, stepsize)
            # logger.debug("Window not initialized, waiting")
            return None

        # Attempt cache fetch
        pilimg = self.photoImageCache.get(filename)

        if pilimg:
            # logger.debug(f"photoimage cache hit for filename '{filename}'")
            return ImageTk.PhotoImage(pilimg)

        (filename_, fileext) = os.path.splitext(filename)

        # Get initial image
        try:
            if fileext.lower() in _IMAGEEXTS:
                pilimg = Image.open(filename)
                pilimg = autoRotate(pilimg)

            elif fileext.lower() in _VIDEOEXTS:
                capture = cv2.VideoCapture(filename)
                capture.grab()
                flag, frame = capture.retrieve()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pilimg = Image.fromarray(frame)
            else:
                raise OSError("Exception reading image")
        except (cv2.error, OSError,):
            pilimg = self.placeholderImage()

        # For full support
        pilimg = pilimg.convert('RGBA')

        # Resize image to canvas
        ratio = 1.0
        imageIsTooBig = (pilimg.width > maxwidth) or (pilimg.height > maxheight)

        if imageIsTooBig:
            ratio = min(maxwidth / pilimg.width, maxheight / pilimg.height)
            method: Image.Resampling = Image.Resampling.BICUBIC
        else:
            ratio = min(maxwidth / pilimg.width, maxheight / pilimg.height)
            ratio = math.floor(ratio * 4) / 4
            method = Image.Resampling.NEAREST
            # else:
            #     print("Warning: stepratio =", stepratio, "with ratio", ratio, "and stepsize", stepsize)
        if ratio != 1.0 and ratio > 0:
            # logger.debug(f"Resizing {filename} to {ratio}x using method {method}")
            try:
                # print(f"Resize: mw{maxwidth}, mh{maxheight}, w{pilimg.width}, h{pilimg.height}, ratio {ratio}, method {method}, stepsize {stepsize}\n{filename}")
                pilimg = pilimg.resize(
                    (int(pilimg.width * ratio), int(pilimg.height * ratio)), method)
            except (OSError, ValueError):
                logger.error(f"OS error resizing file {filename}", exc_info=True)
                # raise
                # loc = None
                # for loc in locals():
                #     print(loc, ":", locals().get(loc))
                try:
                    return ImageTk.PhotoImage(pilimg)
                except SyntaxError:
                    logger.error("Corrupt image", exc_info=True)
                    pilimg = self.placeholderImage()
                except (MemoryError, tk.TclError):
                    logger.error("Corrupt image, I think?", exc_info=True)
                    pilimg = self.placeholderImage()
                except Exception:
                    logger.error("Unhandled exception", exc_info=True)
                    raise
        else:
            logger.debug(f"NOT {filename} to {ratio}x using method {method} (bad ratio)")

        # Add overlay to video files
        pilimg_bak = pilimg
        try:
            if fileext.lower() in _VIDEOEXTS:
                ImageDraw.Draw(pilimg).rectangle([(0, 0), (30, 14)], fill=(0, 0, 0))
                ImageDraw.Draw(pilimg).text((2, 2), fileext.lower(), fill=(255, 255, 255))

            if (fileext.lower() in _IMAGEEXTS and framesInImage(filename) > 1):
                ImageDraw.Draw(pilimg).rectangle([(0, 0), (30, 14)], fill=(0, 0, 0))
                ImageDraw.Draw(pilimg).text((2, 2), str(framesInImage(filename)), fill=(255, 255, 255))
        except ValueError:
            import traceback
            traceback.print_exc()
            # pilimg = pilimg

        self.photoImageCache[filename] = pilimg
        # logger.debug("Adding new photoimage to cache %s", filename)

        threading.Thread(target=self.pruneImageCache, name="pruneImageCache").start()
        return ImageTk.PhotoImage(pilimg)

    def pruneImageCache(self, max_caches=6, max_memory_entries=100):
        # while len(self.photoImageCaches) > max_caches:
        #     bad_cache = list(self.photoImageCaches.keys())[0]
        #     logger.info(f"Popping entire cache {bad_cache} ({len(self.photoImageCaches[bad_cache])} entries)")
        #     self.photoImageCaches.pop(bad_cache)
        for cache in self.photoImageCaches.values():
            if len(cache) < max_memory_entries:
                continue
            while len(cache) > max_memory_entries // 2:
                dirty_item = list(cache.keys())[0]
                logger.info(f"Cache too big, removing entry {dirty_item}")
                cache.pop(dirty_item)
