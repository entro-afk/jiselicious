from discord.ext import commands
from discord.utils import get
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
from discord import File, Member, Role, PermissionOverwrite, ChannelType
import requests
import time
import asyncio
import threading
from typing import Union
from remoteGoogImage import detect_text_uri
import pytz

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
    while True:
        try:
            await check_if_which_db_time_channels_need_update()
        except Exception as err:
            print(err)

async def check_if_which_db_time_channels_need_update():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")

    with db.connect() as conn:
        try:
            channel_time_table = Table('timeChannels', metadata, autoload=True, autoload_with=conn)
            select_st = select([channel_time_table])
            res = conn.execute(select_st)
            for _row in res:
                former_name = _row[0]
                now_time = datetime.datetime.today().now(pytz.timezone(_row[3])).strftime('%H:%M')
                if _row[0] != f"⌚ {_row[1]}'s time: {now_time}":
                    update_statement = channel_time_table.update().values(
                        channelName=f"⌚ {_row[1]}'s time: {now_time}").where(
                        and_(
                            channel_time_table.c.channelName != f"⌚ {_row[1]}'s time: {now_time}",
                            channel_time_table.c.channelID == _row[2]
                        )
                    )
                    res = conn.execute(update_statement)
                    await client.wait_until_ready()
                    guild = client.get_guild(jiselConf['guild_id'])
                    print(guild)
                    print(guild.voice_channels)
                    channel = get(guild.voice_channels, id=_row[2])
                    print(channel)
                    await channel.edit(name=f"⌚ {_row[1]}'s time: {now_time}")
        except Exception as err:
            print(err)
            if conn:
                conn.close()
            db.dispose()
    db.dispose()

client.run(jiselConf['bot_token'])

# pm2 reload homesteadNotifier.py --interpreter=python3

