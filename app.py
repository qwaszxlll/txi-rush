#!/usr/bin/env python
import urllib
import requests
import unicodecsv
import subprocess
from cStringIO import StringIO
from flask import Flask, jsonify, request, abort
from flask_errormail import mail_on_500
from flask_mail import Mail, Message
from flask.ext.cors import cross_origin
from flask.ext.cache import Cache
from flask.ext.pymongo import PyMongo
# from functools import wraps
import json
import os
import pipes
import phonenumbers
import requests
from datetime import datetime, timedelta
import time
from tempfile import mkdtemp

app = Flask(__name__)
app.config["MONGO_DBNAME"] = "rushapp"
cache_dir = mkdtemp()
cache = Cache(app, config={
    'CACHE_TYPE': 'memcached',
    'CACHE_MEMCACHED_SERVERS': ['127.0.0.1'],
})

app = Flask(__name__)
mongo = PyMongo(app)

import logging.handlers, logging
file_handler = logging.handlers.RotatingFileHandler("/var/www/txirush.log", 'a', 10000000, 1000)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s '
    '[in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(file_handler)


if os.getenv("LOGFILE", None):
    import logging.handlers, logging
    file_handler = logging.handlers.RotatingFileHandler(os.getenv("LOGFILE"), 'a', 10000000, 1000)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    ))
    app.logger.addHandler(file_handler)

mail_on_500(app, ["txi-web@mit.edu", ])

# Replace this.
DOC_KEY="xx"

def ldapsearch(uid):
    cmd = 'ldapsearch -l 5 -LLL -x -h ldap-too -b "ou=users,ou=moira,dc=mit,dc=edu" ' + pipes.quote("uid=" + uid)
    try:
        output = subprocess.check_output(cmd, shell=True)
    except subprocess.CalledProcessError, e:
        app.logger.error(str(e))
        return None
    out = {}
    lines = output.strip().splitlines()
    for line in lines:
        key, val = line.split(":", 1)
        if key != "objectClass":
            out[key] = val.strip()
    return out

@app.before_request
def fill_user():
    provider = request.headers.get("Shib-Identity-Provider", None)
    if provider is None:
        request.user = None
        return

    assert provider == "https://idp.mit.edu/shibboleth"
    assert "Mail" in request.headers
    request.user = {
        "brother": False,
        "rushee": False,
        "email": request.headers["Mail"],
        "kerberos": request.headers["Mail"].replace("@mit.edu", ""),
        "name": request.headers["Nickname"],
        "affiliation": request.headers.get("Affiliation", "").replace("@mit.edu", "")
    }
    ldap = mongo.db.ldap.find_one({"uid": request.user["kerberos"]}, fields={"_id": False})
    if ldap is None:
        info = ldapsearch(request.user["kerberos"])
        if info:
            ldap = mongo.db.ldap.find_and_modify(query={"uid": request.user["kerberos"]},
                                                 update=info,
                                                 upsert=True,
                                                 new=True,
                                                 fields={"_id": False})
    request.user["ldap"] = ldap or {}
    brother = mongo.db.brothers.find_one({
        "kerberos": request.user["kerberos"],
        })
    if brother:
        request.user["brother"] = True
        request.user["name"] = brother["name"]
        request.user["cell"] = brother["cell"]
        request.user["course"] = brother["course"]
        request.user["bio"] = brother["bio"]
        request.user["delta"] = brother["delta"]
        request.user["driver"] = brother["driver"]
        request.user["coordinator"] = brother["coordinator"]
    else:
        rushee = mongo.db.rushees.find_one({"kerberos": request.user["kerberos"]})
        if rushee is not None:
            request.user["rushee"] = True
            request.user["name"] = rushee["name"]
            request.user["cell"] = rushee["cell"]


@app.route("/sms", methods=["GET", "POST"])
def send_sms():
    data = request.get_json() if request.method == "POST" else request.args
    recipient, message = data.get("recipient"), data.get("message")
    if recipient is None:
        return jsonify({"error": "Missing recipient."})
    if message is None:
        return jsonify({"error": "Missing message."})
    endpoint = "https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT}/Messages.json"
    sender = "+1num"
    auth = ("user", "pass")
    mongo.db.sms.insert({
        "recipient": recipient,
        "message": message,
        "created": datetime.utcnow()
    })
    try:
        x = phonenumbers.parse(recipient, "US")
        num = phonenumbers.format_number(x, phonenumbers.PhoneNumberFormat.E164)
    except:
        app.logger.warning("%s is not a valid number." % r)
        return jsonify({"error": "%s is not a valid number." % r})
    try:
        r = requests.post(endpoint, auth=auth, data={
            "Body": message, "From": sender, "To": num,
        })
        if "message" in r.json():
            return jsonify({"error": r.json()["message"]})
        if r.json().get("error_message"):
            return jsonify({"error": r.json()["error_message"]})
        else:
            return jsonify({"status": "ok"})
    except:
        app.logger.error("Sending message to %s failed." % num)
        return jsonify({"error": "failed.. who knows why.."})

