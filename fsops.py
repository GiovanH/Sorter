import os


def doFileRename(oldFileName, newFileName, confident=False):
    try:
        os.rename(oldFileName, newFileName)
    except FileExistsError as e:
        if confident:
            print("Renaming conflicting file", e.filename2)
            "DISPLACED_"
            bits = e.filename2.split("\\")
            doFileRename(e.filename2, "\\".join(bits[:-1]) +
                         "\\DISPLACED_" + bits[-1])
            os.rename(oldFileName, newFileName)
