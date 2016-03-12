#!/usr/bin/python
# -*- coding: utf-8 -*-

from tweepy.streaming import StreamListener
from tweepy import OAuthHandler
from tweepy import Stream
from tweepy import API
import time
import re
import sqlite3 as lite
import sys
import datetime
# For preventing XSS :)
from xml.sax.saxutils import quoteattr
import json

try:
    from wherethehellis_conf import USERNAME_TO_WATCH
except ImportError:
    USERNAME_TO_WATCH = "nickname"

# This file should be downloaded from:
# http://openflights.org/data.html
try:
    from wherethehellis_conf import AIRPORTS_DB_FILE
except ImportError:
    AIRPORTS_DB_FILE = "airports.dat"

try:
    from wherethehellis_conf import OUTPUT_HTML_FILE
except ImportError:
    OUTPUT_HTML_FILE = "wherethehellisnick.html"

# Unrelated to the web page, but could be used as "API" for the last position
try:
    from wherethehellis_conf import OUTPUT_JSON_FILE
except ImportError:
    OUTPUT_JSON_FILE = "nicklast.json"

try:
    from wherethehellis_conf import USERNAME_ICON
except ImportError:
    USERNAME_ICON = "nick_icon.jpg"

try:
    from wherethehellis_conf import SQLITE_DB_FILE
except ImportError:
    SQLITE_DB_FILE = "nick.db"

# Go to http://dev.twitter.com and create an app.
# The consumer key and secret will be generated for you after
try:
    from wherethehellis_conf import CONSUMER_KEY, CONSUMER_SECRET
except ImportError:
    CONSUMER_KEY = "CONSUMER_KEY"
    CONSUMER_SECRET = "CONSUMER_SECRET"

# After the step above, you will be redirected to your app's page.
# Create an access token under the the "Your access token" section
try:
    from wherethehellis_conf import ACCESS_TOKEN, ACCESS_TOKEN_SECRET
except ImportError:
    ACCESS_TOKEN = "ACCESS_TOKEN"
    ACCESS_TOKEN_SECRET = "ACCESS_TOKEN_SECRET"


try:
    con = lite.connect(SQLITE_DB_FILE)
    cur = con.cursor()    
    cur.execute("CREATE TABLE IF NOT EXISTS Statuses(Id INTEGER PRIMARY KEY,"
                " Timestamp INTEGER, Lat NUMERIC, Long NUMERIC, Text TEXT)")
    con.commit()

except lite.Error, e:
    if con:
        con.rollback()
    print "SQLite Error %s:" % e.args[0]
    sys.exit(1)

def gen_airport_map():
    airports_map = {}
    for line in open(AIRPORTS_DB_FILE, "r"):
        line = line.replace("\n","")
        if not line: continue
        tokens = line.split(",")
        airports_map[tokens[-8].replace('"',"")] = (float(tokens[-6]), float(tokens[-5]))
    return airports_map


airports_map = gen_airport_map()
    
def compile_page():
    # Get all processed tweets
    cur.execute("SELECT Id, Timestamp, Lat, Long, Text FROM Statuses "
                "ORDER BY Timestamp DESC")
    con.commit()
    
    rows = list(cur.fetchall())
    first_pos = None
    map_points = {}
    if len(rows) == 0:
        print("No data saved in the db :(")
        return
    con.commit()
    # Because entries are ordered by time, the first is the newest
    first_pos = (rows[0][2], rows[0][3])
    
    for status_id, timestamp, lat, lon, text in rows:
        key = (lat, lon)
        if key not in map_points:
            map_points[key] = []
        map_points[key].append([timestamp, text, status_id])

    fd = open(OUTPUT_HTML_FILE, "w")
    fd.write(("""<!DOCTYPE html>\n<html><head><title>{nickname} Map</title>"""
        """<script type="text/javascript" src="//ajax.googleapis.com/ajax/li"""
        """bs/jquery/1.6.4/jquery.min.js"></script><script type="text/javasc"""
        """ript" src="//maps.google.com/maps/api/js?sensor=true"></script><s"""
        """cript type="text/javascript" src="/gmaps.js"></script><link href="""
        """'//fonts.googleapis.com/css?family=Convergence|Bitter|Droid+Sans|"""
        """Ubuntu+Mono' rel='stylesheet' type='text/css' /><script type="tex"""
        """t/javascript">var map; $(document).ready(function(){{"""
        """map = new GMaps({{
            div: '#map',
            lat: {pos1},
            lng: {pos2},
        }}); map.setZoom(6);""").format(
            nickname = USERNAME_TO_WATCH,
            pos1 = first_pos[0],
            pos2 = first_pos[1]))

    for key in map_points:
        if (key[0] == first_pos[0]) and (key[1] == first_pos[1]):
            json_fd = open(OUTPUT_JSON_FILE, "w")
            stripped_message = str(quoteattr(map_points[key][0][1].replace("'",
                "").replace("\"","")).replace("'","").replace("\"",
                "").replace("\n",""))
            infos = {
                # Note: UTC time is used
                "time" : time.strftime("%Y-%m-%d %H:%M:%S",
                             time.gmtime(map_points[key][0][0])),
                "text" : stripped_message,
                "link" : "https://twitter.com/{user}/status/{status}".format(
                             user = USERNAME_TO_WATCH,
                             status = map_points[key][0][2]),
                "lat" : str(key[0]),
                "long" : str(key[1]),
            }
            json_fd.write(json.dumps(infos))
            json_fd.close()

        fd.write("""
            map.addMarker({{
            lat: {latitude},
            lng: {longitude},
            title: '{nickname}',{icon_data}
            infoWindow: {{
                content: '<p><ul>""".format(
            latitude = key[0],
            longitude = key[1],
            nickname = USERNAME_TO_WATCH,
            icon_data = "\nicon: '"+USERNAME_ICON+"'," if ( \
                key[0] == first_pos[0] and key[1] == first_pos[1]) else ""))

        # Pupulate the text list in the marker's box with all statuses and
        # positions.
        for timestamp, message, statusid in map_points[key]:
            date = time.strftime("%Y-%m-%d %H:%M:%S UTC",
                                 time.gmtime(timestamp))
            stripped_message = str(quoteattr(message.replace("'",
                "").replace("\"","")).replace("'","").replace("\"",
                "").replace("\n",""))
            fd.write("""<li>{date_string} - <a href=\\'https://twitter.com/"""
                     """{user}/status/{status_id}\\'>{message_text}</a>"""
                     """</li>""".format(
                date_string = date,
                user = USERNAME_TO_WATCH,
                status_id = statusid,
                message_text = stripped_message))
        
        fd.write("""</ul></p>'\n}\n});""")

    fd.write("""\n});\n</script><style type="text/css" media="screen">"""
             """#map { position:absolute; top: 0; bottom: 0; left: 0; """
             """right: 0;} </style></head><body><p>Loading...</p>"""
             """<div id="map"></div></body></html>""")
    fd.close()

