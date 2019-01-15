#!/bin/python3
"""Summary
"""

from time import sleep
import threading

necessary_threads = 1


def extraThreads():
    """Returns:
        int: Number of threads, not including main.
    """
    return threading.active_count() - necessary_threads


def threadWait(threshhold=0, interval=1, quiet=True, use_pbar=True):
    """Wait for threads to complete.

    Args:
        threshhold (int): Wait until at most X extra threads exist.
        interval (int, optional): Seconds between checking thread status
        quiet (bool, optional): Print detailed thread status
        use_pbar (bool, optional): Show progressbar
    """
    if threshhold < 0:
        # Short circuit
        return

    pbar = None
    if use_pbar and (extraThreads() > threshhold):
        import progressbar
        _max = extraThreads() - threshhold
        print("Finishing {} background jobs.".format(_max))
        pbar = progressbar.ProgressBar(max_value=_max, redirect_stdout=True)

    while (extraThreads() > threshhold):
        c = extraThreads() - threshhold

        if pbar:
            pbar.update(_max - c)

        if not quiet:
            print("Waiting for {} job{} to finish:".format(c, "s" if c > 1 else ""))
            print(threading.enumerate())

        sleep(interval)

    if pbar:
        pbar.finish()


def thread(target, *args, **kwargs):
    """Initialize and start a thread

    Args:
        target (function): Task to complete
        *args: Passthrough to threading.Thread
        **kwargs: threading.Thread
    """
    t = threading.Thread(target=target, *args, **kwargs)
    t.start()


