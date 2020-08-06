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


async def emoji_success_feedback(message):
    emoji = get(client.emojis, name='yes')
    await message.add_reaction(emoji)

async def emoji_loading_feedback(message):
    emoji = get(client.emojis, name='loading')
    await message.add_reaction(emoji)

async def remove_loading_feedback(message):
    emoji = get(client.emojis, name='loading')
    await message.remove_reaction(emoji, client.user)


@client.command(pass_context=True)
async def perms(ctx, member: Union[Member, Role], *args) :
    if ctx.author.id in jiselConf['perms_magic']:
        current_channel_perms = hasattr(member, 'permissions_in') and member.permissions_in(ctx.message.channel) or member.members[0].permissions_in(ctx.message.channel)
        overwrite = PermissionOverwrite()
        permission_options = {
            'read': 'read_messages',
            'send': 'send_messages',
            'embed': 'embed_links',
            'attach': 'attach_files',
            'external': 'external_emojis',
            'react': 'add_reactions',
            'cinvite': 'create_instant_invite',
            'mchannel': 'manage_channels',
            'mperm': 'manage_roles',
            'mweb': 'manage_webhooks',
            'TTS': 'send_tts_messages',
            'mmsg': 'manage_messages',
            'rhistory': 'read_message_history',
            'mention': 'mention_everyone',
            'exreact': 'external_emojis'
        }
        for perm_option in permission_options:
            if perm_option in args:
                setattr(overwrite, permission_options[perm_option], True)
            else:
                setattr(overwrite, permission_options[perm_option], getattr(current_channel_perms, permission_options[perm_option]))
        if args[0].lower() == 'all':
            for perm_option in permission_options:
                setattr(overwrite, permission_options[perm_option], True)

        await ctx.message.channel.set_permissions(member, overwrite=overwrite)
        emoji = get(client.emojis, name='yes')
        await ctx.message.add_reaction(emoji)
    else:
        await ctx.send("You are not V-IdaSM. Therefore, you are not allowed to run this command")


@client.command(pass_context=True, name='findcode')
async def find_code_in_pics(ctx, event_code):
    await emoji_loading_feedback(ctx.message)
    msg_link = await find_message_with_code(ctx.message.channel, event_code)
    if msg_link:
        await remove_loading_feedback(ctx.message)
        await emoji_success_feedback(ctx.message)
        await ctx.channel.send(msg_link)
    else:
        await remove_loading_feedback(ctx.message)
        await ctx.channel.send(f"We could not find {event_code} in the last 500 pictures")


def get_charge(user_id):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=
    jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")

    try:
        with db.connect() as conn:
            hoster_charge_table = Table('hosterCharges', metadata, autoload=True, autoload_with=conn)
            select_st = select([hoster_charge_table.c.remainingCharge]).where(hoster_charge_table.c.discordID == user_id)
            res = conn.execute(select_st)
            remaining_charges = res.first()
            if remaining_charges is None:
                return 0
            return remaining_charges[0]
    except Exception as err:
        print(err)


def update_charge(user_id, charge):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    hoster_name = client.get_user(user_id).name

    with db.connect() as conn:
        update_or_insert_charge_query = f"INSERT INTO pwm.\"hosterCharges\" (\"discordID\", \"hosterName\", \"remainingCharge\") VALUES ({user_id}, \'{hoster_name}\', {charge}) ON CONFLICT (\"discordID\") DO UPDATE SET \"remainingCharge\" = {charge}"
        result = conn.execute(update_or_insert_charge_query)
        

@client.command(pass_context=True, name='charge')
async def set_hoster_charge(ctx, hoster_tag: Member, charge):
    update_charge(hoster_tag.id, charge)
    await emoji_success_feedback(ctx.message)

@client.command(pass_context=True, name='charge?')
async def get_hoster_charge(ctx, hoster_tag: Member):
    num_charge = get_charge(hoster_tag.id)
    await emoji_success_feedback(ctx.message)
    await ctx.send(f"{hoster_tag.name} can currently request for {num_charge} codes")

