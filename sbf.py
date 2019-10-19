import tkinter as tk
from tkinter import ttk


class SidebarFrame(tk.Frame):

    """Frame that manages the sidebar and user input
    """

    # Init and window management

    def __init__(self, parent, submitCallback, *args, **kwargs):
        """Args:
            parent (tk): Tk parent widget
            *args: Passthrough
            **kwargs: Passthrough
        """
        tk.Frame.__init__(self, *args, **kwargs)

        self.controller = parent
        self.submit = submitCallback
        # Initialize window
        self.initwindow()

    def reFocusEntry(self):
        self.entry.delete(0, last=tk.END)
        self.entry.focus()

    def initwindow(self):
        """Initialize widgets
        """
        inOrderRow = 0

        def rowInOrder():
            """Helper function to increment in-order elements"""
            nonlocal inOrderRow
            inOrderRow += 1
            return inOrderRow

        btn_ref = ttk.Button(self, text="Open", takefocus=False, command=self.controller.openDir)
        btn_ref.grid(row=rowInOrder(), sticky=tk.W)
        btn_ref = ttk.Button(self, text="Refresh", takefocus=False, command=(
            lambda: (self.controller.reloadDirContext(), self.controller.imageUpdate()))
        )
        btn_ref.grid(row=inOrderRow, sticky=tk.E)

        btn_back = ttk.Button(self, text="Prev", takefocus=False, command=self.controller.prevImage)
        btn_back.grid(row=rowInOrder(), sticky=tk.W)
        btn_skip = ttk.Button(self, text="Skip", takefocus=False, command=self.controller.nextImage)
        btn_skip.grid(row=inOrderRow, sticky=tk.E)

        def highlightEntry(parent):
            """Quick factory for entries that highlight"""
            return tk.Entry(parent, takefocus=True, highlightthickness=2)

        # Entry text field
        lab_context_label = ttk.Label(self, text="Move to folder ID:")
        lab_context_label.grid(row=rowInOrder())

        self.entry = highlightEntry(self)
        self.entry.bind("<Return>", self.submit)
        self.entry.bind("<KeyRelease>", self.processEntryInput)
        self.entry.grid(row=rowInOrder(), sticky="WE")
        self.reFocusEntry()

        # New folder entry
        lab_newfolder = ttk.Label(self, text="Move to new folder:")
        lab_newfolder.grid(row=rowInOrder())

        self.entry_newfolder = highlightEntry(self)
        self.entry_newfolder.bind("<Return>", self.controller.moveToFolder)
        self.entry_newfolder.grid(row=rowInOrder(), sticky="WE")

        # Rename
        lab_rename = ttk.Label(self, text="Rename")
        lab_rename.grid(row=rowInOrder())

        self.entry_rename = highlightEntry(self)
        self.entry_rename.grid(row=rowInOrder(), sticky="WE")
        self.entry_rename.bind("<Return>", self.controller.dorename)

        # context keys
        lab_context_label = ttk.Label(self, text="Folder IDs:")
        lab_context_label.grid(row=rowInOrder())

        # self.str_context = tk.StringVar()
        self.listbox_context = tk.Listbox(
            self, state=tk.DISABLED, takefocus=False, relief=tk.GROOVE)
        self.listbox_context.grid(row=rowInOrder(), sticky="nsew")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(inOrderRow, weight=1)

        settings_popup = tk.Menu(self, tearoff=0)

        self.fuzzy = tk.BooleanVar()
        settings_popup.add_checkbutton(label="Fuzzy search", variable=self.fuzzy)
        
        self.confident = tk.BooleanVar()
        settings_popup.add_checkbutton(label="Displace conflict targets", variable=self.confident)
        
        self.aggressive = tk.BooleanVar()
        settings_popup.add_checkbutton(label="Aggressive matching", variable=self.aggressive)
        self.auto_reload = tk.BooleanVar()
        self.auto_reload.set(True)
        settings_popup.add_checkbutton(label="Reload on change", variable=self.auto_reload)

        settings_popup.add_separator()
        settings_popup.add_command(label="Add Unsorted to base", command=self.controller.addUnsortedToBase)

        # settings_popup.add_separator()

        btn_settings = ttk.Button(self, text="Settings", takefocus=False)
        btn_settings.bind("<Button-1>", lambda event: settings_popup.tk_popup(event.x_root, event.y_root, 0))
        btn_settings.grid(row=rowInOrder(), sticky=tk.EW)
        self.combobox_sorter = ttk.Combobox(self, state="readonly", takefocus=False, values=[name for name in self.controller.sortkeys.keys()])
        self.combobox_sorter.bind("<<ComboboxSelected>>", self.on_adjust_sort)
        self.combobox_sorter.grid(row=rowInOrder(), sticky="WE")

        self.var_progbar_seek = tk.IntVar()
        self.progbar_seek = ttk.Scale(self, takefocus=False, variable=self.var_progbar_seek, command=self.on_adjust_seek)
        self.progbar_seek.grid(row=rowInOrder(), sticky="WE")

        self.var_progbar_prog = tk.IntVar()
        self.progbar_prog = ttk.Progressbar(self, variable=self.var_progbar_prog)
        self.progbar_prog.grid(row=rowInOrder(), sticky="WE")

        self.highlightListboxItems([])

    def highlightListboxItems(self, matches):
        """Highlight specific items in the listbox

        Args:
            matches (list): List of indexes to highlight
        """
        self.listbox_context.configure(state=tk.NORMAL)
        self.listbox_context.selection_clear(0, tk.END)
        if len(matches) == 0:
            self.listbox_context.configure(state=tk.DISABLED)
            return
        for index in matches:
            self.listbox_context.selection_set(index)
            self.listbox_context.see(index)

    def on_adjust_seek(self, event):
        self.controller.gotoImage(event)

    def on_adjust_sort(self, event):
        self.controller.sorter = self.controller.sortkeys[event.widget.get()]
        self.controller.resortImageList()
        # self.config(state=tk.NORMAL)

    def processEntryInput(self, event):
        """Process entry input, handling element styling and possible automatic submission.

        Args:
            event (TYPE): Tk entry event
        """
        GOOD = "#AAFFAA"
        BAD = "#FFAAAA"
        NORMAL = "#FFFFFF"

        fieldGet = event.widget.get()
        if event.keycode == 32:
            fieldGet = fieldGet[:-1]  # Delete space character

        if fieldGet == "":
            event.widget.configure(bg=NORMAL)
            self.highlightListboxItems([])
            self.controller.labelFileName()
            return
        bestFolders = self.controller.getBestFolders(fieldGet)
        bestFolderIndices = self.controller.getBestFolders(fieldGet, indexOnly=True)
        self.highlightListboxItems(bestFolderIndices)
        if len(bestFolderIndices) == 1:
            (bestfldrshort, bestfldrpath) = bestFolders[0]
            self.controller.str_curfile.set(bestfldrshort)
            event.widget.configure(bg=GOOD)
            if self.aggressive.get():
                self.submit(entry=fieldGet)
        else:
            # self.controller.labelFileName()
            self.controller.str_curfile.set(
                ", ".join([short for (short, l) in bestFolders])
            )
            event.widget.configure(bg=BAD)