@app.route("/ldapsearch/<uid>")
def web_ldap(uid=None):
    assert uid
    return jsonify(ldapsearch(uid))

def make_spreadsheet_csv_url(key, gid, query=""):
    return "https://spreadsheets.google.com/tq?" + urllib.urlencode({
        "tq": query,
        "key": key,
        "gid": gid,
        "tqx": "out:csv"
        })

def get_spreadsheet(gid):
    url = make_spreadsheet_csv_url(DOC_KEY, gid)
    r = requests.get(url)
    io = StringIO(r.content)
    csv = unicodecsv.DictReader(io, encoding="utf8")
    return csv

def parse_brother_contacts():
    csv = get_spreadsheet(1980692373)
    brothers = {}
    for row in csv:
        brothers[row["Name"]] = row["Cell"]
    return brothers


@cache.memoize(timeout=300)
def brother_contacts_cached():
    return parse_brother_contacts()


@app.route("/sync/brothers", methods=["GET", "POST"])
def sync_brothers():
    csv = get_spreadsheet(1980692373)
    brothers = []
    for row in csv:
        brothers.append({
            "name": row["Name"],
            "cell": row["Cell"],
            "delta": int(row["Delta"]),
            "kerberos": row["Kerberos"],
            "driver": True if row["Driver"] == "Y" else False,
            "coordinator": True if row["Coordinator"] == "Y" else False,
            "year": row["Year"],
            "bio": row["Bio"],
            "course": row["Course"]
            })
    mongo.db.brothers.remove({})
    mongo.db.brothers.insert(brothers)
    return jsonify({"status": "ok"})

@app.route("/sync/route", methods=["GET"])
def sync_route():
    if not request.user["brother"]:
        return jsonify({"error": "You are not a brother."})
    west = [row for row in get_spreadsheet(1651264497)]
    east = [row for row in get_spreadsheet(1078057510)]

    mongo.db.routes.remove({})
    mongo.db.routes.insert({"name": "West",
        "locations": [x["Location"] for x in west]})
    mongo.db.routes.insert({"name": "East",
        "locations": [x["Location"] for x in east]})

    locations = []
    for x in west:
        if x["Location"] not in locations:
            locations.append(x["Location"])
    for x in east:
        if x["Location"] not in locations:
            locations.append(x["Location"])
    locations = map(lambda x: {"name": x}, locations)

    mongo.db.locations.remove({})
    mongo.db.locations.insert(locations)
    return jsonify({"status": "ok"})

@app.route("/", methods=["GET"])
def hello():
    return "hello. "

@app.route("/me", methods=["GET"])
def me():
    return jsonify({"me": request.user, "useragent": request.user_agent.string})

@app.route("/rushee", methods=["GET", "POST"])
def update_rushee():
    if request.method == "POST":
        j = request.get_json()
    else:
        j = request.args
    cell = j.get("cell")
    name = j.get("name")
    if not cell or not name:
        return jsonify({"error": "Cell or name is missing."})

    mongo.db.rushees.update({"kerberos": request.user["kerberos"]}, {
        "$set": {
            "cell": cell,
            "name": name
        },
        "$setOnInsert": {
            "kerberos": request.user["kerberos"],
        },
    }, upsert=True)
    fill_user()
    return me()

@app.route("/headers", methods=["GET"])
def headers():
    return jsonify(request.headers)

@app.route("/brothers", methods=["GET"])
def brothers():
    if request.user["brother"]:
        out = [row for row in mongo.db.brothers.find({}, {'_id': False})]
        return jsonify({"brothers": out})
    else:
        return jsonify({"error": "Permission denied."})

def compile_requests():
    requests = mongo.db.pickups.find({}, {"_id": False})
    requests_by_location = {}
    for r in requests:
        requests_by_location.setdefault(r["location"], [])
        requests_by_location[r["location"]].append(r)
    locations = mongo.db.locations.find({}, {"_id": False})
    out = []
    tt = 0
    for l in locations:
        name = l["name"]
        reqs = requests_by_location.get(name, [])
        tt += len(reqs)
        out.append({
            "location": name,
            "requests": reqs
        })
    totals = {}
    routes = mongo.db.routes.find({}, {"_id": False})
    for route in routes:
        totals[route["name"]] = 0
        for location in route["locations"]:
            totals[route["name"]] += len(requests_by_location.get(location, []))
    totals["all"] = tt
    return {"requests": out, "totals": totals}

