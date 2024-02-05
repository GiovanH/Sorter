import tkinter as tk
from tkinter import ttk

# from .sort import FileSorter

from typing import *

class SidebarFrame(tk.Frame):

    """Frame that manages the sidebar and user input
    """

    # Init and window management

    def __init__(self, parent, submitCallback: Callable[..., None], *args, **kwargs) -> None:
        """Args:
            parent (tk): Tk parent widget
            *args: Passthrough
            **kwargs: Passthrough
        """
        tk.Frame.__init__(self, *args, **kwargs)

        self.controller = parent

        self.submit: Callable[..., None] = submitCallback
        # Initialize window
        self.initwindow()

    def reFocusEntry(self) -> None:
        self.entry.delete(0, last=tk.END)
        self.entry.focus()

    def initwindow(self) -> None:
        """Initialize widgets
        """
        inOrderRow = 0

        def rowInOrder() -> int:
            """Helper function to increment in-order elements"""
            nonlocal inOrderRow
            inOrderRow += 1
            return inOrderRow

        btn_open = ttk.Button(self, text="Open", takefocus=False, command=self.controller.openDir)
        btn_open.grid(row=rowInOrder(), sticky=tk.W)
        btn_filter = ttk.Button(self, text="Filter", takefocus=False, command=self.controller.changeMatchGlobs)
        btn_filter.grid(row=inOrderRow, sticky=tk.E)

        btn_ref = ttk.Button(self, text="Refresh", takefocus=False, command=(
            lambda: (self.controller.reloadDirContext(), self.controller.imageUpdate()))
        )
        btn_ref.grid(row=rowInOrder(), sticky="WE")

        # btn_back = ttk.Button(self, text="Prev", takefocus=False, command=self.controller.prevImage)
        # btn_back.grid(row=rowInOrder(), sticky=tk.W)
        # btn_skip = ttk.Button(self, text="Skip", takefocus=False, command=self.controller.nextImage)
        # btn_skip.grid(row=inOrderRow, sticky=tk.E)

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

        lab_rename = ttk.Label(self, text="Rename Prefix")
        lab_rename.grid(row=rowInOrder())

        self.entry_rename = highlightEntry(self)
        self.entry_rename.grid(row=rowInOrder(), sticky="WE")
        self.entry_rename.bind("<Return>", self.controller.doPrefixRename)

        # context keys
        lab_context_label = ttk.Label(self, text="Folder IDs:")
        lab_context_label.grid(row=rowInOrder())

        # self.str_context = tk.StringVar()
        self.listbox_context = tk.Listbox(
            self, state=tk.DISABLED, takefocus=False, relief=tk.GROOVE)
        self.listbox_context.grid(row=rowInOrder(), sticky="nsew")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(inOrderRow, weight=1)



        self.strv_prev_query = tk.StringVar(value="<None>")
        ttk.Label(self, text="Ctrl+. to repeat:").grid(row=rowInOrder())
        ttk.Label(self, textvariable=self.strv_prev_query).grid(row=rowInOrder())
        self.entry.bind("<Control-period>", self.doRepeat)
        # self.entry.bind("<Control-slash>", self.doRepeat)

        settings_popup = tk.Menu(self, tearoff=0)

        for key, (var, label) in self.controller.settings.items():
            settings_popup.add_checkbutton(label=label, variable=var)

        settings_popup.add_separator()
        settings_popup.add_command(label="Add Unsorted to base", command=self.controller.addUnsortedToBase)
        settings_popup.add_command(label="Commit deleted files now", command=self.controller.trash.flush)

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

    def doRepeat(self, event):
        self.controller.doRepeat()

    def processEntryInput(self, event):
        """Process entry input, handling element styling and possible automatic submission.

        Args:
            event (TYPE): Tk entry event
        """
        GOOD = "#AAFFAA"
        BAD = "#FFAAAA"
        NORMAL = "#FFFFFF"

        query = event.widget.get()
        if event.keycode == 32:
            query = query[:-1]  # Delete space character

        if query == "":
            event.widget.configure(bg=NORMAL)
            self.highlightListboxItems([])
            self.controller.updateLabelFileName()
            return

        # Use controller folder to "predict" action and highlight
        best_folder_list = self.controller.getBestFolders(query)

        self.highlightListboxItems([ir.index for ir in best_folder_list])

        # Preview target, state
        if len(best_folder_list) == 1:
            best_folder = best_folder_list[0]
            self.controller.str_curfile.set(best_folder.label)
            event.widget.configure(bg=GOOD)

            # Automatically submit if aggressive
            if self.controller.settings["aggressive"][0].get():
                self.submit(entry=query)
        else:
            self.controller.str_curfile.set(
                ", ".join([li.label for li in best_folder_list])
            )
            event.widget.configure(bg=BAD)