class Spool(object):

    """A spool is a queue of threads.
    This is a simple way of making sure you aren't running too many threads at one time.
    At intervals, determined by `delay`, the spooler (if on) will start threads from the queue.
    The spooler can start multiple threads at once.

    Attributes:
        delay (num): How long to wait between waves
        start (bool): Start spooling when created, y/n.
        cverbose (bool): If called as a context manager, verbose finish.
        cverbose (bool): If called as a context manager, finish with progress bar.
    """

    def __init__(self, quota, delay=1, start=True):
        super(Spool, self).__init__()
        self.queue = []
        self.running_threads = []
        self.quota = quota
        self.delay = delay
        self.background_spool = False
        self.flushlock = False

        if start:
            self.start()

    def start(self):
        """Begin spooling threads, if not already doing so. 
        """
        if not self.background_spool:
            self.background_spool = True
            self.spoolThread = threading.Thread(target=self.spoolLoop, name="Spooler")
            self.spoolThread.start()

    def __str__(self):
        return "{} at {}: {} threads queued, {}/{} currently running".format(type(self), hex(id(self)), len(self.queue), self.getNoRunningThreads(), self.quota)

    def spoolLoop(self, delay=None, verbose=False, cb=None):
        """Periodically start additional threads, if we have the resources to do so.
        This function is intended to be run as a thread.
        If run as a blocking call, self.background_spool should be False, in order to allow peaceful termination. 

        Args:
            verbose (bool, optional): Report progress towards queue completion.
            delay (num): Optionally override the normal delay.
        """
        if delay is None:
            delay = self.delay

        while self.background_spool or (self.queue and len(self.queue) > 0):
            self.doSpool(verbose=verbose, cb=cb)        
            if cb:
                cb()
            sleep(delay)

    def doSpool(self, verbose=False, cb=None):
        """Spools new threads until the queue empties or the quota fills.
        
        Args:
            verbose (bool, optional): Verbose output
        """
        # Unlock if done
        if self.flushlock and self.getNoRunningThreads() == 0:
            self.flushlock = False

        # If we can start threads...
        if self.queue and not self.flushlock:
            # Start threads until we've hit quota, or until we're out of threads.
            while len(self.queue) > 0 and (self.getNoRunningThreads() < self.quota):
                self.startThread(self.queue.pop(0))

        if verbose:
            print(self.running_threads)
            print("{} threads queued, {}/{} currently running.".format(len(self.queue), self.getNoRunningThreads(), self.quota))

    def startThread(self, newThread):
        """Start and track a new thread.
        
        Args:
            newThread (Thread): Thread with a .start() method.
        """
        self.running_threads.append(newThread)
        newThread.start()

    def flush(self):
        """Finish all current threads before starting any new ones. 
        """
        self.flushlock = True

    def queue_append(self, *args, **kwargs):
        """Add an item to the queue, with the caution that the queue may not exist.
        """
        try:
            self.queue.append(*args, **kwargs)
        except AttributeError as e:
            assert self.queue is None
            raise TypeError("finish() has been called, and the queue has been destroyed.")

    def enqueue(self, target, *args, **kwargs):
        """Add a thread to the back of the queue.

        Args:
            Passthrough to threading.Thread. 
            target (function)
            name (str)
            args (tuple)
            kwargs (dict)
            group
        """
        self.queue_append(threading.Thread(target=target, *args, **kwargs))

    def enqueueSeries(self, targets):
        def closure():
            for target in targets:
                target()
        self.queue_append(threading.Thread(target=closure))

    def finish(self, resume=False, verbose=False, delay=None, use_pbar=True):
        """Block and complete all threads in queue.

        Args:
            resume (bool, optional): If true, spooling resumes after. Otherwise, spooling stops.

        Args, spool:
            verbose (bool, optional): Report progress towards queue completion.
            use_pbar (bool, optional): Graphically display progress towards queue completion.
            delay (num): Optionally override the normal delay.
        """
        self.background_spool = False

        cb = None

        _max = self.getNoRunningThreads() + len(self.queue)
        if use_pbar and _max > 0:
            def getProgressValue():
                q = (len(self.queue) if self.queue else 0)
                return (_max - (self.getNoRunningThreads() + q))
            (pbar, cb) = self.startProgressBar(_max, getProgressValue)

        self.spoolLoop(cb=cb, delay=delay, verbose=verbose)
        assert len(self.queue) == 0, "Finished without deploying all threads"

        self.queue = None  # Disallow adding to a queue that will not be revisited.
        self.waitForNoRunningThreads(cb)

        assert self.getNoRunningThreads() == 0

        if cb:
            cb(True)
            # pbar.finish()

        if resume:
            self.queue = []  # Create a fresh queue
            self.start()

    def startProgressBar(self, _max, updateValue, redirect_stdout=True):
        """Create a new progress bar and provide objects and callbacks.
        
        Args:
            _max (TYPE): Description
            updateValue (TYPE): Description
        
        Returns:
            Tuple: (pbar, callback)
        """
        import progressbar
        pbar = progressbar.ProgressBar(max_value=_max, redirect_stdout=redirect_stdout)

        def callback(force=False):
            v = updateValue()
            if v == _max: 
                pbar.finish()
                return True
            else:
                pbar.update(v)
                return False or force
        return (pbar, callback)

    def waitForNoRunningThreads(self, cb=None):
        while self.getNoRunningThreads() > 0:
            if cb:
                cb()
            sleep(self.delay)

    def setDelay(self, newDelay):
        self.delay = newDelay

    def prune(self):
        """Accurately count number of "our" running threads.
        This removes references to non-alive threads."""
        self.running_threads = [
            thread
            for thread in self.running_threads
            if thread.is_alive()
        ]

    def getNoRunningThreads(self):
        """Accurately count number of "our" running threads.
        This prunes dead threads and returns a count of live threads."""
        self.prune()
        return len(self.running_threads)


class SpoolWrapper(Spool):
    def __init__(self, *args, cverbose=False, cpbar=False, **kwargs):
        super(SpoolWrapper, self).__init__(*args, **kwargs)

        self.cverbose = cverbose
        self.cpbar = cpbar

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.finish(resume=False, verbose=self.cverbose, use_pbar=self.cpbar)