@app.route("/requests", methods=["GET", "POST"])
def requests_view():
    return jsonify(compile_requests())

# @app.route("/requests/<location>/<inc>", methods=["POST", "GET"])
# def update_location(**kwargs):
#     l = kwargs["location"]
#     inc = int(kwargs["inc"])
#     loc = mongo.db.requests.find_and_modify(query={"location": l},
#                                             update={"$inc": {"requests": inc}},
#                                             upsert=False, new=True,
#                                             fields={"_id": False})

#     if loc is None:
#         return jsonify({"error": "%s does not exist in route." % l})
#     mongo.db.requests.update({"requests": {"$lt": 0}},
#                              {"$set": {"requests": 0}}, multi=True)
#     return jsonify(loc)

@app.route("/requests/add", methods=["GET", "POST"])
def add_request():
    if request.method == "GET":
        form = request.args
    else:
        form = request.get_json()
    name = form.get("name")
    cell = form.get("cell")
    location = form.get("location")
    if not name or not cell or not location:
        return jsonify({"error": "missing location, name or cell."})
    mongo.db.pickups.update({"name": name, "location": location}, {
        "$set": {
            "timestamp": datetime.utcnow(),
            "cell": cell
        },
        "$setOnInsert": {
            "name": name,
            "location": location
        },
    }, upsert=True)
    return jsonify(compile_requests())


@app.route("/requests/delete", methods=["GET", "POST"])
def remove_request():
    if request.method == "GET":
        form = request.args
    else:
        form = request.get_json()
    # print dict(form)
    name = form.get("name")
    location = form.get("location")
    cell = form.get("cell")
    mongo.db.pickups.remove({"name": name, "location": location})
    return jsonify(compile_requests())

@app.route("/routes", methods=["GET"])
def routes_view():
    q = mongo.db.routes.find({}, {"_id": False})
    return jsonify({"routes": [row for row in q]})

@app.route("/pickup/<location>", methods=["POST", "GET"])
def pick_me_up(location=None):
    assert location
    if mongo.db.locations.find_one({"name": location}) is None:
        return jsonify({"error": "%s does not exist." % location})
    mongo.db.pickups.update({"kerberos": request.user["kerberos"]}, {
        "$set": {
            "location": location,
            "timestamp": datetime.utcnow(),
            "cell": request.user["cell"],
            "name": request.user["name"]
        },
        "$setOnInsert": {
            "rushee": request.user["kerberos"],
        },
    }, upsert=True)
    return jsonify({"status": "ok"})

@app.route("/vans", methods=["POST", "GET"])
@cache.cached(timeout=1)
def vans():
    vans = [row for row in mongo.db.vans.find({}, {'_id': False})]
    out = []
    for van in vans:
        route = []
        done = True
        for x in van["route"]:
            if x == van["current_location"]:
                done = False
            route.append({
                "location": x,
                "done": done
            })
        if van["drivers"]:
            copilot = van["drivers"][-1]
            copilot_b = mongo.db.brothers.find_one({"kerberos": copilot})
            cell = copilot_b["cell"]
        else:
            cell = None
        out.append({
            "current_location": van["current_location"],
            "drivers": van["drivers"],
            "route": route,
            "full": van["full"],
            "contact": cell})
    return jsonify({"vans": out})

def van_status():
    van = mongo.db.vans.find_one({"drivers": request.user["kerberos"]},
                                 {"_id": False})
    if not van:
        return jsonify({"error": "You are not a driver."})

    requests = mongo.db.pickups.find({}, {"_id": False})
    requests_by_location = {}
    for r in requests:
        requests_by_location.setdefault(r["location"], [])
        requests_by_location[r["location"]].append(r)
    route = []
    done = True
    for x in van["route"]:
        if x == van["current_location"]:
            done = False
        reqs = requests_by_location.get(x, [])
        route.append({
            "location": x,
            "requests": reqs,
            "headcount": len(reqs),
            "done": done
        })
    return jsonify({
        "current_location": van["current_location"],
        "drivers": van["drivers"],
        "route": route,
        "full": van["full"]})

@app.route("/vans/poll", methods=["GET"])
def poll_van():
    return van_status()

