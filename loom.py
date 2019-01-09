#!/bin/python3

from time import sleep
import threading


def threadWait(threshhold, interval, quiet=False):
    if threshhold < 1:
        threshhold = 1
    while (threading.active_count() > threshhold):
        c = threading.active_count()
        if not quiet:
            print("Waiting for {} job{} to finish:".format(c, "s" if c > 1 else ""))
            print(threading.enumerate())
        sleep(interval)


def thread(*args, **kwargs):
    # args.get("target")()
    t = threading.Thread(*args, **kwargs)
    t.start()
    return


class Loom():
    def __init__(self):
        super(Loom, self).__init__()

        