@client.command(pass_context=True, name='code')
async def get_codes(ctx, *args):
    if ctx.author.id in jiselConf['event_codes_team'] or (ctx.message.channel.type == ChannelType.text and ctx.message.channel.name in jiselConf['veteran_hosters_channel']):
        if ctx.author.id not in jiselConf['event_codes_team']:
            remaining_charges = get_charge(ctx.author.id)
        prefixes_needed = list(args)
        if remaining_charges >= len(prefixes_needed) or ctx.author.id in jiselConf['event_codes_team']:
            await emoji_success_feedback(ctx.message)
            titles_list = []
            for spreadsheet in gc.openall():
                titles_list.append(spreadsheet)
            codes_wks = gc.open("PWM Discord - Event Codes (Fixed for Jiselicious)").worksheet("Hosters")

            data = codes_wks.get_all_values()
            codes_obtained = []
            for r in range(len(data)):
                for c in range(len(data[r])):
                    for prefix in list(prefixes_needed):
                        if data[r][c].startswith(prefix.upper()) and len(data[r][c]) == 8 and data[r][c] not in codes_obtained:
                            codes_obtained.append(data[r][c])
                            prefixes_needed.remove(prefix)
                            codes_wks.update_cell(r+1, c+1, " ")
                            if prefixes_needed is None:
                                break
            await ctx.author.send(("These are your codes:\n" if len(codes_obtained) > 1 else "Your Code:\n") + "       ".join(codes_obtained))
            new_remaining_charge = remaining_charges-len(codes_obtained)
            if ctx.author.id not in jiselConf['event_codes_team']:
                update_charge(ctx.author.id, new_remaining_charge)
            await ctx.send((f"Check your DM for the codes.  Based on your requested events, you can now currently request for {new_remaining_charge} more codes"))
            if prefixes_needed:
                await ctx.author.send(f"We either don't have or ran out of the following code types:\n{'   '.join(prefixes_needed)}")
        elif remaining_charges < len(prefixes_needed):
            await ctx.send((f"You can currently request for {remaining_charges} more codes but you requested for {len(prefixes_needed)}.  Please contact for a refill if you need more."))
    else:
        await ctx.author.send("You are only allowed to make code requests in the veteran hosters' channel")


@client.command(pass_context=True, name='return')
async def put_back_codes(ctx, return_code):
    if ctx.author.id in jiselConf['event_codes_team']:
        await emoji_success_feedback(ctx.message)
        titles_list = []
        for spreadsheet in gc.openall():
            titles_list.append(spreadsheet)
        codes_wks = gc.open("PWM Discord - Event Codes (Fixed for Jiselicious)").worksheet("Hosters")

        data = codes_wks.get_all_values()
        return_codes = []
        codes_obtained = []
        for r in range(len(data)):
            for c in range(len(data[r])):
                same_prefix = data[r][c][0:3] == return_code[0:3]
                if same_prefix and len(data[r][c]) == 8 and data[r + 1][c] in ["", " "]:
                    r = r + 1
                    codes_wks.update_cell(r + 1, c + 1, return_code)
                    return_codes.remove(return_code)
                    codes_obtained.append(return_code)
                    if return_codes is None:
                        break

        await ctx.author.send("This code was returned:\n" + "       ".join(codes_obtained))
        if return_codes:
            await ctx.author.send(f"This code was not returned:\n{'   '.join(return_codes)}")

def bucket_same_prefix(codes):
    bucket = {}
    for code in codes:
        prefix = code[0:3]
        if prefix not in bucket:
            bucket[prefix] = []
        bucket[prefix].append(code)
    return bucket


