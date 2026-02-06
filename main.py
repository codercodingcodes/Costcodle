import os
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from urllib.parse import urlparse
import psycopg2
import requests
import time
from nacl.signing import VerifyKey
from sentry import tunnel_bp
import sentry_sdk
import logging
import json

app = Flask(__name__)
app.register_blueprint(tunnel_bp)

cors = CORS(app, resources={r"/*": {"origins": "https://1445980061390999564.discordsays.com"}})

sentry_sdk.init(
    dsn="https://b57458227a52237b9a973fa466c31d14@o4510660094787584.ingest.us.sentry.io/4510660099112960",
    enable_logs=True
)

DB_GUESS_NAME = "public.guesses"
DB_WEBHOOK_NAME = "public.interaction"
DB_GUESS_COLUMN = '("user_id","high","low","date","guess_cnt","avatar","username","game_completed")'
DB_WEBHOOK_COLUMN = '("user_id","interaction_id","session_id")'

clientID = os.environ.get("CLIENT_ID", "")
clientSec = os.environ.get("CLIENT_SEC", "")
clientPub = os.environ.get("CLIENT_PUB", "")
API_ENDPOINT = os.environ.get("API_ENDPOINT", "")
redirectURI = os.environ.get("REDIRECT_URI", "")
DB_URL = os.environ.get("DB_URL", "")

logging.basicConfig(level=logging.DEBUG)
with open('games.json', 'r') as file:
    gameData = json.load(file)


def get_connection():
    result = urlparse(DB_URL)
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    try:
        return psycopg2.connect(
            database=database,
            user=username,
            password=password,
            host=hostname,
            connect_timeout=10
        )
    except:
        logging.error("DB connection failed")
        return False


