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
            await check_if_reminder_needed()
        except Exception as err:
            print(err)

async def check_if_reminder_needed():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")

    try:
        with db.connect() as conn:
            trello_hoster_cards_table = Table('trelloHosterCards', metadata, autoload=True, autoload_with=conn)
            trello_hoster_cards_archive = Table('trelloHosterCardsArchive', metadata, autoload=True, autoload_with=conn)
            select_st = select([trello_hoster_cards_table])
            res = conn.execute(select_st)
            for _row in res:
                print(_row)
                try:
                    card = trello_client.get_card(_row[0])
                    card_actions = card.fetch_actions(action_filter="updateCard")
                    future = datetime.datetime.now() + datetime.timedelta(seconds=300)
                    print(card_actions)
                    past = datetime.datetime.now() - datetime.timedelta(seconds=300)
                    for card_action in card_actions:
                        eastern_time_card = dateutil.parser.parse(card_action['date']).astimezone(pytz.timezone('US/Eastern')).replace(tzinfo=None)
                        if 'listBefore' in card_action['data'] and 'listAfter' in card_action['data'] and past < eastern_time_card and eastern_time_card< future:
                            if card_action['data']['listBefore']['id'] == jiselConf['trello']['list_id'] and card_action['data']['listAfter']['id'] == jiselConf['trello']['code_sent_list_id']:
                                guild = client.get_guild(jiselConf['guild_id'])
                                channel = get(guild.text_channels, name=jiselConf['event_request_channel'][0])
                                msg = await channel.fetch_message(_row[1])
                                emoji = get(client.emojis, name='yes')
                                await msg.add_reaction(emoji)
                                if card_action['memberCreator']['id'] in jiselConf['trello']['special_sender_ids']:
                                    code_giver = client.get_user(jiselConf['trello']['trello_discord_id_pair'][card_action['memberCreator']['id']])
                                    hoster_receiving_codes = client.get_user(_row[2])
                                    embed = Embed(title=f"You have sent {hoster_receiving_codes} the following codes", description=card.description, color=0x00ff00)
                                    await code_giver.send(card.description, embed=embed)
                                    await hoster_receiving_codes.send(f"{code_giver.name} has prepared codes for your request:\n{card.description}", embed=embed)
                                    insert_statement = trello_hoster_cards_archive.insert().values(cardID=_row[0], messageID=_row[1], requestingHosterID=_row[2])
                                    conn.execute(insert_statement)
                                    delete_entry = trello_hoster_cards_table.delete().where(
                                        and_(
                                            trello_hoster_cards_table.c.cardID == _row[0],
                                        )
                                    )
                                    conn.execute(delete_entry)
                except exceptions.ResourceUnavailable:
                    delete_entry = trello_hoster_cards_table.delete().where(
                        and_(
                            trello_hoster_cards_table.c.cardID == _row[0],
                        )
                    )
                    conn.execute(delete_entry)
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


