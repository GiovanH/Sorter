"""Summary

Attributes:
    BAD_WORDS (list): List of substrings to avoid while sorting
    DEBUG_FILE_EXISTS (bool): Description
    GLOBAL_QUIET_DEFAULT (bool): Description
    HASHDEBUG (bool): Description
    IScachetotal (TYPE): Description
    PROGRESSBAR_ALLOWED (bool): Description
    SHELVE_FILE_EXTENSIONS (list): Description
    SORTDEBUG (bool): Description
    VALID_IMAGE_EXTENSIONS (list): Description
"""
import loom             # Simple threading wrapper
import imagehash        # Perceptual image hashing
import progressbar      # Progress bars
import os.path          # isfile() method
import traceback
from PIL import Image   # Image IO libraries
from binascii import crc32
from os import sep
import hashlib
from json.decoder import JSONDecodeError

# import shelve           # Persistant data storage
import jfileutil as ju
from snip import chunk

# Todo: Replace some sep formatting with os.path.join

# DEBUG_FILE_EXISTS = False
VALID_IMAGE_EXTENSIONS = ["gif", "jpg", "png", "jpeg", "bmp"]

# Image.MAX_IMAGE_PIXELS = 148306125
Image.MAX_IMAGE_PIXELS = 160000000


def md5(path):
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


def CRC32(filename):
    """Gives the CRC hash of a file on disk.
    Args:
        path (str): Path to a file
    
    Returns:
        str: CRC32 hex digest
    """
    buf = open(filename, 'rb').read()
    buf = (crc32(buf) & 0xFFFFFFFF)
    return "{:08X}".format(buf)
#     return "%08X" % buf


def isImage(filename):
    """
    Args:
        filename (str): Path to a file
    
    Returns:
        bool: True if the path points to an image, else False.
    """
    try:
        return filename.split(".")[-1].lower() in VALID_IMAGE_EXTENSIONS
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
        return filename.split(".")[-1].lower() in ["webm", "mp4"]
    except IndexError:
        # No extension
        return False


def imageSize(filename, quiet=False):
    """
    Args:
        filename (str): Path to an image on disk
        quiet (bool, optional): Surpress printing information
    
    Returns:
        int: Pixels in image or 0 if file is not an image.
    
    Raises:
        FileNotFoundError: Path is not on disk
    """

    try:
        w, h = Image.open(filename).size
        size = w * h
        return size
    except Image.DecompressionBombError:
        return Image.MAX_IMAGE_PIXELS
    except FileNotFoundError:
        print("WARNING! File not found: ", filename)
        raise FileNotFoundError(filename)
    except OSError:
        print("WARNING! OS error with file: ", filename)
        return 0


