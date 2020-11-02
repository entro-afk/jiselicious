from discord.ext import commands
from discord.utils import get
import yaml
from trello import TrelloClient, exceptions
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import re
from gyazo import Api
from urllib.parse import urlparse
from os.path import splitext, basename
import aiohttp
from sqlalchemy import *
import json
import os
import datetime
from discord import File, Member, Role, PermissionOverwrite, Embed
import requests
import time
import asyncio
import threading
import dateutil.parser
import pytz
import random
import redis
import math
client = commands.Bot(command_prefix='+')

with open(r'jiselConf.yaml') as file:
    # The FullLoader parameter handles the conversion from YAML
    # scalar values to Python the dictionary format
    jiselConf = yaml.load(file, Loader=yaml.FullLoader)

    print(jiselConf)

gyazo_client = Api(access_token=jiselConf['gyazo_token'])

trello_client = TrelloClient(
    api_key=jiselConf['trello']['api_key'],
    api_secret=jiselConf['trello']['api_secret'],
    token=jiselConf['trello']['token'],
)

scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

credentials = ServiceAccountCredentials.from_json_keyfile_name(jiselConf['goog'], scope)  # Your json file here
r = redis.Redis(host='localhost', port=6379, db=0)

gc = gspread.authorize(credentials)
curr_minute = datetime.datetime.now().minute
random_minute = random.randint(0, 30)

def get_questions():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            questions = []
            questions_table = Table('triviaQuestions', metadata, autoload=True, autoload_with=conn)
            select_st = select([questions_table])
            res = conn.execute(select_st)
            for row in res:
                question = row[1]
                questions.append({
                    "id": row[0],
                    "question": question,
                })
            return questions
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

trivia_questions = get_questions()

def event_handler(msg):
    print("Handler", msg)
    try:
        key = msg["data"].decode("utf-8")
        # If shadowKey is there then it means we need to proceed or else just ignore it
        if "shadowKey" in key:
            # To get original key we are removing the shadowKey prefix
            key = key.replace("shadowKey:", "")
            value = r.get(key)
            # Once we got to know the value we remove it from Redis and do whatever required
            r.delete(key)
            print("Got Value: ", value)
    except Exception as exp:
        pass


@client.event
async def on_ready():
    print('Bot is ready.')
    while True:
        try:
            await update_trello_cards_and_time()
            await asyncio.sleep(3.0)
        except Exception as err:
            print(err)

def check_if_card_contains_codes(card):
    for text in re.split(r"\s+|\n", card.description):
        if len(text) == 8 and text[0:3] in jiselConf['code_prefixes']:
            return True
    return False
def find_number_of_codes_needed(card):
    for text in re.split(r"\n", card.description):
        if any(word in text.lower() for word in ['round', 'win']):
            return int(re.findall('\d+', text)[0])

def append_random_codes(card, number_of_codes):
    if number_of_codes > 7:
        number_of_codes = 5
    prefixes_needed = []
    for i in range(number_of_codes):
        random_i = random.randint(0, len(jiselConf['random_prefixes']) - 1)
        prefixes_needed.append(jiselConf['random_prefixes'][random_i])
    codes_wks = gc.open("PWM Discord - Event Codes (Fixed for Jiselicious)").worksheet("Hosters")

    data = codes_wks.get_all_values()
    codes_obtained = []
    back_up_codes = []
    for r in range(len(data)):
        for c in range(len(data[r])):
            for prefix in list(prefixes_needed):
                if data[r][c].startswith(prefix.upper()) and len(data[r][c]) == 8 and data[r][c] not in codes_obtained:
                    codes_obtained.append(data[r][c])
                    prefixes_needed.remove(prefix)
                    codes_wks.update_cell(r + 1, c + 1, " ")
                    if prefixes_needed is None:
                        break
    codes_sent = "These are your codes:\n" + "       ".join(codes_obtained)

    card.set_description(card.description + f"\n{codes_sent}")