def getDate():
    return int((((time.time()) // 86400)+100) % 3399)


def getTime():
    return int(time.time() % 86400)


def httpLog(r, fMsg, sMsg):
    if r.status_code != 200:
        logging.error(str(r.status_code) + " " + fMsg)
        logging.error(r.text)
    else:
        logging.info(r.status_code)
        logging.info(r.text)
        logging.info(sMsg)


def getInterID(userID,sessionID=""):
    conn = get_connection()
    curr = conn.cursor()
    if len(sessionID)>0:
        curr.execute('''
        SELECT * FROM {name}
        WHERE user_id=%(userID)s OR session_id=%(sessionID)s;
        '''.format(
            name=DB_WEBHOOK_NAME), {'userID': userID,'sessionID':sessionID})

    else:
        curr.execute('''
        SELECT * FROM {name}
        WHERE user_id=%(userID)s;
        '''.format(
            name=DB_WEBHOOK_NAME), {'userID': userID})
    data = curr.fetchall()
    results = []
    for i in data:
        results.append(i)
    conn.close()
    logging.info("results")
    logging.info(results)
    if len(results)>0:
        return results[0][2]
    else:
        return ""


def updateInterID(userID, interactionID, sessionID):
    conn = get_connection()
    curr = conn.cursor()
    curr.execute('''
            UPDATE {name} SET
            interaction_id=%(interactionID)s, session_id=%(sessionID)s
            WHERE user_id=%(userID)s;
            INSERT INTO {name} 
            {columns}
            SELECT 
            %(userID)s,%(interactionID)s,%(sessionID)s
            WHERE NOT EXISTS (SELECT 1 FROM {name} WHERE 
            user_id=%(userID)s);
                '''.format(
        name=DB_WEBHOOK_NAME, columns=DB_WEBHOOK_COLUMN), {'userID': userID, 'interactionID': interactionID,'sessionID':sessionID})
    rowCnt = curr.rowcount
    conn.commit()
    curr.close()
    conn.close()

    if rowCnt > 0:
        logging.info("user interaction updated")
    else:
        logging.error("no rows updated for user interaction")
    return rowCnt


@app.route("/", methods=["OPTIONS", "GET"])
def main():
    if request.method == "GET":
        return "hello world"
    elif request.method == "OPTIONS":
        print(request.environ.get('HTTP_ORIGIN', 'default value'))
        print("options requested")
        return {}, 200, {"Access-Control-Allow-Origin": "https://1445980061390999564.discordsays.com",
                         "Access-Control-Allow-Credentials": True,
                         "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                         "Access-Control-Allow-Headers": "*",
                         "Access-Control-Max-Age": 86400}
    # elif request.method == "POST":
    #     API_ENDPOINT = 'https://discord.com/api/v10'
    #
    #     data = {
    #         'grant_type': 'client_credentials',
    #         'scope': 'applications.commands.update'
    #     }
    #     headers = {
    #         'Content-Type': 'application/x-www-form-urlencoded'
    #     }
    #     r = requests.post('%s/oauth2/token' % API_ENDPOINT, data=data, headers=headers,
    #                       auth=(clientID, clientSec))
    #     r.raise_for_status()
    #     data = r.json()
    #     token = data["access_token"]
    #     url = "https://discord.com/api/v10/applications/{appID}/commands".format(appID=clientID)
    #
    #     # This is an example CHAT_INPUT or Slash Command, with a type of 1
    #     json = {
    #         "name": "play",
    #         "type": 1,
    #         "description": "play costcodle in your channel"
    #     }
    #
    #     # or a client credentials token for your app with the applications.commands.update scope
    #     headers = {
    #         "Authorization": "Bearer {token}".format(token=token)
    #     }
    #
    #     r = requests.post(url, headers=headers, json=json)
    #     r.raise_for_status()
    #     return r.json()


@app.route("/auth", methods=["POST"])
def getAuthToken():
    if request.method == "POST":
        code = request.json.get("code")
        print(code)
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirectURI
        }
        headers = {"Content-Type": 'application/x-www-form-urlencoded'}
        r = requests.post('%s/oauth2/token' % API_ENDPOINT, data=data, headers=headers, auth=(clientID, clientSec))
        print(r, "token")
        httpLog(r, "oAuth failed", "oAuth success")
        r.raise_for_status()
        return r.json()


@app.route("/updateMsg", methods=["POST"])
def updateMsg():
    if request.method == "POST":
        signature = request.headers.get("X-Signature-Ed25519")
        timestamp = request.headers.get("X-Signature-Timestamp")
        type = request.json.get("type")
        body = request.data.decode("utf-8")
        verify = VerifyKey(bytes.fromhex(clientPub))
        print(request.data)
        print(type, body)
        logging.info("{type} ping recieved".format(type=type))
        try:
            verify.verify(f'{timestamp}{body}'.encode(), bytes.fromhex(signature))
        except:
            logging.error("ping verification failed")
            raise
        if type == 1:
            print("Ping recieved")
            return jsonify({
                "type": 1
            })
        elif type == 2:
            logging.info("app launch")
            print("app command")
            print(request.json)
            if "user" in request.json:
                userID = request.json.get("user").get("id")
            else:
                userID = request.json.get("member").get("user").get("id")
            if userID:
                token = request.json.get("token")
                updateInterID(userID, token,"")
                logging.info(userID)
                logging.info(token)
                logging.info(request.json)
                return jsonify({
                    "type": 12
                })
            else:
                logging.info(request.json)
                logging.error("user ID not found on app launch")
                raise Exception("User ID not found on app launch")
        elif type == 3:
            logging.info("button launch")
            print("button launch command")
            print(request.json)
            if "user" in request.json:
                userID = request.json.get("user").get("id")
            else:
                userID = request.json.get("member").get("user").get("id")
            if userID:
                print(request.json)
                print(userID)
                token = request.json.get("token")
                updateInterID(userID, token,"")
                logging.info(userID)
                logging.info(token)
                logging.info(request.json)
                return jsonify({
                    "type": 12
                })
            else:
                logging.info(request.json)
                logging.error("user ID not found on app launch")
                raise Exception("User ID not found on button ping")


@app.route("/guess", methods=["POST", "GET"])
def guessDB():
    conn = get_connection()
    if request.method == "POST" and conn:
        date = getDate()
        print(request.json)
        guess = request.json["guess"]
        userID = request.json["userID"]
        isHigh = request.json["isHigh"]
        isLow = request.json["isLow"]
        avatar = request.json["avatar"]
        username = request.json["username"]
        gameCompleted = request.json["gameCompleted"]
        guessCnt = int(request.json["guessCnt"]) + 1
        print("avatar", avatar)
        print("username", username)
        curr = conn.cursor()
        if isHigh:
            print("is high")
            curr.execute('''
            BEGIN;
            UPDATE {name} SET
            high=%(high)s,avatar=%(avatar)s,username=%(username)s, guess_cnt = guess_cnt + 1, game_completed=%(gameCompleted)s
            WHERE user_id=%(userID)s AND date={date};
            INSERT INTO {name} 
            {columns}
            SELECT 
            %(userID)s,%(high)s,%(low)s,{date},%(guessCnt)s,%(avatar)s,%(username)s,%(gameCompleted)s
            WHERE NOT EXISTS (SELECT 1 FROM {name} WHERE 
            user_id=%(userID)s AND date={date});
            COMMIT;
            '''.format(
                name=DB_GUESS_NAME,
                columns=DB_GUESS_COLUMN,
                date=date), {'high': guess, 'avatar': avatar, 'username': username, 'gameCompleted': gameCompleted,
                             'guessCnt': guessCnt, 'low': 0, 'userID': userID})
        elif isLow:
            print("is low")
            curr.execute('''
                        BEGIN;
                        UPDATE {name} SET
                        low=%(low)s,avatar=%(avatar)s,username=%(username)s, guess_cnt = guess_cnt + 1, game_completed=%(gameCompleted)s
                        WHERE user_id=%(userID)s AND date={date};
                        INSERT INTO {name} 
                        {columns}
                        SELECT 
                        %(userID)s,%(high)s,%(low)s,{date},%(guessCnt)s,%(avatar)s,%(username)s,%(gameCompleted)s
                        WHERE NOT EXISTS (SELECT 1 FROM {name} WHERE 
                        user_id=%(userID)s AND date={date});
                        COMMIT;
                        '''.format(
                name=DB_GUESS_NAME,
                columns=DB_GUESS_COLUMN,
                date=date), {'high': 0, 'avatar': avatar, 'username': username, 'gameCompleted': gameCompleted,
                             'guessCnt': guessCnt, 'low': guess, 'userID': userID})
        msg = ""
        if gameCompleted:
            msg = "{user} got today's item in {guessCnt} guesses".format(user=username, guessCnt=guessCnt)
        elif not gameCompleted and guessCnt == 5:
            msg = "Better luck tomorrow {user}!".format(user=username)
        component = [{"type": 1,
                      "components":
                          [{"type": 2,
                            "custom_id": "launch",
                            "style": 1,
                            "label": "Play"
                            }]
                      }]
        embeds = [{"type": "image",
                   "image": {
                       "url": getGame()["game"]["image"],
                       "height": 100,
                       "width": 100
                   }}]
        intToken = getInterID(userID)
        if len(intToken)>0:
            url = "https://discord.com/api/v10/webhooks/{appID}/{intToken}".format(appID=clientID,
                                                                                   intToken=intToken)
            json = {
                "content": msg,
                "components": component,
                "embeds": embeds
            }
            if len(msg) > 0:
                r = requests.post(url, json=json)
                httpLog(r, "guess update failure", "guess update success")
                r.raise_for_status()
        else:
            curr.close()
            conn.close()
            return Response("No session id found", status=500)
        curr.close()
        conn.close()
        return Response("posted", status=200)
    elif request.method == "GET" and conn:
        userIDs = request.args.getlist("userID")
        getHistory = request.args.get("getHistory")
        if getHistory == 'true':
            curr = conn.cursor()
            userID_query = "("
            for i in userIDs:
                userID_query += "%s,"
            userID_query = userID_query[:-1]
            userID_query += ")"
            curr.execute('''
                        SELECT * FROM {name}
                        WHERE user_id IN {userIDs};
                        '''.format(name=DB_GUESS_NAME, userIDs=userID_query), tuple(userIDs))
            data = curr.fetchall()
            results = []
            for i in data:
                results.append(i)
            curr.close()
            conn.close()
            return results
        else:
            curr = conn.cursor()
            userID_query = "("
            for i in userIDs:
                userID_query += "%s,"
            userID_query = userID_query[:-1]
            userID_query += ")"
            curr.execute('''
                        SELECT * FROM {name}
                        WHERE date={date} AND user_id IN {userIDs};
                        '''.format(date=getDate(), name=DB_GUESS_NAME, userIDs=userID_query), tuple(userIDs))
            data = curr.fetchall()
            results = []
            for i in data:
                results.append(i)
            curr.close()
            conn.close()
            return results


@app.route("/channel", methods=["GET", "POST"])
def channelDB():
    conn = get_connection()
    if request.method == "GET" and conn:
        channelID = request.args.get("channelID")
        curr = conn.cursor()
        curr.execute('''
                SELECT * FROM {name}
                WHERE %(channelID)s=ANY(channel_ids) AND date={date};
                '''.format(date=getDate(), name=DB_GUESS_NAME), {'channelID': channelID})
        data = curr.fetchall()
        results = []
        for i in data:
            results.append(i)
        curr.close()
        conn.close()
        logging.info("channel get success")
        return results
    elif request.method == "POST" and conn:
        channelID = request.json["channelID"]
        userID = request.json["userID"]
        curr = conn.cursor()
        curr.execute('''
        BEGIN;
        UPDATE {name}
        SET channel_ids = array_append(COALESCE(channel_ids, '{{}}'),%(channelID)s) 
        WHERE date = {date} AND user_id = %(userID)s AND NOT (%(channelID)s = ANY(COALESCE(channel_ids, '{{}}')));
        COMMIT;'''.format(
            date=getDate(),
            name=DB_GUESS_NAME
        ), {'channelID': channelID, 'userID': userID})
        logging.info("channel post success")
        curr.close()
        conn.close()
        return Response("posted", status=200)


@app.route("/game", methods=["GET"])
def getGame():
    date = getDate()
    time = getTime()
    game = gameData["game-" + str(date)]
    logging.info("game retrieved")
    logging.info(game)
    return {"date": date,
            "game": game,
            "time": time}

@app.route("/register",methods=["POST"])
def register():
    sessionID = request.json["sessionID"]
    userID = request.json["userID"]
    interID = getInterID(userID,sessionID)
    logging.info(sessionID)
    logging.info(userID)
    logging.info(interID)
    rowCnt = updateInterID(userID,interID,sessionID)
    if rowCnt>0:
        logging.info("user registration success")
        return Response("registered",status=200)
    else:
        logging.error("user registration failed: no updates")
        return Response("registration failed, user not updated",status=500)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
