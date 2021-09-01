import json
from tkinter.constants import TRUE
import requests
import math
import os
import sqlite3
from sqlite3 import Error
import time as time2
import hashlib
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

MESSAGES = 0b1000000
PICTURES = 0b0100000
VIDEOS = 0b0010000
STORIES = 0b0000100
ARCHIVED = 0b0000010
AUDIO = 0b0000001

class Onlyfans:
    def __init__(self):
        self.active_subs = []
        self.expired_subs = []
        self.all_subs = []
        self.links = []
        self.current_sub_list = []
        self.all_files_size = 0
        self.current_dl = 0
        self.config = {}
        self.filter_list = []
        self.session = requests.Session()
        self.conn = self.get_database()

    def get_database(self):
        conn = None
        try:
            conn = sqlite3.connect('onlyfans.sqlite3.db', check_same_thread=False)
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS `entries`"
                      "(`id`	TEXT, `url` TEXT, `userid` TEXT, `username` TEXT, `filename` TEXT);")
        except Error as e:
            print (e)
        return conn
    
    def load_config(self):
        try:
            self.f = open("config.json")
            self.config = json.load(self.f)
            self.f.close()
            if len(self.config) > 0:
                self.set_values()
        except FileNotFoundError:
            pass

    def set_values(self):
        self.user_agent = self.config["user-agent"]
        self.sess = self.config["cookie"]
        self.reload_sub = self.config["reload-sub"]
        auth_id = self.sess
        auth_id = auth_id[auth_id.find("auth_id=") + 8:]
        auth_id = auth_id[0:auth_id.find(";"):]
        self.auth_id = str(auth_id)

    def get_sess(self):
        sess = self.sess
        sess = sess[sess.find("sess=") + 5:]
        sess = sess[0:sess.find(";"):]
        return sess

    def create_headers(
        self,
        dynamic_rules: dict[str, Any],
        auth_id: Union[str, int],
        user_agent: str = "",
        link: str = "https://onlyfans.com/",
    ):
        headers: dict[str, Any] = {}
        headers["user-agent"] = user_agent
        headers["referer"] = link
        headers["user-id"] = str(auth_id)
        headers["x-bc"] = ""
        for remove_header in dynamic_rules["remove_headers"]:
            headers.pop(remove_header)
        headers["app-token"] = dynamic_rules["app_token"]
        return headers

    def create_signed_headers(self, link: str, auth_id: int, dynamic_rules: dict):
            # Users: 300000 | Creators: 301000
            final_time = str(int(round(time2.time())))
            path = urlparse(link).path
            query = urlparse(link).query
            path = path if not query else f"{path}?{query}"
            a = [dynamic_rules["static_param"], final_time, path, str(auth_id)]
            msg = "\n".join(a)
            message = msg.encode("utf-8")
            hash_object = hashlib.sha1(message)
            sha_1_sign = hash_object.hexdigest()
            sha_1_b = sha_1_sign.encode("ascii")
            checksum = (
                sum([sha_1_b[number] for number in dynamic_rules["checksum_indexes"]])
                + dynamic_rules["checksum_constant"]
            )
            headers = {}
            headers["sign"] = dynamic_rules["format"].format(sha_1_sign, abs(checksum))
            headers["time"] = final_time
            return headers

    def prepareRequest(self, link: str):
        referer = f"https://onlyfans.com/api2/v2/users/me"
        headers = self.create_headers(self.dynamic_rules, self.auth_id, self.user_agent, referer)
        headers |= self.create_signed_headers(link, 0, self.dynamic_rules)
        headers |= {
            'accept': 'application/json, text/plain, */*',
            'Cookie' : self.sess,
            "Connection": "keep-alive"
        }
        self.session.headers = headers

    def get_subscriptions(self):
        if len(self.config) == 0:
            config = {}
            config["cookie"] = "cookie"
            config["user-agent"] = "user-agent"
            config["reload-sub"] = False
            with open("config.json", "w") as f:
                json.dump(config, f)
            print("File config.json created. Fill info and restart app.")
            return

        dynamic_rules = requests.get("https://raw.githubusercontent.com/DATAHOARDERS/dynamic-rules/main/onlyfans.json").json()
        with open("dynamicRules.json", "w") as f:
            json.dump(dynamic_rules, f)
        self.dynamic_rules = dynamic_rules

        meurl = f"https://onlyfans.com/api2/v2/users/me"
        self.prepareRequest(meurl)
        r = self.session.get(meurl)
        if r.status_code != 200:
            print ("Login failed")
            print (r.content)
            return

        if self.reload_sub:
            print("------------------------------------------------------------")
            print("Reloading subs from server")
            print("------------------------------------------------------------")
            if os.path.exists("Subs") == False:
                os.mkdir("Subs")

            subscription_link = "https://onlyfans.com/api2/v2/subscriptions/subscribes?limit=99&offset="

            sub_temp = subscription_link.replace("offset=", "offset=0")
            json_result = self.make_json_server_request(sub_temp)

            index = 0
            while len(json_result) > 0:
                print("Loading subs (part " + str(index + 1) + ")")
                with open("Subs/Following_" + str(index) + ".subs", "w") as f:
                    json.dump(json_result, f)
                for sub in json_result:
                    if sub["subscribedBy"] == True and sub["username"] not in self.active_subs:
                        self.active_subs.append(sub["username"])
                    else:
                        if sub["username"] not in self.expired_subs:
                            self.expired_subs.append(sub["username"])
                    if sub["username"] not in self.all_subs:
                        self.all_subs.append(sub["username"])
                if len(json_result) == 99:
                    print("Pause " + str(index + 1) + " (5 secondes)")
                    time2.sleep(5)

                    index += 1
                    sub_temp = subscription_link.replace("offset=", "offset=" + str(index * 99))
                    json_result = self.make_json_server_request(sub_temp)
                else:
                    json_result = []

        else:
            print("------------------------------------------------------------")
            print("Reloading subs from files")
            print("------------------------------------------------------------")
            if os.path.exists("Subs") == False:
                print("Subs folder not found. You must load from serveur before realoding from files. Change config.json > 'reload-sub' to reload from server.")

            if os.path.exists("Subs/Following_0.subs") == False:
                print("Subs file not found. You must load from serveur before realoding from files. Change config.json > 'reload-sub' to reload from server.")

            index = 0
            while os.path.exists("Subs/Following_" + str(index) + ".subs"):
                print("Loading file " + str(index + 1))
                with open("Subs/Following_" + str(index) + ".subs", "r") as r:
                    json_result = json.load(r)
                    for sub in json_result:
                        if sub["subscribedBy"] == True and sub["username"] not in self.active_subs:
                            self.active_subs.append(sub["username"])
                        else:
                            if sub["username"] not in self.expired_subs:
                                self.expired_subs.append(sub["username"])
                        if sub["username"] not in self.all_subs:
                            self.all_subs.append(sub["username"])
                index += 1
        print("Loading complete ... " + str(len(self.all_subs)) + " subscriptions loaded")

        self.active_subs.sort()
        self.expired_subs.sort()
        self.all_subs.sort()

    def make_json_server_request(self, url):
        self.prepareRequest(url)
        response = self.session.get(url)
        return json.loads(response.content)

    def return_active_subs(self):
        return self.active_subs

    def return_expired_subs(self):
        return self.expired_subs

    def return_all_subs(self):
        return self.all_subs

    def get_user_info(self, username):
        link = 'https://onlyfans.com/api2/v2/users/' + username
        return_dict = {}

        self.prepareRequest(link)
        r = self.session.get(link)
        json_data = json.loads(r.text)
        if json_data is None:
            return
        if "error" in json_data:
            print (json_data)
            return
        return_dict["photosCount"] = json_data["photosCount"]
        return_dict["videosCount"] = json_data["videosCount"]
        return_dict["audiosCount"] = json_data["audiosCount"]
        return_dict["archivedPostsCount"] = json_data["archivedPostsCount"]
        return_dict["id"] = json_data["id"]
        return_dict["username"] = username

        self.current_sub_list.append(return_dict)

        return return_dict

    def reset_download_size(self):
        self.current_dl = 0
        self.all_files_size = 0

    def File_Size_Str(self, size):
        unit = ["KB", "MB", "GB", "TB"]
        count = -1
        if size < 1024:
            return str(size) + "B"
        else:
            while size >= 1024:
                size /= 1024
                count += 1
        return str('%.2f' % size) + unit[count]

    def get_links(self, info, flag, index):
        if info is None:
            return
        user_id = info["id"]
        offsets = []
        messages = []
        images = []
        videos = []
        audio = []
        stories = []
        archived = []
        filesNames = []
        total_count = info["photosCount"] + info["videosCount"] + info["audiosCount"]
        user_file_size = 0
        isExistingUser = self.user_exist_database(user_id)

        offset_range = math.ceil(total_count / 100)
        offsets = list(range(offset_range))

        message_api = "https://onlyfans.com/api2/v2/chats/"+str(user_id)+"/messages?limit=100&offset=&order=desc"
        post_api = "https://onlyfans.com/api2/v2/users/"+str(user_id)+"/posts?limit=100&offset=&order=publish_date_desc"
        stories_api = "https://onlyfans.com/api2/v2/users/"+str(user_id)+"/stories?limit=100&offset=0&order=desc"
        archive_api = "https://onlyfans.com/api2/v2/users/"+ str(user_id)+"/posts/archived?limit=100&offset=0&order=publish_date_desc"
        audio_api = "https://onlyfans.com/api2/v2/users/"+str(user_id)+"/posts/audios?limit=10&offset=&order=publish_date_desc"

        print("------------------------------------------------------------")
        print("Getting links for " + str(info["username"]))
        print("------------------------------------------------------------")

        if flag & MESSAGES:
            print("Loading messages")
            js_message = []
            offset = 0

            json_data = self.make_json_server_request(message_api)
            js_message.append(json_data)
            while json_data['hasMore'] == True:
                message_temp = message_api.replace("offset=", "offset=" + str(offset * 100))
                json_data = self.make_json_server_request(message_temp)
                js_message.append(json_data)
                offset += 1
                if offset % 5 == 0:
                    print("Loading messages ... " + str(offset * 100))
            print("Loading messages ... Done")

            print("Counting messages")
            for j in js_message:
                if "list" in j:
                    json_list = j["list"]
                    for sec in json_list:
                        if "media" in sec:
                            media = sec["media"]
                            date = sec["createdAt"]
                            for m in media:
                                if "src" in m and "type" in m:
                                    id_post = sec["id"]
                                    type_src = m["type"]
                                    src = m["src"]
                                    if src is None:
                                        continue
                                    m_info = m["info"]
                                    m_info = m_info["source"]
                                    file_size = m_info["size"]
                                    fileName = self.get_file_names(src)
                                    
                                    if type_src == "photo" and not self.file_names_exists_and_add_if_not(filesNames, fileName):
                                        #self.all_files_size += file_size
                                        file_dict = {"source" : src, "size": file_size, "index" : index, "id": id_post,
                                                     "date" : date, "flag" : MESSAGES, "isVideo" : False, "fileName" : fileName}
                                        messages.append(file_dict)
                                    elif type_src == "video" and not self.file_names_exists_and_add_if_not(filesNames, fileName) and self.is_new_file(isExistingUser, user_id, fileName):
                                        if file_size == 0:
                                            r = self.session.head(src)
                                            if "Content-Length" in r.headers:
                                                file_size = int(r.headers["Content-Length"])
                                        self.all_files_size += file_size
                                        file_dict = {"source" : src, "size": file_size, "index" : index, "id": id_post,
                                                     "date" : date, "flag" : MESSAGES, "isVideo" : True, "fileName" : fileName}
                                        messages.append(file_dict)
            print("Counting messages ... Done")

        if flag & PICTURES or flag & VIDEOS:
            print("Loading pictures and videos")
            json_data = []
            for n in offsets:
                offset = str(n * 100)
                post_tmp = post_api.replace("offset=", "offset=" + offset)

                self.prepareRequest(post_tmp)
                r = self.session.get(post_tmp)
                json_data.append(json.loads(r.text))
                print("Loading pictures and videos ... " + str(offset) + " / " + str(total_count))
            nbItemJson_data = len(json_data)

            print("Loading stories")
            js = self.make_json_server_request(stories_api)
            print("Loading stories ... done")
            print("Counting stories")
            for j in js:
                if "media" in j and "createdAt" in j:
                    m = j["media"]
                    date = j["createdAt"]
                    post_id = j["id"]
                    for media in m:
                        if "source" in media and "type" in media:
                            file_details = media["source"]
                            type_src = media["type"]
                            if "source" in file_details and "size" in file_details:
                                src = file_details["source"]
                                file_size = file_details["size"]
                                fileName = self.get_file_names(src)
                                if type_src == "photo" and not self.file_names_exists_and_add_if_not(filesNames, fileName):
                                    #self.all_files_size += file_size
                                    file_dict = {"source" : src, "size": file_size, "index" : index, "id": post_id,
                                                    "date" : date, "flag" : STORIES, "isVideo" : False, "fileName" : fileName}
                                    stories.append(file_dict)
                                elif type_src == "video" and not self.file_names_exists_and_add_if_not(filesNames, fileName) and self.is_new_file(isExistingUser, user_id, fileName):
                                    file_size = file_details["size"]
                                    if file_size == 0:
                                        r = self.session.head(src)
                                        if "Content-Length" in r.headers:
                                            file_size = int(r.headers["Content-Length"])
                                    self.all_files_size += file_size
                                    file_dict = {"source" : src, "size": file_size, "index" : index, "id": post_id,
                                                    "date" : date, "flag" : STORIES, "isVideo" : True, "fileName" : fileName}
                                    stories.append(file_dict)
                                
            print("Counting stories ... done")
        
        if flag & PICTURES:
            print("Counting pictures")
            nbCounted = 0
            for j in json_data:
                for js in j:
                    if "postedAt" in js and "media" in js and "id" in js:
                        date = js["postedAt"]
                        media = js["media"]
                        id_post = js["id"]
                        for m in media:
                            if "source" in m:
                                file_details = m["source"]
                                if "size" in file_details and "source" in file_details:
                                    file_size = file_details["size"]
                                    type_src = file_details["source"]
                                    if type_src is None or not type_src.startswith('https://cdn'):
                                        continue
                                    fileName = self.get_file_names(type_src)
                                    if (".jpg" in type_src or ".jpeg" in type_src or ".png" in type_src) and not self.file_names_exists_and_add_if_not(filesNames, fileName):
                                        #self.all_files_size += file_size
                                        file_dict = {"source" : type_src, "size": file_size, "index" : index, "id": id_post,
                                             "date" : date, "flag" : PICTURES, "isVideo" : False, "fileName" : fileName}
                                        images.append(file_dict)
                nbCounted += 1
                print("Counting pictures ... " + str(nbCounted) + " / " + str(nbItemJson_data))
            print("Counting pictures ... Done")
            
        if flag & VIDEOS:
            print("Counting videos")
            nbCounted = 0
            for j in json_data:
                for js in j:
                    if "postedAt" in js and "media" in js and "id" in js:
                        date = js["postedAt"]
                        media = js["media"]
                        id_post = js["id"]
                        for m in media:
                            if "source" in m:
                                file_details = m["source"]
                                if "size" in file_details and "source" in file_details:
                                    file_size = file_details["size"]
                                    type_src = file_details["source"]
                                    if type_src is None or not type_src.startswith('https://cdn'):
                                        continue
                                    fileName = self.get_file_names(type_src)
                                    if ".mp4" in type_src and not self.file_names_exists_and_add_if_not(filesNames, fileName) and self.is_new_file(isExistingUser, user_id, fileName):
                                        if file_size == 0:
                                            r = self.session.head(type_src)
                                            if "Content-Length" in r.headers:
                                                file_size = int(r.headers["Content-Length"])      
                                        self.all_files_size += file_size
                                        file_dict = {"source" : type_src, "size": file_size, "index" : index, "id": id_post,
                                             "date" : date, "flag" : VIDEOS, "isVideo" : True, "fileName" : fileName}
                                        videos.append(file_dict)
                nbCounted += 1
                print("Counting videos ... " + str(nbCounted) + " / " + str(nbItemJson_data))
            print("Counting videos ... Done")

        if flag & ARCHIVED:
             cnt = info["archivedPostsCount"]
             if cnt > 0:
                print("Loading and counting archives")
                off_range = math.ceil(cnt / 100)
                offsets_arch = list(range(off_range))
                nbCounted = 0

                for off in offsets_arch:
                    nbCounted += 1
                    print("Loading and counting archives ... " + str(nbCounted) + " / " + str(off_range))
                    arch_temp = archive_api.replace("offset=", "offset=" + str(off))

                    self.prepareRequest(arch_temp)
                    r = self.session.get(arch_temp)
                    js = json.loads(r.text)

                    for j in js:
                        if "postedAt" in j and "media" in j and "id" in j:
                            date = j["postedAt"]
                            media = j["media"]
                            id_post = j["id"]
                            for m in media:
                                if "source" in m:
                                    file_details = m["source"]
                                    if "size" in file_details and "source" in file_details:
                                        file_size = file_details["size"]
                                        type_src = file_details["source"]
                                    if type_src is None or not type_src.startswith('https://cdn'):
                                        continue
                                    fileName = self.get_file_names(type_src)
                                    if ".mp4" in type_src and not self.file_names_exists_and_add_if_not(filesNames, fileName) and self.is_new_file(isExistingUser, user_id, fileName):
                                        if file_size == 0:
                                            r = self.session.head(type_src)
                                            if "Content-Length" in r.headers:
                                                file_size = int(r.headers["Content-Length"])
                                        self.all_files_size += file_size
                                        file_dict = {"source" : type_src, "size": file_size, "index" : index, "id": id_post,
                                                "date" : date, "flag" : ARCHIVED, "isVideo" : True, "fileName" : fileName}
                                        archived.append(file_dict)
                                    if (".jpg" in type_src or ".jpeg" in type_src or ".png" in type_src) and not self.file_names_exists_and_add_if_not(filesNames, fileName):
                                        #self.all_files_size += file_size
                                        file_dict = {"source" : type_src, "size": file_size, "index" : index, "id": id_post,
                                                "date" : date, "flag" : ARCHIVED, "isVideo" : False, "fileName" : fileName}
                                        archived.append(file_dict)
                print("Loading and counting archives ... Done")

        if flag & AUDIO:
            cnt = info["audiosCount"]
            if cnt > 0:
                print("Loading and counting audio")
                off_range = math.ceil(cnt / 10)
                offsets_arch = list(range(off_range))
                nbCounted = 0

                for off in offsets_arch:
                    nbCounted += 1
                    print("Loading and counting audio ... " + str(off) + " / " + str(off_range))
                    audio_temp = audio_api.replace("offset=", "offset=" + str(off))
                    js = self.make_json_server_request(audio_temp)
                    for j in js:
                        if "postedAt" in j and "media" in j and "id" in j:
                            date = j["postedAt"]
                            media = j["media"]
                            id_post = j["id"]
                            for m in media:
                                if "source" in m:
                                    file_details = m["source"]
                                    if "size" in file_details and "source" in file_details:
                                        file_size = file_details["size"]
                                        type_src = file_details["source"]
                                    if type_src is None or not type_src.startswith('https://cdn'):
                                        continue
                                    if ".mp3" in type_src:
                                        #self.all_files_size += file_size
                                        fileName = self.get_file_names(type_src)
                                        file_dict = {"source" : type_src, "size": file_size, "index" : index, "id": id_post,
                                                    "date" : date, "flag" : AUDIO, "isVideo" : False, "fileName" : fileName}
                                        audio.append(file_dict)
                print("Loading and counting audio ... Done")

        if isExistingUser:
            print("Validating duplicate")
            self.validate_duplicate(user_id, messages, "messages")
            self.validate_duplicate(user_id, stories, "stories")
            self.validate_duplicate(user_id, images, "images")
            self.validate_duplicate(user_id, videos, "videos")
            self.validate_duplicate(user_id, audio, "audio")
            self.validate_duplicate(user_id, archived, "archived")
            print("Validating duplicate ... Done")
        else:
            print("Validating duplicate ... Skipped (Never downloaded " + str(info["username"]) + ")")

        links_info = {
            "user_id" : user_id, "index" : index, 
            "file_count" : len(messages) + len(stories) + len(images) + len(videos) + len(audio) + len(archived),
            "messages" : messages, "stories" : stories, "images" : images,
            "videos" : videos, "audio" : audio, "archived" : archived }
        types_file = ["messages", "stories", "images", "videos", "audio", "archived"]
        for type_file in types_file:
            for file in links_info[type_file]:
                user_file_size += file["size"]
        links_info["user_file_size"] = user_file_size
        self.links.append(links_info)
        print("Getting links for " + str(info["username"]) + " ... Done")
        print("     Total files: " + str(links_info["file_count"]))
        print("     Total size (videos): " + self.File_Size_Str(links_info["user_file_size"]))

    def is_new_file(self, isExistingUser, user_id, fileName):
        if not isExistingUser:
            return True
        else:
            return not self.select_database(user_id, fileName)

    def validate_duplicate(self, user_id, user_links, type_links):
        nbTotal = len(user_links)
        if nbTotal > 0:
            nbValider = 0
            list_copy = user_links.copy()
            print("Validating duplicate " + type_links + " ... 0 / " + str(nbTotal))
            for link in list_copy:
                if not link["isVideo"] or self.select_database(user_id, link["fileName"]):
                    user_links.remove(link)
                    self.all_files_size -= link["size"]
                nbValider += 1
                if nbValider % 100 == 0:
                    print("Validating duplicate " + type_links + " ... " + str(nbValider) + " / " + str(nbTotal))
            print("Validating duplicate " + type_links + " ... Done")

    def file_names_exists_and_add_if_not(self, fileNames, fileName):
        if fileName in fileNames:
            return True
        else:
            fileNames.append(fileName)
            return False

    def get_file_names(self, source):
        return source.split('/')[-1].split('?')[0]

    def user_exist_database(self, userid):
        try:
            c = self.conn.cursor()
            c.execute("SELECT * FROM entries WHERE userid = ? LIMIT 1", (userid,))
            data = c.fetchall()
            if len(data) > 0:
                return True
            return False
        except:
            return False

    def select_database(self, userid, filename):
        try:
            c = self.conn.cursor()
            c.execute("SELECT * FROM entries where userid = ? AND filename = ? LIMIT 1", (userid, filename,))
            data = c.fetchall()
            if len(data) > 0:
                return True
            return False
        except:
            return False

    def insert_database(self, id_user, username, file):
        url = file["source"].split('?')[0]
        post_id = file["id"]
        File_Name = url.split('/')[-1]
        try:
            c = self.conn.cursor()
            c.execute('INSERT INTO entries VALUES(?,?,?,?,?)', (str(post_id), str(url), str(id_user), str(username),
                                                                  str(File_Name)))
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass

    def return_links(self):
        return self.links
    
    def clear_links(self):
        if len(self.links) > 0:
            del self.links[:]

    def subscript_array(self, ind):
        if ind < len(self.current_sub_list):
            return self.current_sub_list[ind]["username"]
        return ""

    def return_user_array(self):
        return self.current_sub_list

    def clear_array(self):
        if len(self.current_sub_list) > 0:
            del self.current_sub_list[:]

    def clear_filter(self):
        if len(self.filter_list) > 0:
            del self.filter_list[:]

    def download(self, obj, folder, file_links):
        file_name = file_links["source"]
        flag = file_links["flag"]
        File_Extension = file_name.split('.')[-1]
        File_Extension = File_Extension.split('?')[0]
        File_Name = file_name.split('/')[-1]
        File_Name = File_Name.split('?')[0]
        total_download = self.all_files_size
        directory = ""

        if flag & MESSAGES:
            directory = "Messages"
        elif flag & VIDEOS or flag & PICTURES:
            directory = "Posts"
        elif flag & STORIES:
            directory = "Stories"
        elif flag & ARCHIVED:
            directory = "Archived"

        self.create_dir(folder + "/" + directory)
        obj.ProgressBarItem['value'] =  0
        type_file = ""

        if File_Extension == "jpg" or File_Extension == "jpeg" or File_Extension == "png":
            type_file = "Images"
        elif File_Extension == "mp4":
            type_file = "Videos"
        elif File_Extension == "mp3":
            type_file = "Audio"
        else:
            type_file = "Misc"

        self.create_dir(folder + "/" + directory + "/" + type_file)
        if os.path.isfile("Files/" + folder + "/" + directory + "/" + type_file + "/" + File_Name) == False:
            with open("Files/" + folder + "/" + directory + "/" + type_file + "/" + File_Name, "wb") as file:
                response = self.session.get(file_name, stream=True)
                tmp = response.headers.get('content-length')
                if tmp is None:
                    file.write(response.content)
                    if file_links["isVideo"]:
                        self.current_dl += file_links["size"]
                else:
                    total_length = int(tmp)
                    current_file_dl = 0
                    for data in response.iter_content(chunk_size=4096):
                        current_file_dl += len(data)
                        self.current_dl += len(data)
                        obj.ProgressBar['value'] =  (self.current_dl / total_download) * 100
                        if file_links["isVideo"] and file_links["size"] > 10_485_760:   #10MB
                            obj.ProgressBarItem['value'] =  (current_file_dl / total_length) * 100
                        file.write(data)
                    if file_links["isVideo"] and file_links["size"] > 10_485_760:   #10MB
                        obj.ProgressBarItem['value'] =  100
                    if current_file_dl != file_links["size"]:
                        self.current_dl += file_links["size"] - current_file_dl
                        obj.ProgressBar['value'] =  (self.current_dl / total_download) * 100

    def create_dir(self, dirname):
        try:
            if os.path.exists("Files/" + dirname) == False:
                os.mkdir("Files/" + dirname)
        except FileExistsError:
            pass