class db():

    def __init__(self, shelvefile, bad_words=[], sort_debug=False):
        super(db, self).__init__()

        self.shelvefile = shelvefile

        self.bad_words = bad_words
        self.sort_debug = sort_debug

        self.IScachetotal = self.IScachefails = 0

        try:
            self.fsizecache = ju.load("sizes", default=dict())
        except JSONDecodeError:
            print("Bad fscache file, resetting. ")
            self.fsizecache = dict() 

    def getMediaSize(self, filename, quiet=False):

        h4sh = md5(filename)
        hit = self.fsizecache.get(h4sh)
        global IScachetotal
        global IScachefails
        IScachetotal += 1
        if hit:
            # print("H {:5}/{:5}".format(cachehits, (cachefails + cachehits)))
            return hit
        else:
            # print("F {:5}/{:5}".format(cachehits, (cachefails + cachehits)))
            IScachefails += 1
            if IScachefails % 8000 == 0:
                print("Too many cache misses: only {:5}/{:5} hits".format((IScachetotal - IScachefails), IScachetotal))
                ju.save(self.fsizecache, "sizes")

            size = imageSize(filename, quiet)
            self.fsizecache[h4sh] = size
            return size

    def sortDuplicatePaths(self, filenames):
        """
        Takes a list of files known to be duplicates
        and sorts them in order of "desirability"
        
        Args:
            filenames (list): List of file paths
        
        Returns:
            list: Sorted list of file paths
        """

        if len(filenames) <= 1:
            return filenames

        # Sorting key
        def sort(x):
            # Define our sort criteria.
            upper = x.upper()
            xtuple = (
                -imageSize(x),  # Put full resolution images higher
                -upper.count("F:{s}".format(s=sep)),  # Put images in drive F higher.
                sum([upper.count(x.upper()) for x in self.bad_words]),  # Put images with bad words lower
                # Put images in an exports folder lower
                upper.count("{s}EXPORTS{s}".format(s=sep)),
                # Put images with short folder paths higher
                len(x[:x.rfind(sep)]),
                upper.rfind("{s}IPAD{s}".format(s=sep)),  # Put images with iPad in the path lower
                len(x)  # Put images with short total paths higher
            )
            if self.sort_debug:
                print(xtuple, x)
            return xtuple

        st = sorted(filenames, key=sort)
        return st

    def prune(self, verbose=False, show_pbar=True, purge=False, paths=[]):
        """Remove hashes without files.
        
        Args:
            shelvefile (str): Name of database
            verbose (bool, optional): Description
            show_pbar (bool, optional): Description
        """
        print("Removing dead hashes")
        empties = []
        
        with ju.RotatingHandler(self.shelvefile, basepath="databases", readonly=False, default=dict()) as db:
            for key in db.keys():
                if purge:
                    db[key] = [p for p in db.get(key) if (p in paths) and os.path.isfile(p)]
                if len(db.get(key)) == 0:
                    empties.append(key)

            pbar = progressbar.ProgressBar(max_value=len(empties), redirect_stdout=True) if show_pbar else None
            i = 0
            for key in empties:
                db.pop(key)
                if pbar:
                    i += 1
                    pbar.update(i)
                if verbose:
                    print("Cleared key:", key)
            if pbar:
                pbar.finish()

            ju.save(db, shelvefile, basepath="databases")

    def scanDirs(self, image_paths, recheck=False, hash_size=16):
        """Summary
        
        Args:
            shelvefile (str): Name of database
            image_paths (list): List of paths to check (globbed)
            recheck (bool, optional): Don't skip known images
            hash_size (int, optional): Hash size
        """
        # Resolve glob to image paths

        # Make a list of image paths we already know about. We use this to skip images
        # that probably haven't changed.
        # If we're rechecking, we don't need to build this list at all!

        known_paths = set()

        if not recheck:
            print(shelvefile)
            with ju.RotatingHandler(shelvefile, default=dict(), basepath="databases", readonly=True) as db:
                known_paths = set(
                    [
                        item for sublist in
                        db.values()
                        for item in sublist
                    ]
                )

        # Prune the shelve file

        # SCAN: Scan filesystem for images and hash them.

        # Threading
        def fingerprintImage(db, image_path):
            """Updates database db with phash data of image at image_path.
            
            Args:
                db (TYPE): Description
                image_path (TYPE): Description
            
            Returns:
                TYPE: Description
            """

            # load the image and compute the difference hash
            try:
                if isVideo(image_path):
                    proc_hash = md5(image_path)
                elif not isImage(image_path):
                    # print("Unrecognized file format:", image_path)
                    return
                else:            
                    image = Image.open(image_path)
                    proc_hash = str(imagehash.dhash(image, hash_size=hash_size))
                    # Compress:
                    # proc_hash = proc_hash.decode("hex").encode("base64")

            except FileNotFoundError:
                print("WARNING! File not found: ", image_path)
                # traceback.print_exc()
                return
            except ValueError:
                print("WARNING! Error parsing image: ", image_path)
                traceback.print_exc()
                return
            except OSError:
                # traceback.print_exc(limit=2)
                print("ERROR: File", image_path, "is corrupt or invalid.")
                with open("forcedelete.sh", "a", newline='\n') as shellfile:
                    shellfile.write("rm -vf '{}' \n".format(image_path))
                # print("Trashing file.")
                # try:
                #     trash(image_path)
                # except Exception:
                #     print("...but it failed!")
                #     traceback.print_exc(limit=1)
                #     with open("forcedelete.sh", "a", newline='\n') as shellfile:
                #         shellfile.write("rm -vf '{}' \n".format(image_path))

                #     pass  # Not a dealbreaker.
                return

            filename = image_path  # [image_path.rfind("/") + 1:]

            # Add the path to the database if it's not already present.
            # Each Key (a hash) has a List value.
            # The list is a list of file paths with that hash.
            if filename not in db.get(proc_hash, []):
                if HASHDEBUG:
                    print("New file:", image_path, proc_hash)
                db[proc_hash] = db.get(proc_hash, []) + [filename]

        # Reset forcedelete script
        open("forcedelete.sh", "w").close()

        # Only check needed images
        images_to_fingerprint = [image_path for image_path in image_paths if (image_path not in known_paths) or recheck]
        
        # Progress and chunking
        num_images_to_fingerprint = len(images_to_fingerprint)
        chunk_size = 4000

        from math import ceil
        total_chunks = ceil(num_images_to_fingerprint / chunk_size)

        print("Fingerprinting {} images with hash size {}".format(num_images_to_fingerprint, hash_size))
        for (i, image_path_chunk) in enumerate(chunk(images_to_fingerprint, chunk_size)):
            with ju.RotatingHandler(shelvefile, default=dict(), basepath="databases", readonly=False) as db:
                with loom.Spool(8, name="Fingerprint {}/{}".format(i + 1, total_chunks)) as fpSpool:
                    for image_path in image_path_chunk:
                        fpSpool.enqueue(target=fingerprintImage, args=(db, image_path,))

    def getDuplicatesToDelete(self, interactive=False):
        """Given a database, generate a list of duplicate files to delete.
        
        Args:
            shelvefile (str): Name of database
            interactive (bool, optional): Require user confirmation
        
        Returns:
            list: List of file paths of images marked for deletion
        
        Raises:
            AssertionError: Internal error, abort
        """
        # Initialize a list of file paths to delete at the end.
        filestodelete = []

        # CHECK: Process and evalulate duplicate fingerprints.
        print("Checking database for duplicates")
        i = 0
        for filenames in self.generateDuplicateFilelists(self.shelvefile, threshhold=2, progressbar_allowed=(not interactive)):
            # filenames = sortDuplicatePaths(filenames)
            if interactive:
                # The user gets to pick the image to keep.
                # Print up a pretty menu.
                print()
                for i in range(0, len(filenames)):
                    print("{0}. {1}".format(i, filenames[i]))
                # Loop over the menu until the user selects a valid option
                good_ans = False
                while not good_ans:
                    # Show the choices
                    ans = input(
                        "\nEnter the number of the file to KEEP: (0) ('s' to skip) ")
                    try:
                        if ans.upper() == "S":
                            # Skip this image (don't delete anything)
                            # and also, for good measure, output the delete file.
                            good_ans = True
                            goingtokeep = "All."
                            goingtodelete = []
                            continue
                        if ans is "":
                            ans = 0

                        index = int(ans)
                        goingtokeep = filenames[index]
                        goingtodelete = filenames[:index] + \
                            filenames[(index + 1):]
                        good_ans = True
                    except ValueError:
                        print("Not a valid number. ")  # Have another go.
            else:  
                # Not interactive.
                # We keep the FIRST file in the sort.
                # We'll delete the rest.
                goingtokeep = filenames[0]
                goingtodelete = filenames[1:]
                if (goingtokeep is None or len(goingtokeep) == 0):
                    # Just in case.
                    for sym in [filenames, goingtokeep, goingtodelete]:
                        print(sym)
                    raise AssertionError("Internal logic consistancy error. Program instructed to consider ALL images with a given hash as extraneous. Please debug.")
            
            # However the method, add all our doomed files to the list.
            filestodelete += goingtodelete

            # And explain ourselves.
            print("\n\t* " + goingtokeep, *["\n\t  " + f for f in goingtodelete])
        return filestodelete

    def generateDuplicateFilelists(self, bundleHash=False, threshhold=1, sort=True, progressbar_allowed=True):
        """Generate lists of files which all have the same hash.
        
        Args:
            shelvefile (TYPE): Description
            bundleHash (bool, optional): Description
            threshhold (int, optional): Description
            quiet (TYPE, optional): Description
            sort (bool, optional): Description
            progressbar_allowed (bool, optional): Description
        
        Yields:
            tuple: (list, hash) OR
            list: File paths of duplicates
        """
        print("Generating information about duplicate images from database")

        with ju.RotatingHandler(self.shelvefile, basepath="databases", readonly=False) as db:

            pbar = None
            if progressbar_allowed:
                pbar = progressbar.ProgressBar(max_value=len(db.keys()), redirect_stdout=True)
                i = 0

            for h in db.keys():
                if pbar:
                    i += 1
                    pbar.update(i)

                # For each hash `h` and the list of filenames with that hash `filenames`:
                filenames = db[h]
                # filenames = [filepath for filepath in db[h] if os.path.isfile(filepath)]

                # Remove duplicate filenames
                if len(set(filenames)) < len(filenames):
                    print("Duplicate file names detected in hash {}, cleaning.".format(h))
                    db[h] = filenames = list(set(filenames))
                    # = freshening[h]
                # Verify that all these files exist.
                missing_files = []
                for filepath in (f for f in filenames if not os.path.isfile(f)):
                        missing_files.append(filepath)
                    # else:
                    #     if DEBUG_FILE_EXISTS:
                    #         print("GOOD {}".format(filepath))

                for filepath in missing_files:
                    filenames.remove(filepath)

                # if DEBUG_FILE_EXISTS:
                #     for filepath in filenames:
                #         assert os.path.isfile(filepath), filepath

                # If there is STILL more than one file with the hash:
                if sort and len(filenames) >= threshhold:
                    filenames = self.sortDuplicatePaths(filenames)
                if len(filenames) >= threshhold:
                    if not self.quiet:
                        print("Found {0} duplicate images for hash [{1}]".format(
                            len(filenames), h))
                    if bundleHash:
                        yield (filenames, h)
                    else:
                        yield filenames

        if pbar:
            pbar.finish()