class FastSpool(Spool):
    def __init__(self, *args, **kwargs):
        super(FastSpool, self).__init__(*args, **kwargs)
        self.background_spool = False
        self.refresh_callbacks = []

    def start(self):
        pass

    def doCallbacks(self):
        done = []
        for f in self.refresh_callbacks:
            r = f()
            if r:
                done.append(f)
        for d in done:
            self.refresh_callbacks.remove(d)

    def refresh(self, *args, **kwargs):
        self.doCallbacks()
        self.doSpool()

    def startThread(self, newThread):
        self.running_threads.append(newThread)
        newThread.start()
        self.doCallbacks()

    def startProgressBar(self, *args, **kwargs):
        (pbar, callback) = super(FastSpool, self).startProgressBar(*args, **kwargs)
        self.refresh_callbacks.append(callback)
        return (pbar, callback)

    def enqueue(self, target, args=tuple(), kwargs=dict(), *threadingargs, **threadingkwargs):
        def closure():
            target(*args, **kwargs)
            self.refresh()
        self.queue_append(threading.Thread(target=closure, *threadingargs, **threadingkwargs))

    def enqueueSeries(self, targets):
        def closure():
            for target in targets:
                target()
            self.refresh()
        self.queue_append(threading.Thread(target=closure))


class FastSpoolWrapper(FastSpool):
    def __init__(self, *args, cverbose=False, cpbar=False, **kwargs):
        super(FastSpoolWrapper, self).__init__(*args, **kwargs)

        self.cverbose = cverbose
        self.cpbar = cpbar

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.finish(resume=False, verbose=self.cverbose, use_pbar=self.cpbar)


def test():
    """Test threading functionality
    """
    from time import sleep
    from random import random

    work = []

    def dillydally(i, wait):
        sleep(wait)
        work.append(i)
        print("Job", i, "done.")

    Spool = FastSpool
    SpoolWrapper = FastSpoolWrapper

    # with Spool(8, start=True, cpbar=True) as s:

    def test_simple_finish():
        print("Test simple w/ finish.")
        work.clear()
        s = Spool(2, start=True)
        for i in range(0, 10):
            s.enqueue(target=dillydally, args=(i, random()))

        sleep(2)
        print("Finish.")
        s.finish(use_pbar=True)
        print(work, len(work))
        assert len(work) == 10

        work.clear()
        s = Spool(2, start=True)
        for i in range(0, 10):
            s.enqueue(target=dillydally, args=(i, random()))

        sleep(2)
        print("Quiet Finish.")
        s.finish(use_pbar=False)
        print(work, len(work))
        assert len(work) == 10

    def test_wrapper():
        print("Test wrapper.")

        work.clear()
        with SpoolWrapper(2, cpbar=True) as w:
            for i in range(0, 10):
                w.enqueue(target=dillydally, args=(i, 3 + random()))

            sleep(2)
            print("Finish.")
        print(work, len(work))
        assert len(work) == 10

        work.clear()
        with SpoolWrapper(2, cpbar=True, start=False) as w:
            for i in range(0, 10):
                w.enqueue(target=dillydally, args=(i, random()))

            sleep(2)
            print("Delayed Finish.")
        print(work, len(work))
        assert len(work) == 10

        work.clear()
        with SpoolWrapper(2, cpbar=False) as w:
            for i in range(0, 10):
                w.enqueue(target=dillydally, args=(i, random()))

            sleep(2)
            print("Quiet finish.")
        print(work, len(work))
        assert len(work) == 10

    def test_midflush():
        print("Test mid-work flush.")
        work.clear()
        s = Spool(2, start=True)
        
        s.enqueue(target=dillydally, args=(1, 1))
        s.enqueue(target=dillydally, args=(2, 3))
        s.enqueue(target=dillydally, args=(3, 0))
        s.enqueue(target=dillydally, args=(4, 2))
        s.flush()
        s.enqueue(target=dillydally, args=(10, 1))
        s.enqueue(target=dillydally, args=(20, 3))
        s.enqueue(target=dillydally, args=(30, 0))
        s.enqueue(target=dillydally, args=(40, 2))

        sleep(5)
        print("Finish.")
        s.finish(use_pbar=True)
        print(work, len(work))
        assert len(work) == 8

    # test_simple_finish()
    test_wrapper()
    # test_midflush()

    # threadWait(5, 0.8)
    # print("Finished", done, "jobs")


TimedSpool = Spool 
TimedSpoolWrapper = SpoolWrapper

# Spool = FastSpool
# SpoolWrapper = FastSpoolWrapper


if __name__ == '__main__':
    test()
