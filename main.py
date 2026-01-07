import os
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from urllib.parse import urlparse
import psycopg2
import requests
import time
from nacl.signing import VerifyKey
from sentry import tunnel_bp
import logging
import json
app = Flask(__name__)
app.register_blueprint(tunnel_bp)

cors = CORS(app,resources={r"/*": {"origins": "https://1445980061390999564.discordsays.com"}})

DB_GUESS_NAME = "public.guesses"
DB_GUESS_COLUMN = '("user_id","high","low","date","guess_cnt","avatar","username","game_completed")'
DB_GUESS_FORMAT = "'{user_id}',{high},{low},{date},{guess_cnt},'{avatar}','{username}',{game_completed}"

clientID = os.environ.get("CLIENT_ID", "")
clientSec = os.environ.get("CLIENT_SEC", "")
clientPub = os.environ.get("CLIENT_PUB", "")
API_ENDPOINT = os.environ.get("API_ENDPOINT", "")
redirectURI = os.environ.get("REDIRECT_URI", "")
DB_URL = os.environ.get("DB_URL", "")
interaction_dict = {}
logging.basicConfig(level=logging.DEBUG)
with open('games.json','r') as file:
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
            host=hostname
        )
    except:
        return False
def getDate():
    return int(((time.time())//86400)%3399)
def httpLog(r,fMsg,sMsg):
    if r.status_code > 200:
        logging.error(str(r.status_code)+" "+fMsg)
        logging.error(r.text)
    else:
        logging.info(sMsg)
@app.route("/",methods=["OPTIONS","GET"])
def main():
    if request.method=="GET":
        return "hello world"
    elif request.method=="OPTIONS":
        print(request.environ.get('HTTP_ORIGIN', 'default value'))
        print("options requested")
        return {},200,{"Access-Control-Allow-Origin":"https://1445980061390999564.discordsays.com",
          "Access-Control-Allow-Credentials": True,
          "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
          "Access-Control-Allow-Headers":"*",
                       "Access-Control-Max-Age":86400}
@app.route("/auth",methods=["POST"])
def getAuthToken():
    if request.method == "POST":
        code = request.json.get("code")
        print(code)
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirectURI
        }
        headers = {"Content-Type":'application/x-www-form-urlencoded'}
        r = requests.post('%s/oauth2/token' % API_ENDPOINT, data=data, headers=headers, auth=(clientID,clientSec))
        print(r,"token")
        httpLog(r,"oAuth failed","oAuth success")
        r.raise_for_status()
        return r.json()
@app.route("/updateMsg",methods=["POST"])
def updateMsg():
    if request.method == "POST":
        signature = request.headers.get("X-Signature-Ed25519")
        timestamp = request.headers.get("X-Signature-Timestamp")
        type = request.json.get("type")
        body = request.data.decode("utf-8")
        verify = VerifyKey(bytes.fromhex(clientPub))
        print(request.data)
        print(type,body)
        logging.info("{type} ping recieved".format(type=type))
        try:
            verify.verify(f'{timestamp}{body}'.encode(),bytes.fromhex(signature))
        except:
            print("error verifying")
            raise
        if type == 1:
            print("Ping recieved")
            return jsonify({
                "type": 1
            })
        elif type == 2:
            print("app command")
            print(request.json)
            if "user" in request.json:
                userID = request.json.get("user").get("id")
            else:
                userID = request.json.get("member").get("user").get("id")
            if userID:
                token = request.json.get("token")
                interaction_dict[userID] = token
                return jsonify({
                    "type": 12
                })
            else:
                raise Exception("User ID not found on app launch")
        elif type == 3:
            print("button launch command")
            print(request.json)
            userID = request.json.get("message").get("interaction_metadata").get("user").get("id")
            if userID:
                print(request.json)
                print(userID)
                token = request.json.get("token")
                interaction_dict[userID] = token
                return jsonify({
                    "type": 12
                })
            else:
                raise Exception("User ID not found on button ping")
@app.route("/guess",methods=["POST","GET"])
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
        print("avatar",avatar)
        print("username",username)
        if isHigh:
            print("is high")
            curr = conn.cursor()
            curr.execute('''
            BEGIN;
            UPDATE {name} SET
            high={high},avatar='{avatar}',username='{username}', guess_cnt = guess_cnt + 1, game_completed={gameCompleted}
            WHERE user_id='{userID}' AND date={date};
            INSERT INTO {name} 
            {columns}
            SELECT 
            {data}
            WHERE NOT EXISTS (SELECT 1 FROM {name} WHERE 
            user_id='{userID}' AND date={date});
            COMMIT;
            '''.format(
                name=DB_GUESS_NAME,
                high=guess,
                columns=DB_GUESS_COLUMN,
                userID=userID,
                date=date,
                avatar=avatar,
                username=username,
                gameCompleted=gameCompleted,
                data=DB_GUESS_FORMAT.format(
                    user_id=userID,
                    high=guess,
                    low=0,
                    date=date,
                    guess_cnt=0,
                    avatar=avatar,
                    username=username,
                    game_completed=gameCompleted
                )))

        elif isLow:
            print("is low")
            curr = conn.cursor()
            curr.execute('''
            BEGIN;
            UPDATE {name} SET
            low={low},avatar='{avatar}',username='{username}', guess_cnt = guess_cnt + 1, game_completed={gameCompleted}
            WHERE user_id='{userID}' AND date={date};
            INSERT INTO {name} 
            {columns}
            SELECT 
            {data}
            WHERE NOT EXISTS (SELECT 1 FROM {name} WHERE 
            user_id='{userID}' AND date={date});
            COMMIT;
            '''.format(
                name=DB_GUESS_NAME,
                low=guess,
                columns=DB_GUESS_COLUMN,
                userID=userID,
                date=date,
                avatar=avatar,
                username=username,
                gameCompleted=gameCompleted,
                data=DB_GUESS_FORMAT.format(
                    user_id=userID,
                    high=0,
                    low=guess,
                    date=date,
                    guess_cnt=0,
                    avatar=avatar,
                    username=username,
                    game_completed=gameCompleted
                )))
        msg = ""
        if gameCompleted:
            msg = "{user} got today's item in {guessCnt} guesses".format(user=username, guessCnt=guessCnt)
        elif not gameCompleted and guessCnt == 5:
            msg = "Better luck tomorrow {user}!".format(user=username)
        component = [{"type":1,
                      "components":
                          [{"type":2,
                            "custom_id":"launch",
                            "style":1,
                            "label":"Play"
                            }]
                      }]
        url = "https://discord.com/api/v10/webhooks/{appID}/{intToken}".format(appID=clientID,
                                                                               intToken=interaction_dict[userID])
        json = {
            "content": msg,
            "components":component
        }
        if len(msg)>0:
            r = requests.post(url, json=json)
            httpLog(r,"guess update failure","guess update success")
            r.raise_for_status()
            conn.close()
        return Response("posted",status=200)
    elif request.method == "GET" and conn:
        userID = request.args.get("userID")
        curr = conn.cursor()
        curr.execute('''
        SELECT * FROM {name}
        WHERE user_id = '{userID}' AND date={date};
        '''.format(userID=userID,date=getDate(),name=DB_GUESS_NAME))
        data =curr.fetchall()
        results = []
        for i in data:
            results.append(i)
        conn.close()
        return results

@app.route("/channel",methods=["GET","POST"])
def channelDB():
    conn = get_connection()
    if request.method == "GET" and conn:
        channelID = request.args.get("channelID")
        curr = conn.cursor()
        curr.execute('''
                SELECT * FROM {name}
                WHERE '{channelID}'=ANY(channel_ids) AND date={date};
                '''.format(channelID=channelID,date=getDate(), name=DB_GUESS_NAME))
        data = curr.fetchall()
        results = []
        for i in data:
            results.append(i)
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
        SET channel_ids = array_append(COALESCE(channel_ids, '{{}}'),'{channelID}') 
        WHERE date = {date} AND user_id = '{userID}' AND NOT ('{channelID}' = ANY(COALESCE(channel_ids, '{{}}')));
        COMMIT;'''.format(
            channelID=channelID,
            date=getDate(),
            userID=userID,
            name=DB_GUESS_NAME
        ))
        logging.info("channel post success")
        return Response("posted", status=200)
@app.route("/game",methods=["GET"])
def getGame():
    date = getDate()
    game = gameData["game-"+str(date)]
    logging.info("game retrieved")
    logging.info(game)
    return {"date":date,
            "game":game}

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))