async def update_trello_cards_and_time():
    global has_asked_a_question
    global random_minute



    try:
        now = datetime.datetime.now()
        guild = client.get_guild(jiselConf['guild_id'])
        curr_question_has_not_expired = r.get('currtriviaexists')
        if not curr_question_has_not_expired:
            curr_question_id = get_current_trivia_question_id()
            trivia_of_hour_msg_id = r.get('lastmessageid')
            trivia_channel = get(guild.text_channels, name=jiselConf['trivia_channel'])
            if curr_question_id:
                result_remove_curr_trivia = remove_current_trivia()
                if result_remove_curr_trivia:
                    private_bot_feedback_channel = get(guild.text_channels, name=jiselConf['bot_feed_back_channel']['name'])
                    private_embed = Embed(title=f"Question of The Hour (ID#{curr_question_id}) has expired", description=f"No one was able to correctly answer the expired question.", color=16426522)
                    embed = Embed(title="Current Question for this hour has expired", description=f"No one was able to correctly answer the expired question.", color=16426522)
                    await private_bot_feedback_channel.send(embed=private_embed)
                    await trivia_channel.send(embed=embed)
            if trivia_of_hour_msg_id:
                question_of_the_hour_message = await trivia_channel.fetch_message(int(trivia_of_hour_msg_id))
                if question_of_the_hour_message:
                    await question_of_the_hour_message.delete()
                    r.delete('lastmessageid')

        if now.weekday() == int(r.get('weekdayend')) and now.hour == int(r.get('hourend')) and r.get('minuteend') >= int(r.get('minuteend')):
            top_3 = get_trivia_leader_board()
            if top_3:
                list_leader = []
                i=1
                for leader in top_3:
                    row_leader = f"\n{i if i >1 else '🏆'} - <@!{leader['id']}> ({leader['score']} points)"
                    i += 1
                    list_leader.append(row_leader)
                stringified_top_3 = '\n'.join(list_leader)
                embed = Embed(title="Weekly Leader Board", description=f"This week's Trivia Leaderboard:\n{stringified_top_3}\n\nCongratulations to <@!{top_3[0]['id']}>! 🎉 You've won this week's Trivia.\nA moderator will contact you privately with your prize.\n\n**Keep participating to find out who will be the next Trivia Master of the week!**", color=0x00ff00)
                trivia_channel = get(guild.text_channels, name=jiselConf['trivia_channel'])
                await trivia_channel.send("", embed=embed)
                clear_trivia_leaderboard()
                private_bot_feedback_channel = get(guild.text_channels, name=jiselConf['bot_feed_back_channel']['name'])
                embed = Embed(title="Success", description=f"Trivia Leaderboard Cleared", color=0x00ff00)
                await private_bot_feedback_channel.send(embed=embed)
        if now.minute >= random_minute:
            print('The random minute------', random_minute)
            last_hour = r.get('lasthour')
            print('The last hour------', last_hour)
            if last_hour:
                last_hour = int(last_hour)
                print('The last hour integer------', last_hour)
            if now.hour != last_hour:
                if last_hour:
                    r.delete('lasthour')
                print('Got random minute------', now.minute)
                await ask_a_question()
                random_minute = random.randint(0, 30)
                r.set('lasthour', str(now.hour))
        last_interval_update = r.get('last5MinuteUpdate')
        if last_interval_update:
            last_interval_update = int(last_interval_update)
        if now.minute % 5 == 0 and now.minute != last_interval_update:
            print('started updating time-------------', datetime.datetime.now().time())
            await update_time()
            r.set('last5MinuteUpdate', now.minute)
            print('finished updating times---------------', datetime.datetime.now().time())
    except Exception as err:
        print(err)



