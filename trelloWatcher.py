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
                try:
                    card = trello_client.get_card(_row[0])
                    card_actions = card.fetch_actions(action_filter="updateCard")
                    future = datetime.datetime.now() + datetime.timedelta(seconds=300)
                    past = datetime.datetime.now() - datetime.timedelta(seconds=300)
                    for card_action in card_actions:
                        eastern_time_card = dateutil.parser.parse(card_action['date']).astimezone(pytz.timezone('US/Eastern')).replace(tzinfo=None)
                        if 'listBefore' in card_action['data'] and 'listAfter' in card_action['data'] and past < eastern_time_card and eastern_time_card< future:
                            if card_action['data']['listBefore']['id'] == jiselConf['trello']['list_id'] and card_action['data']['listAfter']['id'] == jiselConf['trello']['code_sent_list_id']:
                                guild = client.get_guild(jiselConf['guild_id'])
                                channel = get(guild.text_channels, name=jiselConf['event_request_channel'][0])
                                print(_row[1])
                                msg = await channel.fetch_message(_row[1])
                                emoji = get(client.emojis, name='yes')
                                await msg.add_reaction(emoji)
                                hoster_receiving_codes = client.get_user(_row[2])
                                guild = client.get_guild(jiselConf['guild_id'])
                                hoster_roles = [u.roles for u in guild.members if u.id == _row[2]][0]
                                hoster_role_names = [role.name for role in hoster_roles]
                                is_veteran_hoster = jiselConf['veteran_hoster_role_name'] in hoster_role_names
                                if card_action['memberCreator']['username'] in jiselConf['trello']['special_sender_usernames'] and not is_veteran_hoster:
                                    card_has_codes = check_if_card_contains_codes(card)
                                    if not card_has_codes:
                                        num_codes_needed = find_number_of_codes_needed(card)
                                        append_random_codes(card, num_codes_needed)

                                    code_giver = client.get_user(jiselConf['trello']['trello_discord_id_pair'][card_action['memberCreator']['username']])
                                    embed = Embed(title=f"You have sent {hoster_receiving_codes} the following codes:", description=card.description, color=0x00ff00)
                                    await code_giver.send(embed=embed)
                                    hoster_embed = Embed(title=f"{code_giver.name} has prepared codes for your request:", description=card.description, color=0x00ff00)
                                    await hoster_receiving_codes.send(embed=hoster_embed)
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

            try:
                now = datetime.datetime.now()
                if now.minute % 15 == 0:
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
                            channel = get(guild.voice_channels, id=int(_row[2]))
                            await channel.edit(name=f"⌚ {_row[1]}'s time: {now_time}")
            except Exception as err:
                print(err)

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


