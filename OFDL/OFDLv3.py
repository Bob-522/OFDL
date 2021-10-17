import os
import tkinter as tk
from MainWindow import MainWindow

if __name__ == "__main__":
    try:
        os.mkdir("Files")
    except FileExistsError:
        pass
    root = tk.Tk()
    
    MainWind = MainWindow(root)
    root.mainloop()