def airportname_to_coord(airportcode):
    coords = None
    if airportcode in airports_map:
        return airports_map[airportcode]
    return coords


def find_airport_data(text):
    m = re.match(r"[Ww]heels ?down,? ([A-Za-z]+).*", text)
    if m:
        airport_name = m.groups()[0]
        print("Tweet matching regexp, containing "
              "airport {}. Looking up.".format(airport_name))
        airport_coord = airportname_to_coord(airport_name)
        if airport_coord != None:
            print("Airport found")
            return airport_coord
    return None


def process_tweet(status):
    # For some reason we might get tweets retweeted by the filtered user.
    # Check if the tweet has been written by our target user.
    if status.user.screen_name != USERNAME_TO_WATCH:
        return

    # Check if we already processed the tweet with this id
    cur.execute("SELECT count(*) FROM Statuses WHERE Id=:Id",
                {"Id": int(status.id)})
    con.commit()
    row = cur.fetchone()
    # If this tweet was never processed in the past, proceed to processing now.
    if row[0] == 0:
        print("New tweet {} to be processed.".format(status.id))
        airport_info = find_airport_data(status.text)
        
        if airport_info != None:
            latitude, longitude = airport_info
            epoch_time = (status.created_at - \
                          datetime.datetime(1970,1,1)).total_seconds()
            cur.execute("INSERT INTO Statuses(Id,Timestamp,Lat,Long,Text) "
                        "VALUES (?,?,?,?,?)", (int(status.id), epoch_time, 
                        latitude, longitude, status.text))
            con.commit()
            print("written in DB")
            return True
    return False 


class StdOutListener(StreamListener):
     
    def on_status(self, status):
        # Process the new tweet. If the tweet contains new data, then rebuild
        # the page.
        if process_tweet(status):
            compile_page()
        return True

    def on_error(self, status):
        print status


if __name__ == '__main__':
    l = StdOutListener()
    auth = OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    
    api = API(auth, wait_on_rate_limit = True)
    user = api.get_user(USERNAME_TO_WATCH)

    oldest = None
    tweets_list = []
    first_run = True
    downloaded = 0
    print("Starting fetch of old tweets")
    while len(tweets_list) > 0 or first_run:
        if first_run:
            tweets_list = api.user_timeline(screen_name = USERNAME_TO_WATCH,
                                            count = 200, include_rts = False)
            first_run = False
        else:
            #all subsiquent requests use the max_id param to prevent duplicates
            tweets_list = api.user_timeline(screen_name = USERNAME_TO_WATCH,
                                            count = 200, max_id = oldest, 
                                            include_rts = False)
        downloaded += len(tweets_list)
        print("{} tweets downloaded so far".format(downloaded))
        for tweet in tweets_list:
            process_tweet(tweet)

        #update the id of the oldest tweet less one
        if len(tweets_list) > 0:
            oldest = tweets_list[-1].id - 1

    # Even if no tweet was processed, regenerate the page for the first time.
    print("Building HTML page")
    compile_page()
    print("Building completed.")

    stream = Stream(auth, l)
    stream.filter(follow = [str(user.id)])