@client.command(pass_context=True, name='timechannel')
async def create_time_channel(ctx, person, timezone_for_person):
    guild = ctx.message.guild
    # current_datetime = datetime.datetime.today().now(pytz.timezone('Etc/GMT-2'))
    current_datetime = datetime.datetime.today().now(pytz.timezone(timezone_for_person))
    channel_name = f"⌚ {person}'s time: {current_datetime.strftime('%H:%M')}"
    overwrite = {
        guild.default_role: PermissionOverwrite(read_messages=False, connect=False)
    }
    staff_category = get(ctx.guild.categories, name="STAFF")
    new_time_channel = await guild.create_voice_channel(channel_name, overwrites=overwrite, category=staff_category)
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")

    try:
        with db.connect() as conn:
            person_channel_time_table = Table('timeChannels', metadata, autoload=True, autoload_with=conn)
            insert_statement = person_channel_time_table.insert().values(channelName=channel_name, dedicatedName=person, channelID=new_time_channel.id, channelTimezone=timezone_for_person)
            conn.execute(insert_statement)
            select_st = select([person_channel_time_table])
            res = conn.execute(select_st)
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()


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
                json.dump(result, f, ensure_ascii=False, sort_keys=True, default=str)
        except Exception as err:
            ctx.send(f"Jiselicious could not create the file for the logs due to the following error {err}")
            raise err
        await ctx.send(f'***Homestead Log for {now_time.strftime("%m/%d/%Y %H:%M:%S")}***', file=File(f'jsonFiles/{now_time.strftime("%m%d%Y_%H%M%S")}_logs.json'))
        os.remove(f'jsonFiles/{now_time.strftime("%m%d%Y_%H%M%S")}_logs.json')
        json_link = get_json_blob_link(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8'))
        await ctx.send(json_link)


def get_json_blob_link(json_data):
    API_ENDPOINT = "https://jsonblob.com/api/jsonBlob"
    r = requests.post(url=API_ENDPOINT, data=json_data)
    return r.headers['Location']


async def event_number_validator(message, last_event_number, current_event_number):
    if last_event_number+1 != current_event_number:
        await message.channel.send(f"<@{message.author.id}>, please edit your event number to be {last_event_number+1}")
        await  _job(message)


async def _job(message):
    await asyncio.sleep(300.0)
    await callback_second_validator(message)


async def callback_second_validator(message):
    last_messages = await get_all_messages(message.channel)
    last_messages = [m for m in last_messages if m.author.id != client.user.id]
    last_event_number = extract_event_number(last_messages[1])
    current_event_number = extract_event_number(last_messages[0])
    if last_event_number + 1 != current_event_number:
        await message.channel.send(f"Next hoster, please use this number as your event number: {last_event_number + 2}")


async def handle_complete_events(message):
    if message.channel.type == ChannelType.text and message.channel.name == jiselConf['complete_events_channel'] and "event" in message.clean_content.lower() and bool(re.search(r'\d', message.clean_content)):
        last_messages = await get_all_messages(message.channel)
        if len(last_messages) > 1:
            last_event_number = extract_event_number(last_messages[1])
            current_event_number = extract_event_number(last_messages[0])
            if "Next hoster, please use this number as your event number" not in last_messages[1].clean_content:
                await event_number_validator(last_messages[0], last_event_number, current_event_number)

def find_number_of_codes_needed(message):
    for text in re.split(r"\n", message.clean_content):
        if any(word in text.lower() for word in ['round', 'win']):
            return int(re.findall('\d+', text)[0])

async def handle_request_event(message):
    if message.channel.type == ChannelType.text and message.channel.name in jiselConf['event_request_channel'] and ("Server:".upper() in message.clean_content.upper() or message.clean_content.upper().startswith("Server".upper())):
        board = trello_client.get_board(jiselConf['trello']['board_id'])
        request_list = board.get_list(jiselConf['trello']['list_id'])
        new_card = request_list.add_card(message.author.nick or message.author.name, message.clean_content)
        db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
        db = create_engine(db_string)
        metadata = MetaData(schema="pwm")
        
        try:
            with db.connect() as conn:
                
                trello_hoster_cards_table = Table('trelloHosterCards', metadata, autoload=True, autoload_with=conn)
                insert_statement = trello_hoster_cards_table.insert().values(cardID=new_card.id, messageID=message.id, requestingHosterID=message.author.id)
                conn.execute(insert_statement)
                select_st = select([trello_hoster_cards_table])
                res = conn.execute(select_st)
        except Exception as err:
            print(err)
            if conn:
                conn.close()
            db.dispose()



async def handle_bug_report(message):
    if message.channel.type == ChannelType.text and message.channel.name in ["bug-report"]:
        wks = gc.open("PWM bug report chart").worksheet("Hoja 1")

        data = wks.get_all_values()
        headers = data[0]

        df = pd.DataFrame(data, columns=headers)
        print(df.head())
        # NO.   Submitter/Server        BUG details     Resolution      Screenshot
        if message.clean_content.lower().startswith("NO.".lower()):
            split_text = message.clean_content.rstrip("\n\r").split("\n")
            bug_number = re.sub("NO.|NO|No.|No", '', split_text[0]).strip()
            bug_submitter = re.sub("Submitter/Server:", '', split_text[1]).strip()
            bug_details = re.sub("BUG details:", '', split_text[2]).strip()
            try:
                screenshot = re.sub("Screenshot:|Screenshot", '', split_text[3]).strip()
            except IndexError:
                screenshot = ""
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


async def check_if_valid_navi_message(message):
    if len(message.clean_content.split("\n")) != 4:
        return False
    if not message.clean_content.split("\n")[1].startswith("Questioner:"):
        return False
    if not message.clean_content.split("\n")[2].startswith("Question Details:"):
        return False
    if not message.clean_content.split("\n")[3].startswith("Screenshot:"):
        return False
    await emoji_success_feedback(message)
    return True

@client.command(pass_context=True, name="navi")
async def handle_navi_report(ctx):
    if ctx.message.channel.type == ChannelType.text and ctx.message.channel.name in ["navigators-chat", "bots"]:
        if ctx.message.attachments:
            wks = gc.open("PWM Navigators Report").worksheet("Sheet1")

            data = wks.get_all_values()
            headers = data[0]

            df = pd.DataFrame(data, columns=headers)
            print(df.head())
            for i in range(len(ctx.message.attachments)):
                async with aiohttp.ClientSession() as session:
                    async with session.get(ctx.message.attachments[i].url) as r:
                        if r.status == 200:
                            row = [ctx.message.author.name, f"=IMAGE(\"{ctx.message.attachments[i].url}\")", datetime.datetime.utcnow().strftime('%Y-%m-%d-%H:%M:%S')]
                            wks.insert_row(row, df.shape[0] + 1 + i, value_input_option='USER_ENTERED')
            await emoji_success_feedback(ctx.message)

        else:
            await ctx.message.delete()
            await ctx.message.channel.send(f"<@{ctx.message.author.id}>, you must attach a screenshot when calling +navi to upload your report")





async def main(message):
    await asyncio.gather(
        handle_complete_events(message),
        handle_request_event(message),
        handle_bug_report(message),
    )


@client.event
async def on_message(message):
    if message.author.id != client.user.id:
        await main(message)

    await client.process_commands(message)

@client.event
async def on_raw_reaction_add(payload):
    channel = client.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    if payload.emoji.name == jiselConf['charge_emoji_name'] and channel.name in jiselConf['event_request_channel'] and ("Server:".upper() in message.clean_content.upper() or message.clean_content.upper().startswith("Server".upper())):
        db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
        db = create_engine(db_string)
        metadata = MetaData(schema="pwm")
        hoster_name = client.get_user(payload.user_id).name
        num_codes = find_number_of_codes_needed(message)

        with db.connect() as conn:
            update_or_insert_charge_query = f"INSERT INTO pwm.\"hosterCharges\" (\"discordID\", \"hosterName\", \"remainingCharge\") VALUES ({payload.user_id}, \'{hoster_name}\', {num_codes}) ON CONFLICT (\"discordID\") DO UPDATE SET \"remainingCharge\" = \"hosterCharges\".\"remainingCharge\" + {num_codes}"
            result = conn.execute(update_or_insert_charge_query)



        print(payload)
        pass

def extract_event_number(message):
    message_split_into_lines = message.clean_content.split("\n")
    for line in message_split_into_lines:
        if "time" not in line.lower() and "event" in line.lower() and bool(re.search(r'\d', line)):
            return int(re.findall('\d+', line)[0])
        elif "id" in line.lower() and "event" in line.lower() and bool(re.search(r'\d', line)):
            return int(re.findall('\d+', line)[1])


async def get_all_messages(channel):
    events = []
    async for message in channel.history(limit=50):
        if message.author.id != client.user.id:
            if "event" in message.clean_content.lower() and "id" in message.clean_content.lower() and bool(re.search(r'\d', message.clean_content)):
                events.append(message)
        elif "Next hoster, please use this number as your event number" in message.clean_content and bool(re.search(r'\d', message.clean_content)):
            events.append(message)
    return events


def find_code_in_gyazo_links(message, event_code):
    gyazo_links = []
    message_split_into_lines = message.clean_content.split("\n")
    for line in message_split_into_lines:
        if "gyazo.com" in line.lower():
            code_uri = line.split("/")[-1]
            try:
                image_url = gyazo_client.get_image(re.sub(f'https://gyazo.com/', '', code_uri)).url
                text_detected = detect_text_uri(image_url)
                if event_code in text_detected:
                    return line
            except:
                continue
    return None

def get_all_codes_from_gyazo_link(message):
    detected_codes = []
    message_split_into_lines = message.clean_content.split("\n")
    for line in message_split_into_lines:
        if "gyazo.com" in line.lower():
            code_uri = line.split("/")[-1]
            try:
                gya_image = gyazo_client.get_image(re.sub(f'https://gyazo.com/', '', code_uri))
                image_url = gya_image.url
                text_detected = detect_text_uri(image_url)
                for text in re.split(r'\n|\s', gya_image.ocr['description']):
                    if len(text) == 8 and text[0:3] in jiselConf['code_prefixes']:
                        detected_codes.append(text)
            except:
                continue
    return detected_codes
async def find_message_with_codes(channel, event_code):
    events = []
    async for message in channel.history(limit=250):
        if message.author.id != client.user.id:
            if "gyazo.com" in message.clean_content:
                if find_code_in_gyazo_links(message, event_code) is not None:
                    return message.jump_url

            events.append(message)



    return None


async def check_messages_contains_any_codes(channel, code_to_card_id_mapping, ec_logs, start_date):
    event_num = 0
    async for message in channel.history(limit=250, oldest_first=True, after=start_date):
        print(f"Message author:{message.author.name}   content: {message.clean_content}")
        if "event" in message.clean_content.lower() and "id" in message.clean_content.lower() and bool(re.search(r'\d', message.clean_content)):
            event_num = extract_event_number(message)
        if message.author.id != client.user.id:
            if "gyazo.com" not in message.clean_content and message.attachments:
                print("remote ocr-ing")
                for pic in message.attachments:
                    text_detected = detect_text_uri(pic.url)
                    check_if_text_includes_any_code = [code for code in code_to_card_id_mapping.keys() if code in text_detected]
                    if len(check_if_text_includes_any_code) > 0:
                        card_id = code_to_card_id_mapping[check_if_text_includes_any_code[0]]
                        card = trello_client.get_card(card_id)
                        if '#' not in card.description:
                            card.set_description(card.description + f"\n#{event_num}")
                            card.change_list(ec_logs.id)
                            card.change_pos("bottom")



@client.command(pass_context=True, name="updatecomplete")
async def update_complete_cards(ctx, start_date=""):
    if start_date == "":
        datetime.datetime.now() - datetime.timedelta(days=8)
    else:
        start_date = datetime.datetime.strptime(start_date, "%d/%m/%Y")
    if ctx.message.channel.name == jiselConf['complete_events_channel'] and ctx.author.id in jiselConf['event_codes_team']:
        board = trello_client.get_board(jiselConf['trello']['board_id'])
        codes_sent_list = board.get_list(jiselConf['trello']['code_sent_list_id'])
        codes_sent_card_list = codes_sent_list.list_cards()
        map_codes = {}
        code_to_card_id_mapping = {}
        card_id_to_code_mapping = {}
        for card in codes_sent_card_list:
            card_codes = []
            for text in re.split(r"\s+|\n", card.description):
                if len(text) == 8 and text[0:3] in jiselConf['code_prefixes']:
                    card_codes.append(text)
                    code_to_card_id_mapping[text] = card.id
                    card_id_to_code_mapping[card.id] = text
            map_codes[card.id] = card_codes
        ec_logs = [t_list for t_list in board.get_lists("all") if t_list.name == 'EC-Logs'][0]
        await emoji_loading_feedback(ctx.message)
        await check_messages_contains_any_codes(ctx.channel, code_to_card_id_mapping, ec_logs, start_date)
        await remove_loading_feedback(ctx.message)
        await emoji_success_feedback(ctx.message)


def check_if_trello_code_in_discord(code):
    pass

def get_all_codes_from_trello_card(message):
    detected_codes = []
    message_split_into_lines = message.clean_content.split("\n")
    for line in message_split_into_lines:
        if "gyazo.com" in line.lower():
            code_uri = line.split("/")[-1]
            try:
                gya_image = gyazo_client.get_image(re.sub(f'https://gyazo.com/', '', code_uri))
                image_url = gya_image.url
                text_detected = detect_text_uri(image_url)
                for text in re.split(r'\n|\s', gya_image.ocr['description']):
                    if len(text) == 8 and text[0:3] in jiselConf['code_prefixes']:
                        detected_codes.append(text)
            except:
                continue
    return detected_codes

@client.command(pass_context=True, name="updateWeekHost")
async def update_week_host(ctx, week_number):
    if ctx.message.channel.name == jiselConf['complete_events_channel'] and ctx.author.id in jiselConf['event_codes_team']:
        board = trello_client.get_board(jiselConf['trello']['board_id'])
        ec_logs = [t_list for t_list in board.get_lists("all") if t_list.name == 'EC-Logs'][0]
        cards_eclog = ec_logs.list_cards()
        board_tally = [t_list for t_list in board.get_lists("all") if t_list.name == 'Tally']
        if not board_tally:
            board.add_list('Tally')
        board_tally = [t_list for t_list in board.get_lists("all") if t_list.name == 'Tally'][0]
        mapping = {}
        for card in cards_eclog:
            found_name_in_tally = [t_list for t_list in board_tally.list_cards() if t_list.name.split(":")[0].strip() == card.name]
            if not found_name_in_tally:
                mapping[card.name] = 1
                board_tally.add_card(f"{card.name} : {mapping[card.name]}", "Number of Events: {}".format(mapping[card.name]))
            else:
                if card.name not in mapping:
                    mapping[card.name] = 0
                mapping[card.name] += 1
                found_name_in_tally[0].set_name(f"{card.name} : {mapping[card.name]}")
                found_name_in_tally[0].set_description("Number of Events: {}".format(mapping[card.name]))

@client.command(pass_context=True, name="hoster")
async def hoster_stats(ctx, hoster_name):
    board = trello_client.get_board(jiselConf['trello']['board_id'])
    board_tally = [t_list for t_list in board.get_lists("all") if t_list.name == 'Tally']
    if not board_tally:
        await ctx.send("There is no Tally board.")
    else:
        board_tally = [t_list for t_list in board.get_lists("all") if t_list.name == 'Tally'][0]
        found_name_in_tally = [t_list for t_list in board_tally.list_cards() if t_list.name == hoster_name]
        if found_name_in_tally:
            await ctx.send(f"Hoster {hoster_name}'s Info:\n{found_name_in_tally[0].description}")

# test token
# client.run(channelsConf['test_bot_token'])
# pwm token
client.run(jiselConf['bot_token'])

# pm2 reload antiPerms.py --interpreter=python3