@app.route("/vans/clear/<location>", methods=["GET", "POST"])
def clear_location(location=None):
    assert location
    van = mongo.db.vans.find_one({"drivers": request.user["kerberos"]},
                                 {"_id": False})
    try:
        idx = van["route"].index(location)
    except IndexError:
        return jsonify({"error": "%s is not on route." % location})

    if location == "Theta Xi":
        return jsonify({"status": "ok"})
    if idx + 1 <= len(van["route"]):
        mongo.db.vans.update(van, {"$set": {"current_location": van["route"][idx+1]}},
            upsert=False, multi=False)
        van = mongo.db.vans.find_one({"drivers": request.user["kerberos"]},
                                     {"_id": False})

    if van is None:
        return jsonify({"error": "You are not a driver."})

    mongo.db.pickups.remove({"location": location})
    return van_status()

@app.route("/vans/full/<location>", methods=["GET", "POST"])
def full_location(location=None):
    assert location
    van = mongo.db.vans.find_one({"drivers": request.user["kerberos"]},
                                 {"_id": False})
    try:
        idx = van["route"].index(location)
    except IndexError:
        return jsonify({"error": "%s is not on route." % location})

    if location == "Theta Xi":
        return jsonify({"status": "ok"})
    if idx + 1 <= len(van["route"]):
        mongo.db.vans.update(van, {"$set": {"current_location": van["route"][idx+1], "full": True}},
            upsert=False, multi=False)
        van = mongo.db.vans.find_one({"drivers": request.user["kerberos"]},
                                     {"_id": False})

    if van is None:
        return jsonify({"error": "You are not a driver."})
    return van_status()

@app.route("/vans/move/<location>", methods=["GET", "POST"])
def move_location(location=None):
    assert location
    van = mongo.db.vans.find_one({"drivers": request.user["kerberos"]},
                                 {"_id": False})
    try:
        idx = van["route"].index(location)
    except IndexError:
        return jsonify({"error": "%s is not on route." % location})

    if location == "Theta Xi":
        return jsonify({"status": "ok"})
    if idx + 1 <= len(van["route"]):
        mongo.db.vans.update(van, {"$set": {"current_location": location}},
            upsert=False, multi=False)
        van = mongo.db.vans.find_one({"drivers": request.user["kerberos"]},
                                     {"_id": False})

    if van is None:
        return jsonify({"error": "You are not a driver."})
    return van_status()

@app.route("/vans/start", methods=["POST", "GET"])
def start_van():
    if not request.user["brother"]:
        return jsonify({"error": "You are not a brother!"})

    route_name = "West"
    drivers = []

    if request.method == "POST":
        j = request.get_json()
        route_name = j["route"]
        drivers = j["drivers"]
    if request.user["kerberos"] not in drivers:
        drivers.insert(0, request.user["kerberos"])

    for driver in drivers:
        if mongo.db.vans.find_one({"drivers": driver}):
            return jsonify({"error": "%s is already a driver for a running van!" % driver})

    route = mongo.db.routes.find_one({"name": route_name})
    if not route:
        return jsonify({"error": "Route %s does not exist." % route_name})

    van = {
        "drivers": drivers,
        "route": route["locations"],
        "current_location": route["locations"][0],
        "full": False
    }
    mongo.db.vans.insert(van)
    return van_status()

@app.route("/vans/end", methods=["GET", "POST"])
def end_van():
    van = mongo.db.vans.find_one({"drivers": request.user["kerberos"]})
    if not van:
        return jsonify({"error": "You are not driving a van."})
    mongo.db.vans.remove(van)
    return jsonify({"status": "ok"})

@app.route("/vans/end/<kerberos>", methods=["GET", "POST"])
def coordinator_end_van(kerberos=None):
    if not request.user["brother"] or not request.user["coordinator"]:
        return jsonify({"error": "You are not a coordinator."})
    van = mongo.db.vans.find_one({"drivers": kerberos})
    if not van:
        return jsonify({"error": "%s is not driving a van." % kerberos})
    mongo.db.vans.remove(van)
    return jsonify({"status": "ok"})

@app.route("/events", methods=["GET"])
@cache.cached(timeout=30)
def events():
    csv = get_spreadsheet(2136412199)
    days = {}
    days_order = []
    for row in csv:
        day = row["Day of Week"]
        if day not in days_order:
            days_order.append(day)
        days.setdefault(day, {"name": day, "events": []})
        days[day]["events"].append(row)
    output = [days[day] for day in days_order]
    return jsonify({"days": output, "timestamp": int(time.time())})


if __name__ == "__main__":
    app.debug = bool(os.getenv("DEBUG", True))
    app.logger.debug("Application started.")
    app.run(port=5001)
