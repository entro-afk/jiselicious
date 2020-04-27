from discord.ext import commands
import yaml
from trello import TrelloClient
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
from discord import File
import requests


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

gc = gspread.authorize(credentials)


@client.event
async def on_ready():
    print('Bot is ready.')

@client.command(pass_context=True, name='logshome')
async def get_homestead_alarms_log(ctx):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string, echo=True)
    metadata = MetaData(schema="homesteadProduction")

    with db.connect() as conn:
        table = Table('alarmsLog', metadata, autoload=True, autoload_with=conn)
        select_st = select([table])
        res = conn.execute(select_st)
        # column_names = [c["name"] for c in res.column_descriptions]
        result = [{column: value for column, value in rowproxy.items()} for rowproxy in res]
        now_time = datetime.datetime.now()
        if not os.path.exists('jsonFiles'):
            os.makedirs('jsonFiles')
        try:
            with open(f'jsonFiles/{now_time.strftime("%m%d%Y_%H%M%S")}_logs.json', 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=4, sort_keys=True, default=str)
        except Exception as err:
            ctx.send(f"Jiselicious could not create the file for the logs due to the following error {err}")
            raise err
        await ctx.send(f'***Homestead Log for {now_time.strftime("%m/%d/%Y %H:%M:%S")}***', file=File(f'jsonFiles/{now_time.strftime("%m%d%Y_%H%M%S")}_logs.json'))
        os.remove(f'jsonFiles/{now_time.strftime("%m%d%Y_%H%M%S")}_logs.json')
        json_link = get_json_blob_link(str(result))
        await ctx.send(json_link)

def get_json_blob_link(json_data):
    API_ENDPOINT = "https://hastebin.com/documents"
    r = requests.post(url=API_ENDPOINT, data=json_data)
    return f"https://hastebin.com/{r.json()['key']}"

@client.event
async def on_message(message):
    if message.channel.name in jiselConf['event_request_channel'] and ("Server:".upper() in message.clean_content.upper() or message.clean_content.upper().startswith("Server".upper())):
        board = trello_client.get_board(jiselConf['trello']['board_id'])
        request_list = board.get_list(jiselConf['trello']['list_id'])
        request_list.add_card(message.author.nick or message.author.name, message.clean_content)
    if message.channel.name in ["bug-report","event-submissions"]:
        wks = gc.open("PWM bug report chart").worksheet("Hoja 1")

        data = wks.get_all_values()
        headers = data[0]

        df = pd.DataFrame(data, columns=headers)
        print(df.head())
        # NO.   Submitter/Server        BUG details     Resolution      Screenshot
        if message.clean_content.lower().startswith("NO.".lower()):
            split_text = message.clean_content.rstrip("\n\r").split("\n")
            bug_number = re.sub("NO.", '', split_text[0]).strip()
            bug_submitter = re.sub("Submitter/Server:", '', split_text[1]).strip()
            bug_details = re.sub("BUG details:", '', split_text[2]).strip()
            screenshot = re.sub("Screenshot:|Screenshot", '', split_text[3]).strip()
            bug_resolution = ""
            row = [bug_number, bug_submitter, bug_details, bug_resolution]
            if "gyazo" in screenshot:
                if screenshot.startswith("https://gyazo.com/"):
                    image_url = gyazo_client.get_image(re.sub(f'https://gyazo.com/', '', screenshot)).url
                    file_ext = image_url.split(".")[-1]
                    row.append(f"=IMAGE(\"{re.sub(file_ext, file_ext.upper(), image_url)}\")")
                    wks.insert_row(row, df.shape[0] + 2, value_input_option='USER_ENTERED')
            elif message.attachments:
                async with aiohttp.ClientSession() as session:
                    async with session.get(message.attachments[0].url) as r:
                        if r.status == 200:
                            result = await r.read()
                            row.append(f"=IMAGE(\"{message.attachments[0].url}\")")
                            wks.insert_row(row, df.shape[0] + 2, value_input_option='USER_ENTERED')
            else:
                row.append(screenshot)
                wks.insert_row(row, df.shape[0] + 1, value_input_option='USER_ENTERED')
        elif message.attachments:
            async with aiohttp.ClientSession() as session:
                async with session.get(message.attachments[0].url) as r:
                    if r.status == 200:
                        result = await r.read()
                        row = ["Continuation", "", "", "", f"=IMAGE(\"{message.attachments[0].url}\")"]
                        wks.insert_row(row, df.shape[0] + 1, value_input_option='USER_ENTERED')
    await client.process_commands(message)



# test token
# client.run(channelsConf['test_bot_token'])
# pwm token
client.run(jiselConf['bot_token'])

# pm2 reload jisel.py --interpreter=python3