async def update_time():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")

    try:
        with db.connect() as conn:
            channel_time_table = Table('timeChannels', metadata, autoload=True, autoload_with=conn)
            select_st = select([channel_time_table])
            res = conn.execute(select_st)

            for _row in res:
                former_name = _row[0]
                now_time = datetime.datetime.today().now(pytz.timezone(_row[3])).strftime('%H:%M')
                if _row[0] != f"⌚ {_row[1]}: {now_time}":
                    update_statement = channel_time_table.update().values(
                        channelName=f"⌚ {_row[1]}: {now_time}").where(
                        and_(
                            channel_time_table.c.channelName != f"⌚ {_row[1]}: {now_time}",
                            channel_time_table.c.channelID == _row[2]
                        )
                    )
                    res = conn.execute(update_statement)
                    await client.wait_until_ready()
                    guild = client.get_guild(_row[5])
                    if guild:
                        channel = get(guild.voice_channels, id=int(_row[2]))
                        if channel:
                            await channel.edit(name=f"⌚ {_row[1]}: {now_time}")
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()



def set_current_question(question_id):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            current_question_table = Table('currentQuestion', metadata, autoload=True, autoload_with=conn)
            insert_statement = current_question_table.insert().values(question_id=question_id)
            conn.execute(insert_statement)
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

def get_question_by_id(question_id):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            questions_table = Table('triviaQuestions', metadata, autoload=True, autoload_with=conn)
            select_st = select([questions_table]).where(questions_table.c.id == question_id)
            res = conn.execute(select_st)
            for row in res:
                return {
                    "question": row[1],
                    "time_asked": row[2]
                }
            return None
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

def remove_current_trivia():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            curr_question_table = Table('currentQuestion', metadata, autoload=True, autoload_with=conn)
            delete_query = f"DELETE FROM pwm.\"currentQuestion\""
            res = conn.execute(delete_query)
            return True
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

async def ask_a_question():
    guild = client.get_guild(jiselConf['guild_id'])
    trivia_channel = get(guild.text_channels, name=jiselConf['trivia_channel'])
    print('asking a question-------------', datetime.datetime.now().time())
    if trivia_channel:
        x = random.randint(0, len(trivia_questions)-1)
        embed = Embed(title=f"It's Trivia Time! You have {str(jiselConf['expiration_seconds']) if jiselConf['expiration_seconds'] < 100 else str(math.floor(jiselConf['expiration_seconds']/60))} {'seconds' if jiselConf['expiration_seconds'] < 100 else 'minutes'} to answer before the following question expires:", description=f"{trivia_questions[x]['question']}", color=7506394)
        curr_question_has_not_expired = r.get('currtriviaexists')
        if not curr_question_has_not_expired:
            print('question has expired so clearing curr question table-------------', datetime.datetime.now().time())
            result_remove_curr_trivia = remove_current_trivia()
            if result_remove_curr_trivia:
                set_current_question(trivia_questions[x]['id'])
                curr_trivia_message = await trivia_channel.send(embed=embed)
                r.set('currtriviaexists', str(curr_trivia_message.id))
                r.set('lastmessageid', str(curr_trivia_message.id))
                print('setting an expiration after asking a question-------------', datetime.datetime.now().time())
                r.expire('currtriviaexists', jiselConf['expiration_seconds'])

def get_trivia_leader_board():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            participants = []
            leaderboard_table = Table('triviaLeaderboard', metadata, autoload=True, autoload_with=conn)
            select_st = select([leaderboard_table]).order_by(leaderboard_table.c.score.desc(), leaderboard_table.c.lastUpdated)
            res = conn.execute(select_st)
            for _row in res:
                participants.append({
                    'id': _row[0],
                    'name': _row[1],
                    'score': _row[2]
                })
            return participants[0:3]
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

def clear_trivia_leaderboard():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            delete_query = "DELETE FROM pwm.\"triviaLeaderboard\""
            res = conn.execute(delete_query)
            return True
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

def get_current_trivia_question_id():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            curr_question_table = Table('currentQuestion', metadata, autoload=True, autoload_with=conn)
            select_st = select([curr_question_table])
            res = conn.execute(select_st)
            for _row in res:
                return _row[1]
            return None
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

# test token
# client.run(channelsConf['test_bot_token'])
# pwm token
client.run(jiselConf['bot_token'])

# pm2 reload antiPerms.py --interpreter=python3


