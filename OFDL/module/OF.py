import json
import requests
import math
import os
import sqlite3
from sqlite3 import Error
import time
from datetime import datetime, timedelta
import hashlib
from typing import Any, List, Union
from urllib.parse import urlparse
from dateutil import parser
from .Events import Events

MESSAGES = 0b1000000
PICTURES = 0b0100000
VIDEOS = 0b0010000
STORIES = 0b0000100
ARCHIVED = 0b0000010
AUDIO = 0b0000001

MIN_SIZE_SPECIAL_DISPLAY = 10_485_760   #10MB
TYPE_FILE = ["messages", "stories", "images", "videos", "audio", "archived"]

class Onlyfans:
    def __init__(self, events: Events):
        self.events = events
        self.active_subs = []
        self.expired_subs = []
        self.all_subs = []
        self.links = []
        self.current_sub_list = []
        self.all_files_size = 0
        self.current_dl = 0
        self.current_dl_other = 0
        self.config = {}
        self.filter_list = []
        self.session = requests.Session()
        self.conn = self.get_database()

    def get_database(self):
        conn = None
        try:
            conn = sqlite3.connect('onlyfans.sqlite3.db', check_same_thread=False)
            c = conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS __MigrationsHistory (
                    id TEXT PRIMARY KEY
                );""")
            c.execute("SELECT id FROM __MigrationsHistory ORDER BY Id")
            migrations = []
            for migration in c.fetchall():
                migrations.append(migration[0])

            if len(migrations) == 0: #For backward compatibility
                c.execute("""
                    CREATE TABLE IF NOT EXISTS entries (
                        id TEXT,
                        url TEXT,
                        userid TEXT,
                        username TEXT,
                        filename TEXT
                    );""")


            if "202109071745_AddTableSubscriptions" not in migrations:
                self.events.display_event('Applying migration 202109071745_AddTableSubscriptions')
                c.execute("""
                    CREATE TABLE Subscriptions (
                        userid INTEGER PRIMARY KEY,
                        username TEXT,
                        isExpired BOOLEAN NOT NULL CHECK (paid IN (0, 1)),
                        expireDate TEXT,
                        paid BOOLEAN NOT NULL CHECK (paid IN (0, 1)),
                        dateLastScrape TEXT
                    );""")
                c.execute("""
                    INSERT INTO Subscriptions (
                        userid,
                        isExpired,
                        paid
                    )
                    SELECT DISTINCT
                        userid,
                        0,
                        0
                    FROM
                        entries
                    """)
                c.execute("INSERT INTO __MigrationsHistory VALUES('202109071745_AddTableSubscriptions')")
                conn.commit()

            if "202109071835_ReplacingTableEntries" not in migrations:
                self.events.display_event('Applying migration 202109071835_ReplacingTableEntries')
                c.execute("""
                    CREATE TABLE ItemScrape (
                        id INTEGER,
                        userid INTEGER,
                        filename TEXT,
                        dateItem TEXT,
                        CONSTRAINT PK_ItemScrape PRIMARY KEY (userid, filename),
                        FOREIGN KEY (userid) REFERENCES Subscriptions(userid)
                    );""")
                c.execute("""
                    INSERT INTO ItemScrape (
                        id,
                        userid,
                        filename
                    )
                    SELECT
                        MIN(id),
                        userid,
                        filename
                    FROM
                        entries
                    GROUP BY
                        userid,
                        filename
                    """)
                c.execute("DROP TABLE entries")
                c.execute("INSERT INTO __MigrationsHistory VALUES('202109071835_ReplacingTableEntries')")
                conn.commit()

            if "202109092334_PassingVaccum" not in migrations:
                self.events.display_event('Applying migration 202109092334_PassingVaccum')
                c.execute("VACUUM")
                c.execute("INSERT INTO __MigrationsHistory VALUES('202109092334_PassingVaccum')")
                conn.commit()
        except Error as e:
            self.events.display_event(str(e))
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
        if "last-reload-sub" in self.config:
            self.last_reload_sub = datetime.strptime(self.config["last-reload-sub"], "%Y-%m-%d %H:%M:%S")
        else:
            self.last_reload_sub = None
        auth_id = self.sess
        auth_id = auth_id[auth_id.find("auth_id=") + 8:]
        auth_id = auth_id[0:auth_id.find(";"):]
        self.auth_id = str(auth_id)
        self.x_bc = self.config["x-bc"]

    def get_sess(self):
        sess = self.sess
        sess = sess[sess.find("sess=") + 5:]
        sess = sess[0:sess.find(";"):]
        return sess

    def create_headers(self, dynamic_rules: dict[str, Any], auth_id: Union[str, int], x_bc:str, user_agent: str = "", link: str = "https://onlyfans.com/"):
        headers: dict[str, Any] = {}
        headers["user-agent"] = user_agent
        headers["referer"] = link
        headers["user-id"] = str(auth_id)
        headers["x-bc"] = x_bc
        for remove_header in dynamic_rules["remove_headers"]:
            headers.pop(remove_header)
        headers["app-token"] = dynamic_rules["app_token"]
        return headers

    def create_signed_headers(self, link: str, auth_id: int, dynamic_rules: dict):
        # Users: 300000 | Creators: 301000
        final_time = str(int(round(time.time())))
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
        headers = self.create_headers(self.dynamic_rules, self.auth_id, self.x_bc, self.user_agent, referer)
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
            config["x-bc"] = "x-bc"
            with open("config.json", "w") as f:
                json.dump(config, f)
            self.events.display_event("File config.json created. Fill info and restart app.")
            return

        #dynamic_rules = requests.get("https://raw.githubusercontent.com/DIGITALCRIMINALS/dynamic-rules/main/onlyfans.json").json()
        #dynamic_rules = requests.get("https://raw.githubusercontent.com/DATAHOARDERS/dynamic-rules/main/onlyfans.json").json()
        dynamic_rules = requests.get("https://raw.githubusercontent.com/betoalanis/Dynamic-Rules/main/dynamic-rules.json").json()
        
        with open("dynamicRules.json", "w") as f:
            json.dump(dynamic_rules, f)
        self.dynamic_rules = dynamic_rules

        meurl = f"https://onlyfans.com/api2/v2/users/me"
        self.prepareRequest(meurl)
        r = self.session.get(meurl)
        if r.status_code != 200:
            self.events.display_event("Login failed")
            self.events.display_event(str(r.content))
            return

        if self.last_reload_sub == None or self.last_reload_sub + timedelta(days=2) < datetime.now():
            if self.last_reload_sub == None:
                self.events.display_event("Loading subs from server", niveau_titre=2)
            else:
                self.events.display_event("Subsciption list older than 2 days, reloading from server", niveau_titre=2)
            if os.path.exists("Subs") == False:
                os.mkdir("Subs")

            subscription_link = "https://onlyfans.com/api2/v2/subscriptions/subscribes?limit=99&offset="
            sub_temp = subscription_link.replace("offset=", "offset=0")
            json_result = self.make_json_server_request(sub_temp)
            index = 0
            while len(json_result) > 0:
                self.events.display_event("Loading subs (part " + str(index + 1) + ", " + str(len(json_result)) + " users)")
                with open("Subs/Following_" + str(index) + ".subs", "w") as f:
                    json.dump(json_result, f)

                for server_sub in json_result:
                    sub = {
                        'userid': server_sub["id"],
                        'username': server_sub["username"],
                        'isExpired': server_sub["subscribedIsExpiredNow"],
                        'expiration': None,
                        'paid': 0
                    }
                    if server_sub["subscribePrice"] != 0:
                        sub["expiration"] = parser.parse(server_sub["subscribedByExpireDate"]).strftime("%Y-%m-%d %H:%M:%S")
                        sub["paid"] = server_sub["currentSubscribePrice"] != None and server_sub["currentSubscribePrice"] > 0
                    self.update_sub_database(sub)
                    self.load_one_sub(sub)

                index += 1
                sub_temp = subscription_link.replace("offset=", "offset=" + str(index * 99))
                json_result = self.make_json_server_request(sub_temp)

            config = {}
            config["cookie"] = self.config["cookie"]
            config["user-agent"] = self.config["user-agent"]
            config["x-bc"] = self.config["x-bc"]
            config["last-reload-sub"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("config.json", "w") as f:
                json.dump(config, f)
            self.events.display_event("File config.json updated.")

        else:
            self.events.display_event("Reloading subs from database", niveau_titre=2)
            if os.path.exists("Subs") == False:
                self.events.display_event("Subs folder not found. You must load from serveur before realoding from files. Change config.json > 'reload-sub' to reload from server.")

            if os.path.exists("Subs/Following_0.subs") == False:
                self.events.display_event("Subs file not found. You must load from serveur before realoding from files. Change config.json > 'reload-sub' to reload from server.")

            index = 0
            while os.path.exists("Subs/Following_" + str(index) + ".subs"):
                self.events.display_event("Loading file " + str(index + 1))
                with open("Subs/Following_" + str(index) + ".subs", "r") as r:
                    json_result = json.load(r)
                    for database_sub in json_result:
                        sub = {
                            'userid': database_sub["id"],
                            'username': database_sub["username"],
                            'isExpired': database_sub["subscribedIsExpiredNow"],
                            'expiration': None,
                            'paid': 0
                        }
                        if database_sub["subscribePrice"] != 0:
                            sub["expiration"] = parser.parse(database_sub["subscribedByExpireDate"]).strftime("%Y-%m-%d %H:%M:%S")
                            sub["paid"] = database_sub["currentSubscribePrice"] != None and database_sub["currentSubscribePrice"] > 0
                        self.load_one_sub(sub)
                index += 1
        self.events.display_event("Loading complete ... " + str(len(self.all_subs)) + " subscriptions loaded")

        self.active_subs.sort()
        self.expired_subs.sort()
        self.all_subs.sort()

    def load_one_sub(self, sub):
        if sub["isExpired"] == False and (sub["expiration"] == None or datetime.strptime(sub["expiration"], "%Y-%m-%d %H:%M:%S") > datetime.now()):
            self.active_subs.append(sub["username"])
        else:
            self.expired_subs.append(sub["username"])
        self.all_subs.append(sub["username"])

    def make_json_server_request(self, url, nomFichier=None, request_delay=0):
        if nomFichier is not None:
            cache_path = nomFichier + ".json"
            if os.path.isfile(cache_path) and time.time() - os.path.getmtime(cache_path) < 24 * 60 * 60:
                with open(cache_path, "r") as f:
                    return json.load(f)

        if request_delay:
            time.sleep(request_delay)
        self.prepareRequest(url)
        response = self.session.get(url)
        loadedJson = json.loads(response.content)
        if nomFichier is not None:
            if not os.path.isdir(os.path.dirname(nomFichier)):
                os.makedirs(os.path.dirname(nomFichier))
            with open(cache_path, "w+") as f:
                json.dump(loadedJson, f)
        return loadedJson

    def return_active_subs(self):
        return self.active_subs

    def return_expired_subs(self):
        return self.expired_subs

    def return_all_subs(self):
        return self.all_subs

    def get_user_info(self, username):
        link = 'https://onlyfans.com/api2/v2/users/' + username
        return_dict = {}

        json_data = self.make_json_server_request(link, "./Temps/" + username + "/user_info")
        if json_data is None:
            return
        if "error" in json_data:
            self.events.display_event(str(json_data))
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
        self.current_dl_other = 0
        self.all_files_size = 0

    def File_Size_Str(self, size):
        unit = [" B", " KB", " MB", " GB", " TB"]
        count = 0
        while size >= 1024:
            size /= 1024
            count += 1
        return str('%.2f' % size) + unit[count]

    def get_links(self, info, flag, index):
        user_id = info["id"]
        messages = []
        images = []
        videos = []
        audio = []
        stories = []
        archived = []
        filesNames = set()
        total_count = info["photosCount"] + info["videosCount"] + info["audiosCount"]
        user_file_size = 0
        username = str(info["username"])
        isExistingUser = self.user_exist_database(user_id)

        message_api = "https://onlyfans.com/api2/v2/chats/"+str(user_id)+"/messages?limit=100&offset=&order=desc"
        post_api = "https://onlyfans.com/api2/v2/users/"+str(user_id)+"/posts?limit=100&offset=&order=publish_date_desc"
        stories_api = "https://onlyfans.com/api2/v2/users/"+str(user_id)+"/stories?limit=100&offset=0&order=desc"
        archive_api = "https://onlyfans.com/api2/v2/users/"+ str(user_id)+"/posts/archived?limit=100&offset=&order=publish_date_desc"
        audio_api = "https://onlyfans.com/api2/v2/users/"+str(user_id)+"/posts/audios?limit=100&offset=&order=publish_date_desc"

        self.events.display_event("Getting links for " + str(username), niveau_titre=2)

        if flag & MESSAGES:
            self.events.display_event("Loading messages")
            js_message = []
            offset = 0

            json_data = self.make_json_server_request(message_api, "Temps/" + username + "/messages_" + str(offset))
            js_message.append(json_data)
            while json_data['hasMore'] == True:
                offset += 1
                message_temp = message_api.replace("offset=", "offset=" + str(offset * 100))
                json_data = self.make_json_server_request(
                    message_temp,
                    "Temps/" + username + "/messages_" + str(offset),
                    request_delay=2.5,
                )
                js_message.append(json_data)
                self.events.display_event("Loading messages ... part " + str(offset + 1))
            self.events.display_event("Loading messages ... Done")

            self.events.display_event("Counting messages")
            nb_photo = 0
            nb_video = 0
            for j in js_message:
                if "list" in j:
                    json_list = j["list"]
                    for sec in json_list:
                        if "media" in sec:
                            media = sec["media"]
                            date = sec["createdAt"]
                            for m in media:
                                if "files" in m and "type" in m:
                                    files = m["files"]
                                    if files is None:
                                        continue
                                    file = files["full"]
                                    if file is None:
                                        continue
                                    file_url = file["url"]
                                    if file_url is None:
                                        continue
                                    id_post = sec["id"]
                                    type_src = m["type"]
                                    file_size = file["size"]
                                    fileName = self.get_file_names(file_url)
                                    
                                    if type_src == "photo" and not self.file_names_exists_and_add_if_not(filesNames, fileName):
                                        #self.all_files_size += file_size
                                        file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": id_post,
                                                     "date" : date, "flag" : MESSAGES, "isVideo" : False, "fileName" : fileName}
                                        nb_photo += 1
                                        messages.append(file_dict)
                                    elif type_src == "video" and not self.file_names_exists_and_add_if_not(filesNames, fileName) and self.is_new_file(isExistingUser, user_id, fileName):
                                        if file_size == 0:
                                            r = self.session.head(file_url)
                                            if "Content-Length" in r.headers:
                                                file_size = int(r.headers["Content-Length"])
                                        self.all_files_size += file_size
                                        file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": id_post,
                                                     "date" : date, "flag" : MESSAGES, "isVideo" : True, "fileName" : fileName}
                                        nb_video += 1
                                        messages.append(file_dict)
            self.events.display_event("Counting messages ... Done (" + str(nb_photo) + " photo(s) - " + str(nb_video) + " video(s))")

        if flag & PICTURES or flag & VIDEOS:
            self.events.display_event("Loading pictures and videos")
            json_data = []
            nbZeroItems = 0
            offset_range = math.ceil(total_count / 50)
            for n in list(range(offset_range)):
                offset = str(n * 50)
                post_tmp = post_api.replace("offset=", "offset=" + offset)
                json_reponse = self.make_json_server_request(post_tmp, "Temps/" + username + "/post_" + str(n))
                if len(json_reponse) != 50 and n + 1 < offset_range:
                    self.events.display_event("Server response contained " + str(len(json_reponse)) + " items instead of 50")
                if len(json_reponse) == 0:
                    nbZeroItems += 1
                    if nbZeroItems >= 3:
                        self.events.display_event("3 consecutives requests returned 0 items, stopping enumeration")
                        break
                json_data.append(json_reponse)
                self.events.display_event("Loading pictures and videos ... " + str(offset) + " / " + str(total_count))
            nbItemJson_data = len(json_data)

            self.events.display_event("Loading stories")
            js = self.make_json_server_request(stories_api, "Temps/" + username + "/stories")
            self.events.display_event("Loading stories ... done")
            self.events.display_event("Counting stories")
            nb_photo = 0
            nb_video = 0
            for j in js:
                if "media" in j and "createdAt" in j:
                    m = j["media"]
                    date = j["createdAt"]
                    post_id = j["id"]
                    for media in m:
                        if "files" in media and "type" in media:
                            files = media["files"]
                            if files is None:
                                continue
                            file = files["full"]
                            if file is None:
                                continue
                            file_url = file["url"]
                            if file_url is None:
                                continue
                            type_src = media["type"]
                            file_size = file["size"]
                            fileName = self.get_file_names(file_url)
                            if type_src == "photo" and not self.file_names_exists_and_add_if_not(filesNames, fileName):
                                #self.all_files_size += file_size
                                file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": post_id,
                                                "date" : date, "flag" : STORIES, "isVideo" : False, "fileName" : fileName}
                                nb_photo += 1
                                stories.append(file_dict)
                            elif type_src == "video" and not self.file_names_exists_and_add_if_not(filesNames, fileName) and self.is_new_file(isExistingUser, user_id, fileName):
                                if file_size == 0:
                                    r = self.session.head(file_url)
                                    if "Content-Length" in r.headers:
                                        file_size = int(r.headers["Content-Length"])
                                self.all_files_size += file_size
                                file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": post_id,
                                                "date" : date, "flag" : STORIES, "isVideo" : True, "fileName" : fileName}
                                nb_video += 1
                                stories.append(file_dict)
            self.events.display_event("Counting stories ... done (" + str(nb_photo) + " photo(s) - " + str(nb_video) + " video(s))")
        
        if flag & PICTURES:
            self.events.display_event("Counting pictures")
            nbCounted = 0
            nb_photo = 0
            for j in json_data:
                for js in j:
                    if "postedAt" in js and "media" in js and "id" in js:
                        date = js["postedAt"]
                        media = js["media"]
                        id_post = js["id"]
                        for m in media:
                            if "files" in m and "type" in m:
                                files = m["files"]
                                if files is None:
                                    continue
                                file = files["full"]
                                if file is None:
                                    continue
                                file_url = file["url"]
                                if file_url is None:
                                    continue
                                type_src = m["type"]
                                file_size = file["size"]
                                if type_src != "photo" or not file_url.startswith('https://cdn'):
                                    continue
                                fileName = self.get_file_names(file_url)
                                if not self.file_names_exists_and_add_if_not(filesNames, fileName):
                                    #self.all_files_size += file_size
                                    file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": id_post,
                                            "date" : date, "flag" : PICTURES, "isVideo" : False, "fileName" : fileName}
                                    nb_photo += 1
                                    images.append(file_dict)
                nbCounted += 1
                self.events.display_event("Counting pictures ... " + str(nbCounted) + " / " + str(nbItemJson_data))
            self.events.display_event("Counting pictures ... Done (" + str(nb_photo) + " photo(s))")
            
        if flag & VIDEOS:
            self.events.display_event("Counting videos")
            nbCounted = 0
            nb_video = 0
            for j in json_data:
                for js in j:
                    if "postedAt" in js and "media" in js and "id" in js:
                        date = js["postedAt"]
                        media = js["media"]
                        id_post = js["id"]
                        for m in media:
                            if "files" in m and "type" in m:
                                files = m["files"]
                                if files is None:
                                    continue
                                file = files["full"]
                                if file is None:
                                    continue
                                file_url = file["url"]
                                if file_url is None:
                                    continue
                                file_size = file["size"]
                                if m["type"] != "video" or not file_url.startswith('https://cdn'):
                                    continue
                                fileName = self.get_file_names(file_url)
                                if not self.file_names_exists_and_add_if_not(filesNames, fileName) and self.is_new_file(isExistingUser, user_id, fileName):
                                    if file_size == 0:
                                        r = self.session.head(file_url)
                                        if "Content-Length" in r.headers:
                                            file_size = int(r.headers["Content-Length"])      
                                    self.all_files_size += file_size
                                    file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": id_post,
                                            "date" : date, "flag" : VIDEOS, "isVideo" : True, "fileName" : fileName}
                                    nb_video += 1
                                    videos.append(file_dict)
                nbCounted += 1
                self.events.display_event("Counting videos ... " + str(nbCounted) + " / " + str(nbItemJson_data))
            self.events.display_event("Counting videos ... Done (" + str(nb_video) + " video(s))")

        if flag & ARCHIVED:
             cnt = info["archivedPostsCount"]
             if cnt > 0:
                self.events.display_event("Loading and counting archives")
                off_range = math.ceil(cnt / 50)
                offsets_arch = list(range(off_range))
                nbCounted = 0
                nb_photo = 0
                nb_video = 0

                for off in offsets_arch:
                    nbCounted += 1
                    self.events.display_event("Loading and counting archives ... " + str(nbCounted) + " / " + str(off_range))
                    arch_temp = archive_api.replace("offset=", "offset=" + str(off * 50))
                    js = self.make_json_server_request(arch_temp, "Temps/" + username + "/archives_" + str(off))
                    if len(js) != 50 and off + 1 < off_range:
                        self.events.display_event("Server response contained " + str(len(js)) + " items instead of 50")
                    for j in js:
                        if "postedAt" in j and "media" in j and "id" in j:
                            date = j["postedAt"]
                            media = j["media"]
                            id_post = j["id"]
                            for m in media:
                                if "files" in m and "type" in m:
                                    files = m["files"]
                                    if files is None:
                                        continue
                                    file = files["full"]
                                    if file is None:
                                        continue
                                    file_url = file["url"]
                                    if file_url is None:
                                        continue
                                    type_src = m["type"]
                                    file_size = file["size"]
                                    if type_src != "photo" or not file_url.startswith('https://cdn'):
                                        continue
                                    fileName = self.get_file_names(file_url)

                                    if type_src == "photo" and not self.file_names_exists_and_add_if_not(filesNames, fileName):
                                        #self.all_files_size += file_size
                                        file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": id_post,
                                                     "date" : date, "flag" : ARCHIVED, "isVideo" : False, "fileName" : fileName}
                                        nb_photo += 1
                                        archived.append(file_dict)
                                    elif type_src == "video" and not self.file_names_exists_and_add_if_not(filesNames, fileName) and self.is_new_file(isExistingUser, user_id, fileName):
                                        if file_size == 0:
                                            r = self.session.head(file_url)
                                            if "Content-Length" in r.headers:
                                                file_size = int(r.headers["Content-Length"])
                                        self.all_files_size += file_size
                                        file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": id_post,
                                                     "date" : date, "flag" : ARCHIVED, "isVideo" : True, "fileName" : fileName}
                                        nb_video += 1
                                        archived.append(file_dict)
                self.events.display_event("Loading and counting archives ... Done (" + str(nb_photo) + " photo(s) - " + str(nb_video) + " video(s))")

        if flag & AUDIO:
            cnt = info["audiosCount"]
            if cnt > 0:
                self.events.display_event("Loading and counting audio")
                off_range = math.ceil(cnt / 50)
                offsets_arch = list(range(off_range))
                nbCounted = 0
                nb_audio = 0

                for off in offsets_arch:
                    nbCounted += 1
                    self.events.display_event("Loading and counting audio ... " + str(off) + " / " + str(off_range))
                    audio_temp = audio_api.replace("offset=", "offset=" + str(off * 50))
                    js = self.make_json_server_request(audio_temp, "Temps/" + username + "/audio_" + str(off))
                    if len(js) != 50 and off + 1 < off_range:
                        self.events.display_event("Server response contained " + str(len(js)) + " items instead of 50")
                    for j in js:
                        if "postedAt" in j and "media" in j and "id" in j:
                            date = j["postedAt"]
                            media = j["media"]
                            id_post = j["id"]
                            for m in media:
                                if "files" in m and "type" in m:
                                    files = m["files"]
                                    if files is None:
                                        continue
                                    file = files["full"]
                                    if file is None:
                                        continue
                                    file_url = file["url"]
                                    if file_url is None:
                                        continue
                                    type_src = m["type"]
                                    file_size = file["size"]
                                    fileName = self.get_file_names(file_url)

                                    if type_src != "audio" or not file_url.startswith('https://cdn'):
                                        continue
                                    #self.all_files_size += file_size
                                    file_dict = {"source" : file_url, "size": file_size, "index" : index, "id": id_post,
                                                "date" : date, "flag" : AUDIO, "isVideo" : False, "fileName" : fileName}
                                    nb_audio += 1
                                    audio.append(file_dict)
                self.events.display_event("Loading and counting audio ... Done (" + str(nb_audio) + " audio(s))")

        if isExistingUser:
            self.events.display_event("Validating duplicate")
            self.validate_duplicate(user_id, messages, "messages")
            self.validate_duplicate(user_id, stories, "stories")
            self.validate_duplicate(user_id, images, "images")
            self.validate_duplicate(user_id, videos, "videos")
            self.validate_duplicate(user_id, audio, "audio")
            self.validate_duplicate(user_id, archived, "archived")
            self.events.display_event("Validating duplicate ... Done")
        else:
            self.events.display_event("Validating duplicate ... Skipped (Never downloaded " + username + ")")

        links_info = {
            "user_id" : user_id, "index" : index, 
            "file_count" : len(messages) + len(stories) + len(images) + len(videos) + len(audio) + len(archived),
            "messages" : messages, "stories" : stories, "images" : images,
            "videos" : videos, "audio" : audio, "archived" : archived }
        events_detail:List[str] = []
        events_detail.append("Getting links for " + username + " ... Done")
        for type_file in TYPE_FILE:
            type_file_count = len(links_info[type_file])
            if type_file_count > 0:
                events_detail.append("     " + type_file + " : " + str(type_file_count))
                for file in links_info[type_file]:
                    user_file_size += file["size"]
        links_info["user_file_size"] = user_file_size
        self.links.append(links_info)
        if links_info["file_count"] == 0:
            self.update_date_database(user_id)
            events_detail.append("     Total files: " + str(links_info["file_count"]))
            events_detail.append("     Total size (videos): " + self.File_Size_Str(links_info["user_file_size"]))
        self.events.display_event(*events_detail, niveau_titre=2)
        return links_info

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
            self.events.display_event("Validating duplicate " + type_links + " ... 0 / " + str(nbTotal))
            for link in list_copy:
                if not link["isVideo"] and self.select_database(user_id, link["fileName"]):
                    user_links.remove(link)
                    self.all_files_size -= link["size"]
                nbValider += 1
                if nbValider % 100 == 0:
                    self.events.display_event("Validating duplicate " + type_links + " ... " + str(nbValider) + " / " + str(nbTotal))
            self.events.display_event("Validating duplicate " + type_links + " ... Done")

    def file_names_exists_and_add_if_not(self, fileNames: set, fileName: str):
        if fileName in fileNames:
            return True
        else:
            fileNames.add(fileName)
            return False

    def get_file_names(self, source):
        return source.split('/')[-1].split('?')[0]

    def update_sub_database(self, sub):
        try:
            params = {
                'userid': sub["userid"],
                'username': sub["username"],
                'isExpired': sub["isExpired"],
                'expireDate': sub["expiration"],
                'paid': sub["paid"]
            }
            sql_insert_update = """
                INSERT INTO Subscriptions
                    (userid, username, isExpired, expireDate, paid)
                VALUES
                    (:userid, :username, :isExpired, :expireDate, :paid)
                ON CONFLICT(userid) DO UPDATE 
                SET 
                    username = excluded.username,
                    isExpired = excluded.isExpired,
                    expireDate = excluded.expireDate,
                    paid = excluded.paid;
            """
            c = self.conn.cursor()
            c.execute(sql_insert_update, params)
            self.conn.commit()
        except Error as e:
            self.events.display_event(str(e))

    def user_exist_database(self, user_id):
        try:
            params = {
                'userid': user_id
            }
            sql_select = """
                SELECT
                    userid
                FROM
                    ItemScrape
                WHERE
                    userid = :userid
                LIMIT
                    1
            """
            c = self.conn.cursor()
            c.execute(sql_select, params)
            return len(c.fetchall()) > 0
        except:
            return False

    def select_database(self, user_id, filename):
        try:
            params = {
                'userid': user_id,
                'filename': filename
            }
            sql_select = """
                SELECT
                    userid
                FROM
                    ItemScrape
                WHERE
                    userid = :userid
                    AND
                    filename = :filename
                LIMIT 
                    1
            """
            c = self.conn.cursor()
            c.execute(sql_select, params)
            return len(c.fetchall()) > 0
        except:
            return False

    def insert_database(self, user_id, file):
        try:
            params = {
                'id': str(file["id"]),
                'userid': str(user_id),
                'filename': str(file["source"].split('?')[0].split('/')[-1]),
                'dateItem': parser.parse(file["date"]).strftime("%Y-%m-%d %H:%M:%S")
            }
            sql_insert = """
                INSERT INTO ItemScrape
                    (id, userid, filename, dateItem)
                VALUES
                    (:id, :userid, :filename, :dateItem)
            """
            c = self.conn.cursor()
            c.execute(sql_insert, params)
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass

    def update_date_database(self, user_id):
        try:
            params = {
                'userid': str(user_id),
                'dateLastScrape': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            sql_update = """
                UPDATE
                    Subscriptions
                SET
                    dateLastScrape = :dateLastScrape
                WHERE
                    userid = :userid
            """
            c = self.conn.cursor()
            c.execute(sql_update, params)
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
        obj.FileSizeLeft.configure(text = "0.00 B / 0.00 B")
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
                current_file_dl = 0
                response = self.session.get(file_name, stream=True)
                tmp = response.headers.get('content-length')
                if tmp is None:
                    if file_links["isVideo"]:
                        current_file_dl = file_links["size"]
                        self.current_dl += current_file_dl
                    file.write(response.content)

                else:
                    total_length = int(tmp)
                    total_length_str = self.File_Size_Str(total_length)

                    for data in response.iter_content(chunk_size=4096):
                        data_len = len(data)
                        if file_links["isVideo"]:
                            current_file_dl += data_len
                            self.current_dl += data_len
                            if file_links["size"] > MIN_SIZE_SPECIAL_DISPLAY:
                                obj.ProgressBarItem['value'] =  (current_file_dl / total_length) * 100
                                obj.FileSizeLeft.configure(text = self.File_Size_Str(current_file_dl) + " / " + total_length_str)
                        else:
                            self.current_dl_other += data_len
                        file.write(data)

                if file_links["isVideo"] and current_file_dl > 0:
                    self.current_dl += (file_links["size"] - current_file_dl)
                    obj.ProgressBar['value'] =  (self.current_dl / self.all_files_size) * 100
                obj.TotalSizeLeft.configure(text = self.File_Size_Str(self.current_dl) + " (+" + self.File_Size_Str(self.current_dl_other) + ") / " + self.File_Size_Str(self.all_files_size))

    def create_dir(self, dirname):
        try:
            if os.path.exists("Files/" + dirname) == False:
                os.mkdir("Files/" + dirname)
        except FileExistsError:
            pass
