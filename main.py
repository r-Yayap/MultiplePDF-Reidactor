# main.py
"""

"""
import multiprocessing

import customtkinter as ctk
from gui import ReidactorGUI
from constants import INITIAL_WIDTH, INITIAL_HEIGHT, INITIAL_X_POSITION, INITIAL_Y_POSITION

class ReidactorApp:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Reidactor")
        self.root.geometry(f"{INITIAL_WIDTH}x{INITIAL_HEIGHT}+{INITIAL_X_POSITION}+{INITIAL_Y_POSITION}")
        self.gui = ReidactorGUI(self.root)

    def run(self):
        self.root.mainloop()

def main():
    app = ReidactorApp()
    app.run()

if __name__ == '__main__':
    multiprocessing.freeze_support()  # This helps PyInstaller handle multiprocessing.
    main()

