import threading
import tkinter as tk
from tkinter.ttk import *
from CheckboxTreeview import CheckboxTreeview
from module.DateEntry import DateEntry as DateEntry
from module.Events import Events
from module.OF import Onlyfans
from module.OF import *

class MainWindow:
    def __init__(self, master):
        self.master = master
        self.master.title("OF Downloader")
        self.master.geometry("680x530")

        self.ComboBox = Combobox(master, state= "readonly",
                                 values = ["Active Subscriptions",
                                            "Expired Subscriptions",
                                            "All Subscriptions"],
                                width=32)
        self.ComboBox.bind("<<ComboboxSelected>>", self.refresh)
        self.ComboBox.current(0)
        self.ComboBox.place(x = 20, y = 15)

        self.TreeView = CheckboxTreeview(master, show="tree")
        self.TreeView.place(x = 20, y = 40, height = 300)

        vsb = Scrollbar(master, orient="vertical", command=self.TreeView.yview)
        vsb.place(x=220, y=40, height=300)
        self.TreeView.configure(yscrollcommand=vsb.set)

        self.ClearSelection = Button(master, text="Clear selection", command=self.Clear_Selection_T, width=13)
        self.ClearSelection.place(x = 20, y = 350)

        self.GetLinks = Button(master, text="Retrieve Links", command=self.Get_Links_T, width=13)
        self.GetLinks.place(x = 20, y = 380)

        self.Download = Button(master, text="Download Files", command=self.Download_Files_T)
        self.Download.place(x = 130, y = 380)
        self.Download.configure(state='disabled')

        self.Status = Label(master, text = "Status: Idle")
        self.Status.place(x = 20, y = 440)

        self.LogText = tk.Text(master, height = 18, width = 49)
        self.LogText.place(x = 240, y = 40)

        self.ProgressBar = Progressbar(master, orient="horizontal", length=400, mode="determinate")
        self.ProgressBar.place(x = 240, y = 350)
        self.ProgressBar["maximum"] = 100

        self.FilesLeft = Label(master, text = "Files download: 0 / 0", width=32)
        self.FilesLeft.place(x = 240, y = 380)

        self.TotalSizeLeft = Label(master, text = "0.00 B / 0.00 B", width=32, anchor="e")
        self.TotalSizeLeft.place(x = 440, y = 380)

        self.ProgressBarItem = Progressbar(master, orient="horizontal", length=400, mode="determinate")
        self.ProgressBarItem.place(x = 240, y = 410)
        self.ProgressBarItem["maximum"] = 100

        self.FileSizeLeft = Label(master, text = "0.00 B / 0.00 B", width=32, anchor="e")
        self.FileSizeLeft.place(x = 440, y = 440)

        self.events = Events()

        self.onlyfans = Onlyfans(self.events)
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
        elif choice == "All Subscriptions":
            all_sub = self.onlyfans.return_all_subs()
            self.list_subscribers(all_sub)
        else:
            active = self.onlyfans.return_active_subs()
            self.list_subscribers(active)
        self.ComboBox.selection_clear()

    def Clear_Selection_T(self):
        self.TreeView.clear_selection()

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

        self.events.display_event("Getting links", niveau_titre=1)
        self.Status.configure(text = "Status: Collecting Links ...")
        self.onlyfans.reset_download_size()
        self.onlyfans.clear_links()
        self.onlyfans.clear_array()
        self.ProgressBar['value'] =  0
        self.FilesLeft.configure(text = "Files download: 0 / 0")
        self.TotalSizeLeft.configure(text = "0.00 B / 0.00 B")
        self.ProgressBarItem['value'] =  0
        self.FileSizeLeft.configure(text = "0.00 B / 0.00 B")

        self.Download.configure(state='disabled')
        self.GetLinks.configure(state='disabled')
        
        for child in self.TreeView.get_children():
            flag = 0
            state = self.TreeView.item(child)["tags"][0]
            if state == "checked":
                ALL = (MESSAGES | PICTURES | VIDEOS | STORIES | ARCHIVED | AUDIO)
                tmp = { child : ALL}
                users.append(tmp)
            elif state == "unchecked":
                continue
            else:
                for c in self.TreeView.get_children(child):
                    if self.TreeView.item(c)['tags'][0] == 'checked':
                        if self.TreeView.item(c)['text'] == "Messages":
                            flag |= MESSAGES
                        elif self.TreeView.item(c)['text'] == "Pictures":
                            flag |= PICTURES
                        elif self.TreeView.item(c)['text'] == "Videos":
                            flag |= VIDEOS
                        elif self.TreeView.item(c)['text'] == "Archived":
                            flag |= ARCHIVED
                        elif self.TreeView.item(c)['text'] == "Audio":
                            flag |= AUDIO
                tmp = {child : flag}
                users.append(tmp)
                
        self.LogText.delete(1.0, tk.END)
        total_size = 0
        file_count = 0
        image_count = 0
        for u in users:
            for key, value in u.items():
                self.Status.configure(text = "Status: Collecting Links (" + key + ") ...")
                dict_return = self.onlyfans.get_user_info(key)
                if dict_return is None:
                    continue
                links_user = self.onlyfans.get_links(dict_return, value, index)
                self.display_info_user(links_user)
                file_count += links_user["file_count"]
                self.FilesLeft.configure(text = "Files download: 0 / " + str(file_count))
                total_size += links_user["user_file_size"]
                image_count += len(links_user["images"])
                self.TotalSizeLeft.configure(text = "0.00 B / " + self.onlyfans.File_Size_Str(total_size))
                index += 1

        self.display_info_end(file_count, total_size, image_count)

    def display_info_user(self, links):
        self.LogText.insert(tk.END, self.onlyfans.subscript_array(links["index"]) + ": \n")
        for type_file in TYPE_FILE:
            nb_links = len(links[type_file])
            if nb_links > 0:
                self.LogText.insert(tk.END, "   " + type_file + ' ' * (9 - len(type_file)) + ": " + str(nb_links))
                if type_file == "videos":
                    self.LogText.insert(tk.END, " (" + self.onlyfans.File_Size_Str(links["user_file_size"]) + ")\n")
                elif type_file == "images":
                    self.LogText.insert(tk.END, " (~" + self.onlyfans.File_Size_Str(nb_links * 1_000_000) + ")\n")
                else:
                    self.LogText.insert(tk.END, "\n")

        if links["file_count"] > 0:
            self.LogText.insert(tk.END, "             ------\n")
        self.LogText.insert(tk.END, "   Total    : " + str(links["file_count"]) + "\n")
        self.LogText.see(tk.END)

    def display_info_end(self, file_count, total_size, image_count):
        self.LogText.insert(tk.END, "\n\n")
        self.LogText.insert(tk.END, "Files to be downloaded: " + str(file_count) + "\n")
        self.LogText.insert(tk.END, "Download Size : " + self.onlyfans.File_Size_Str(total_size) + " (+ ~" + self.onlyfans.File_Size_Str(image_count * 1_000_000) + ")\n")

        self.events.display_event(
            "Getting links ... Completed",
            "     Files to be downloaded: " + str(file_count),
            "     Download Size (videos): " + self.onlyfans.File_Size_Str(total_size),
            niveau_titre=1
        )

        self.GetLinks.configure(state='normal')
        if file_count > 0:
            self.Download.configure(state='normal')
        else:
            self.Download.configure(state='disabled')
        self.Status.configure(text = "Status: Done ...")
        self.LogText.see(tk.END)
    
    def Download_Files(self):
        files = self.onlyfans.return_links()
        file_len = 0
        for user in files:
            file_len += user["file_count"]

        self.Status.configure(text = "Status: Downloading Files...")
        self.ProgressBar['value'] = 0
        self.ProgressBarItem['value'] = 0
        file_downloaded = 0

        self.events.display_event("Downloading files", niveau_titre=1)
        for user in files:
            user_folder = self.onlyfans.subscript_array(user["index"])
            if user["file_count"] > 0:
                self.onlyfans.create_dir(user_folder)
                self.events.display_event("Downloading file for user " + str(user_folder), niveau_titre=2)
                self.Status.configure(text = "Status: Downloading Files (" + str(user_folder) + ")...")
                for type_file in TYPE_FILE:
                    file_of_type = len(user[type_file])
                    if file_of_type > 0:
                        self.events.display_event("Downloading " + str(type_file))
                        nbFileUser = 0
                        for file in user[type_file]:
                            nbFileUser += 1
                            file_downloaded += 1
                            if file["isVideo"] and file["size"] > MIN_SIZE_SPECIAL_DISPLAY:   #10MB
                                self.events.display_event("Downloading " + type_file + " ... " + str(nbFileUser) + " / " + str(file_of_type) + " (" + self.onlyfans.File_Size_Str(file["size"]) + ")")
                                self.onlyfans.download(self, user_folder, file)
                                self.events.display_event("Downloading " + type_file + " ... " + str(nbFileUser) + " / " + str(file_of_type) + " (" + self.onlyfans.File_Size_Str(file["size"]) + ") ... Done")
                            else:
                                if nbFileUser % 50 == 0:
                                    self.events.display_event("Downloading " + type_file + " ... " + str(nbFileUser) + " / " + str(file_of_type))
                                self.onlyfans.download(self, user_folder, file)
                            self.FilesLeft.configure(text = "Files download: " + str(file_downloaded) + " / " + str(file_len))
                            self.onlyfans.insert_database(user["user_id"], file)
                        self.events.display_event("Downloading " + str(type_file) + " ... Done")
                self.events.display_event("Downloading file for user " + str(user_folder) + " ... Done")
                self.onlyfans.update_date_database(user["user_id"])
            # else:
            #     self.events.display_event("0 file for user " + str(user_folder), niveau_titre=2)

        self.FilesLeft.configure(text = "Files download: " + str(file_downloaded) + " / " + str(file_len) + " ... Done")
        self.Status.configure(text = "Status: Done ...")
        self.events.display_event("Downloading files ... Completed " + datetime.now().strftime("%Y-%m-%d"), niveau_titre=1)
                        
        self.onlyfans.clear_links()
        self.onlyfans.clear_array()
        self.onlyfans.clear_filter()
        self.GetLinks.configure(state='normal')
