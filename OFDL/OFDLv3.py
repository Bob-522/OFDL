import os
import threading
import module.OF
import tkinter as tk
from tkinter.ttk import *
from module.OF import Onlyfans
from icons.checked import checked_icon
from icons.tristate import tristate_icon
from icons.unchecked import unchecked_icon
from module.DateEntry import DateEntry as DateEntry

class CheckboxTreeview(Treeview):
    def __init__(self, master=None, **kw):
        Treeview.__init__(self, master, **kw)

        self.im_checked = tk.PhotoImage(data=checked_icon)
        self.im_unchecked = tk.PhotoImage(data = unchecked_icon)
        self.im_tristate = tk.PhotoImage(data = tristate_icon)
        self.tag_configure("unchecked", image=self.im_unchecked)
        self.tag_configure("tristate", image=self.im_tristate)
        self.tag_configure("checked", image=self.im_checked)

        self.bind("<Button-1>", self.box_click, True)

    def insert(self, parent, index, iid=None, **kw):
        """ same method as for standard treeview but add the tag 'unchecked'
            automatically if no tag among ('checked', 'unchecked', 'tristate')
            is given """
        if not "tags" in kw:
            kw["tags"] = ("unchecked",)
        elif not ("unchecked" in kw["tags"] or "checked" in kw["tags"]
                  or "tristate" in kw["tags"]):
            kw["tags"] = ("unchecked",)
        Treeview.insert(self, parent, index, iid, **kw)

    def check_descendant(self, item):
        """ check the boxes of item's descendants """
        children = self.get_children(item)
        for iid in children:
            self.item(iid, tags=("checked",))
            self.check_descendant(iid)

    def check_ancestor(self, item):
        """ check the box of item and change the state of the boxes of item's
            ancestors accordingly """
        self.item(item, tags=("checked",))
        parent = self.parent(item)
        if parent:
            children = self.get_children(parent)
            b = ["checked" in self.item(c, "tags") for c in children]
            if False in b:
                # at least one box is not checked and item's box is checked
                self.tristate_parent(parent)
            else:
                # all boxes of the children are checked
                self.check_ancestor(parent)

    def tristate_parent(self, item):
        """ put the box of item in tristate and change the state of the boxes of
            item's ancestors accordingly """
        self.item(item, tags=("tristate",))
        parent = self.parent(item)
        if parent:
            self.tristate_parent(parent)

    def uncheck_descendant(self, item):
        """ uncheck the boxes of item's descendant """
        children = self.get_children(item)
        for iid in children:
            self.item(iid, tags=("unchecked",))
            self.uncheck_descendant(iid)

    def uncheck_ancestor(self, item):
        """ uncheck the box of item and change the state of the boxes of item's
            ancestors accordingly """
        self.item(item, tags=("unchecked",))
        parent = self.parent(item)
        if parent:
            children = self.get_children(parent)
            b = ["unchecked" in self.item(c, "tags") for c in children]
            if False in b:
                # at least one box is checked and item's box is unchecked
                self.tristate_parent(parent)
            else:
                # no box is checked
                self.uncheck_ancestor(parent)

    def box_click(self, event):
        """ check or uncheck box when clicked """
        x, y, widget = event.x, event.y, event.widget
        elem = widget.identify("element", x, y)
        if "image" in elem:
            # a box was clicked
            item = self.identify_row(y)
            tags = self.item(item, "tags")
            if ("unchecked" in tags) or ("tristate" in tags):
                self.check_ancestor(item)
                self.check_descendant(item)
            else:
                self.uncheck_descendant(item)
                self.uncheck_ancestor(item)

class MainWindow:
    def __init__(self, master):
        self.master = master
        self.master.title("OF Downloader")
        self.master.geometry("680x530")
        self.sort = False

        self.TreeView = CheckboxTreeview(master, show="tree")
        self.TreeView.place(x = 20, y = 40, height = 300)

        self.Subscriptions = Label(master, text = "Active Subscriptions")
        self.Subscriptions.place(x = 20, y = 20)

        self.Status = Label(master, text = "Status: Idle")
        self.Status.place(x = 20, y = 440)

        vsb = Scrollbar(master, orient="vertical", command=self.TreeView.yview)
        vsb.place(x=220, y=40, height=300) #height=200+20

        self.TreeView.configure(yscrollcommand=vsb.set)

        self.ComboBox = Combobox(master, state= "readonly",
                                 values = ["Active Subscriptions",
                                            "Expired Subscriptions",
                                            "All Subscriptions"])

        self.ComboBox.bind("<<ComboboxSelected>>", self.refresh)
        self.ComboBox.current(0)
        self.ComboBox.place(x = 20, y = 350)

        self.GetLinks = Button(master, text="Retrieve Links", command=self.Get_Links_T)
        self.GetLinks.place(x = 20, y = 400)

        self.Download = Button(master, text="Download Files", command=self.Download_Files_T)
        self.Download.place(x = 140, y = 400)
        self.Download.configure(state='disabled')

        self.LogText = tk.Text(master, height = 18, width = 48)
        self.LogText.place(x = 240, y = 40)

        self.ProgressBar = Progressbar(master, orient="horizontal", length=350, mode="determinate")
        self.ProgressBar.place(x = 250, y = 350)
        self.ProgressBar["maximum"] = 100

        self.FilesLeft = Label(master, text = "Files download: 0 / 0")
        self.FilesLeft.place(x = 250, y = 380)

        self.ProgressBarItem = Progressbar(master, orient="horizontal", length=350, mode="determinate")
        self.ProgressBarItem.place(x = 250, y = 410)
        self.ProgressBarItem["maximum"] = 100

        self.onlyfans = Onlyfans()
        self.onlyfans.load_config()
        self.onlyfans.get_subscriptions()
        self.Sub_List = self.onlyfans.return_active_subs()
        self.list_subscribers(self.Sub_List)

    def list_subscribers(self, lst):
        for x in range(0, len(lst)):
            self.TreeView.insert("", x, lst[x], text=lst[x])
            if lst[x] not in self.Sub_List:
                self.TreeView.insert(lst[x], 0, text="Messages")
            else:
                self.TreeView.insert(lst[x], 0, text="Messages")
                self.TreeView.insert(lst[x], 1, text="Pictures")
                self.TreeView.insert(lst[x], 2, text="Videos")
                self.TreeView.insert(lst[x], 3, text="Archived")
                self.TreeView.insert(lst[x], 4, text="Audio")

    def link_size(self, links):
        size = 0
        for link in links:
            size += link["size"]
        return size

    def refresh(self, event):
        choice = self.ComboBox.get()
        self.TreeView.delete(*self.TreeView.get_children())
        if choice == "Expired Subscriptions":
            exp = self.onlyfans.return_expired_subs()
            self.list_subscribers(exp)
            self.Subscriptions.configure(text = "Expired Subscriptions")
        elif choice == "All Subscriptions":
            all_sub = self.onlyfans.return_all_subs()
            self.list_subscribers(all_sub)
            self.Subscriptions.configure(text = "All Subscriptions")
        else:
            active = self.onlyfans.return_active_subs()
            self.list_subscribers(active)
            self.Subscriptions.configure(text = "Active Subscriptions")
        self.ComboBox.selection_clear()

    def Get_Links_T(self):
        threading.Thread(target=self.Get_Links).start()
        self.GetLinks.configure(state='disabled')

    def Download_Files_T(self):
        threading.Thread(target=self.Download_Files).start()
        self.Download.configure(state='disabled')
        self.GetLinks.configure(state='disabled')

    def Get_Links(self):
        users = []
        index = 0

        self.Status.configure(text = "Status: Collecting Links ...")
        self.onlyfans.reset_download_size()
        self.onlyfans.clear_links()
        self.onlyfans.clear_array()

        self.Download.configure(state='disabled')
        self.GetLinks.configure(state='disabled')
        
        for child in self.TreeView.get_children():
            flag = 0
            state = self.TreeView.item(child)["tags"][0]
            if state == "checked":
                ALL = (module.OF.MESSAGES | module.OF.PICTURES | module.OF.VIDEOS | 
                       module.OF.STORIES | module.OF.ARCHIVED | module.OF.AUDIO)
                tmp = { child : ALL}
                users.append(tmp)
            elif state == "unchecked":
                continue
            else:
                for c in self.TreeView.get_children(child):
                    if self.TreeView.item(c)['tags'][0] == 'checked':
                        if self.TreeView.item(c)['text'] == "Messages":
                            flag |= module.OF.MESSAGES
                        elif self.TreeView.item(c)['text'] == "Pictures":
                            flag |= module.OF.PICTURES
                        elif self.TreeView.item(c)['text'] == "Videos":
                            flag |= module.OF.VIDEOS
                        elif self.TreeView.item(c)['text'] == "Archived":
                            flag |= module.OF.ARCHIVED
                        elif self.TreeView.item(c)['text'] == "Audio":
                            flag |= module.OF.AUDIO
                tmp = {child : flag}
                users.append(tmp)
                
        self.LogText.delete(1.0, tk.END)
        for u in users:
            for key, value in u.items():
                dict_return = self.onlyfans.get_user_info(key)
                if dict_return is None:
                    continue
                self.onlyfans.get_links(dict_return, value, index)
                self.display_info(self.onlyfans.return_links(), False)
                index += 1
                
        links = self.onlyfans.return_links()
        if len(links) == 0:
            self.GetLinks.configure(state='normal')
            self.Status.configure(text = "Status: Done ...")
            return

        self.display_info(links, True)

    def display_info(self, links, is_completed):
        total_size = 0
        file_count = 0
        types_file = ["messages", "stories", "images", "videos", "audio", "archived"]
        
        self.LogText.delete(1.0, tk.END)
        for user in links:
            user_file_size = 0
            user_name = self.onlyfans.subscript_array(user["index"]) + ": \n"
            self.LogText.insert(tk.END, user_name)
            for type_file in types_file:
                user_links = user[type_file]
                user_file_size = user["user_file_size"]
                self.LogText.insert(tk.END, "   " + type_file + ": " + str(len(user_links)) + "\n")

            self.LogText.insert(tk.END, "   Total: " + str(user["file_count"]) + "\n")
            self.LogText.insert(tk.END, "   Total size: " + self.onlyfans.File_Size_Str(user_file_size) + "\n")
            file_count += user["file_count"]
            total_size += user_file_size
               
        if is_completed:
            self.LogText.insert(tk.END, "\n\n")
            self.LogText.insert(tk.END, "Files to be downloaded: " + str(file_count) + "\n")
            self.LogText.insert(tk.END, "Download Size (videos): " + self.onlyfans.File_Size_Str(total_size) + "\n")
            print("============================================================")
            print("Getting links ... Completed")
            print("     Files to be downloaded: " + str(file_count))
            print("     Download Size (videos): " + self.onlyfans.File_Size_Str(total_size))
            print("============================================================")

            self.GetLinks.configure(state='normal')
            if file_count > 0:
                self.Download.configure(state='normal')
            else:
                self.Download.configure(state='disabled')
            self.Status.configure(text = "Status: Done ...")
    
    def Download_Files(self):
        files = self.onlyfans.return_links()
        file_len = 0
        for user in files:
            file_len += user["file_count"]

        self.Status.configure(text = "Status: Downloading Files...")
        self.ProgressBar['value'] = 0
        self.ProgressBarItem['value'] = 0
        file_downloaded = 0
        types_file = ["messages", "stories", "images", "videos", "audio", "archived"]

        print("------------------------------------------------------------")
        print("Downloading files")
        print("------------------------------------------------------------")
        for user in files:
            user_folder = self.onlyfans.subscript_array(user["index"])
            if user["file_count"] > 0:
                self.onlyfans.create_dir(user_folder)
                print("------------------------------------------------------------")
                print("Downloading file for user " + str(user_folder))
                print("------------------------------------------------------------")
                for type_file in types_file:
                    file_of_type = len(user[type_file])
                    if file_of_type > 0:
                        print("Downloading " + str(type_file))
                        nbFileUser = 0
                        for file in user[type_file]:
                            nbFileUser += 1
                            file_downloaded += 1
                            if file["isVideo"] and file["size"] > 10_485_760:   #10MB
                                print("Downloading " + type_file + " ... " + str(nbFileUser) + " / " + str(file_of_type) + " (" + self.onlyfans.File_Size_Str(file["size"]) + ")")
                                self.onlyfans.download(self, user_folder, file)
                                print("Downloading " + type_file + " ... " + str(nbFileUser) + " / " + str(file_of_type) + " (" + self.onlyfans.File_Size_Str(file["size"]) + ") ... Done")
                            elif nbFileUser % 50 == 0:
                                print("Downloading " + type_file + " ... " + str(nbFileUser) + " / " + str(file_of_type))
                                self.onlyfans.download(self, user_folder, file)
                            self.FilesLeft.configure(text = "Files download: " + str(file_downloaded) + " / " + str(file_len))
                            self.onlyfans.insert_database(user["user_id"], user["index"], file)
                print("Downloading file for user " + str(user_folder) + " ... Done")
            else:
                print("------------------------------------------------------------")
                print("0 file for user " + str(user_folder))
                print("------------------------------------------------------------")

        self.FilesLeft.configure(text = "Files download: " + str(file_downloaded) + " / " + str(file_len) + " ... Done")
        self.Status.configure(text = "Status: Done ...")
        print("============================================================")
        print("Downloading files ... Completed")
        print("============================================================")
                        
        self.onlyfans.clear_links()
        self.onlyfans.clear_array()
        self.onlyfans.clear_filter()
        self.GetLinks.configure(state='normal')

if __name__ == "__main__":
    try:
        os.mkdir("Files")
    except FileExistsError:
        pass
    root = tk.Tk()
    
    MainWind = MainWindow(root)
    root.mainloop()
