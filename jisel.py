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
from discord import File, Member, Role, PermissionOverwrite, ChannelType, Embed
import requests
import time
import asyncio
import threading
from typing import Union
from remoteGoogImage import detect_text_uri
import pytz
import math
import random
import redis

client = commands.Bot(command_prefix='+')

redis_client = redis.Redis(host='localhost', port=6379, db=0)

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

@client.event
async def on_member_update(before, after):
    if before.id == 424958829596246027:
        n = after.nick
        if n:
            if n.lower().count("navi") or n.lower().count("mod"):
                last = before.nick
                if last:
                    await after.edit(nick="Death")

@client.command(pass_context=True)
async def perms(ctx, member: Union[Member, Role], *args) :
    guild = client.get_guild(ctx.guild.id)
    if ctx.author.id in jiselConf['perms_magic']:
        if args[0].isdigit():
            given_channel = client.get_channel(int(args[0]))
        else:
            given_channel = ctx.message.channel

        current_channel_perms = hasattr(member, 'permissions_in') and member.permissions_in(given_channel) or member.members[0].permissions_in(given_channel)
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

        await given_channel.set_permissions(member, overwrite=overwrite)
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
    num_charge = get_charge(hoster_tag.id)
    if (num_charge <= 5 and charge <= 5) or ctx.author.id in jiselConf['event_codes_team']:
        update_charge(hoster_tag.id, charge)
        await emoji_success_feedback(ctx.message)
    else:
        if charge > 5 or num_charge > 5:
            ctx.author.send(f"You can currently request {num_charge} codes.  Please call an Event Manager or an assistant to charge more than 5 code requests")

@client.command(pass_context=True, name='chargeall')
async def charge_all_veteran_hosters(ctx, charge):
    veteran_members = get(ctx.guild.roles, name="Veteran Hoster").members
    for member in veteran_members:
        update_charge(member.id, charge)

@client.command(pass_context=True, name='charge?')
async def get_hoster_charge(ctx, hoster_tag: Member):
    num_charge = get_charge(hoster_tag.id)
    await emoji_success_feedback(ctx.message)
    await ctx.send(f"{hoster_tag.name} can currently request for {num_charge} codes")


@client.command(pass_context=True, name='code')
async def get_codes(ctx, *args):
    if ctx.author.id in jiselConf['event_codes_team'] or (ctx.message.channel.type == ChannelType.text and ctx.message.channel.name in jiselConf['veteran_hosters_channel']):
        remaining_charges =0
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
async def create_time_channel(ctx, timezone_for_person, *args):
    person = ' '.join(args)
    guild = ctx.message.guild
    # current_datetime = datetime.datetime.today().now(pytz.timezone('Etc/GMT-2'))
    current_datetime = datetime.datetime.today().now(pytz.timezone(timezone_for_person))
    channel_name = f"⌚ {person}: {current_datetime.strftime('%H:%M')}"
    overwrite = {
        guild.default_role: PermissionOverwrite(read_messages=False, connect=False)
    }
    staff_category = get(ctx.guild.categories, name="STAFF")
    new_time_channel = await guild.create_voice_channel(channel_name, overwrites=overwrite, category=staff_category or ctx.channel.category)
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")

    try:
        with db.connect() as conn:
            person_channel_time_table = Table('timeChannels', metadata, autoload=True, autoload_with=conn)
            insert_statement = person_channel_time_table.insert().values(channelName=channel_name, dedicatedName=person, channelID=new_time_channel.id, channelTimezone=timezone_for_person, guild_id=guild.id)
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
        if message.guild.id == jiselConf['snk_guild_id']:
            wks = gc.open("SNK bug report chart").worksheet("Sheet1")
        else:
            wks = gc.open("PWM bug report chart").worksheet("Hoja 1")

        data = wks.get_all_values()
        headers = data[0]

        df = pd.DataFrame(data, columns=headers)
        print(df.head())
        # NO.   Submitter/Server        BUG details     Resolution      Screenshot
        is_open = redis_client.get(f'{message.author.id}_bug_session_open')
        if is_open:
            await handle_open_bug_report(message)

        else:
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

async def handle_open_bug_report(message):
    bug_id_sent = redis_client.get(f"{message.author.id}_bug_id_sent")
    bug_submitter_and_server_sent = redis_client.get(f"{message.author.id}_bug_submitter_and_server_sent")
    bug_details_sent = redis_client.get(f"{message.author.id}_bug_details_sent")
    bug_screenshot_sent = redis_client.get(f"{message.author.id}_bug_screenshot_sent")
    bug_done_screenshots = redis_client.get(f"{message.author.id}_bug_done_screenshots")
    bug_report_ready_to_preview = redis_client.get(f"{message.author.id}_bug_report_ready_to_preview")
    questionnaire_embed = None
    bug_report_preview_id = redis_client.get(f'{message.author.id}_bug_report_preview_id')
    bug_report_preview_msg = await message.channel.fetch_message(int(bug_report_preview_id))
    preview_embed = bug_report_preview_msg.embeds[0]
    previous_question_id = redis_client.get(f'{message.author.id}_bug_report_previous_question_id')
    previous_question = await message.channel.fetch_message(int(previous_question_id))
    async def handle_screenshots():
        bug_screenshot_sent = redis_client.get(f"{message.author.id}_bug_screenshot_sent")
        if not bug_screenshot_sent:
            atchments = []
            for _a in message.attachments:
                atchments.append(_a.url)
            redis_client.set(f"{message.author.id}_bug_screenshot_sent", message.content + ',' + ",".join(atchments))
        else:
            atchments = []
            for _a in message.attachments:
                atchments.append(_a.url)
            redis_client.set(f"{message.author.id}_bug_screenshot_sent", message.content + ',' + bug_screenshot_sent.decode("utf-8") + "," + ",".join(atchments))
        bug_screenshot_sent = redis_client.get(f"{message.author.id}_bug_screenshot_sent").decode("utf-8").split(',')
        preview_embed.set_field_at(3, name="Bug Screenshot(s) or Videos", value="\n".join(bug_screenshot_sent) or "None provided")
        await bug_report_preview_msg.edit(embed=preview_embed)

    if message.content.lower() == 'cancel':
        await bug_report_preview_msg.delete()
        await previous_question.delete()
        for key in redis_client.scan_iter(f'{message.author.id}_bug_*'):
            redis_client.delete(key)
    elif not bug_id_sent:
        redis_client.set(f"{message.author.id}_bug_id_sent", message.clean_content)
        preview_embed.set_field_at(0, name="Bug ID", value=message.clean_content)
        await bug_report_preview_msg.edit(embed=preview_embed)
        questionnaire_embed = Embed(title="Who is the submitter and in what server was this bug found?", color=jiselConf['info_color'])
    elif not bug_submitter_and_server_sent:
        redis_client.set(f"{message.author.id}_bug_submitter_and_server_sent", message.clean_content)
        preview_embed.set_field_at(1, name="Bug Submitter/Server", value=message.clean_content)
        await bug_report_preview_msg.edit(embed=preview_embed)
        questionnaire_embed = Embed(title="Please provide concise details for this bug", color=jiselConf['info_color'])
    elif not bug_details_sent:
        redis_client.set(f"{message.author.id}_bug_details_sent", message.clean_content)
        preview_embed.set_field_at(2, name="Bug Details", value=message.clean_content)
        await bug_report_preview_msg.edit(embed=preview_embed)
        questionnaire_embed = Embed(title="Please provide screenshots of your bug.  A Link to a video would be ideal", color=jiselConf['info_color'])
    elif not bug_done_screenshots:
        await handle_screenshots()
        questionnaire_embed = Embed(title="Are you done posting attachments? If not, keep attaching all the screenshots you need. If you're ready, just tap on the <:Yes:771864479461539840>", color=jiselConf['info_color'])
        questionnaire_embed.add_field(name="<:Yes:771864479461539840>", value="I'm ready to send my report")
        questionnaire_embed.add_field(name="<:No:771864718939652144>", value="I'm not ready. I'm going to make more attachments")

    if message.attachments and not bug_details_sent:
        await handle_screenshots()

    if questionnaire_embed:
        questionnaire_embed.set_footer(text='You can type "cancel" at any time to exit this bug report session. Your incomplete bug report will not be recorded')
        questionnaire_message = await message.channel.send(embed=questionnaire_embed)
        await previous_question.delete()
        if not message.attachments and not message.embeds:
            await message.delete()
        redis_client.set(f'{message.author.id}_bug_report_previous_question_id', questionnaire_message.id)
        if bug_details_sent:
            await questionnaire_message.add_reaction(':Yes:771864479461539840')
            await questionnaire_message.add_reaction(':No:771864718939652144')


@client.command(pass_context=True, name='report')
async def start_report_questionaire(ctx):
    if ctx.message.channel.type == ChannelType.text and ctx.message.channel.name in ["bug-report"]:
        if ctx.message.guild.id == jiselConf['snk_guild_id']:
            wks = gc.open("SNK bug report chart").worksheet("Sheet1")
        else:
            wks = gc.open("PWM bug report chart").worksheet("Hoja 1")

        data = wks.get_all_values()
        headers = data[0]

        df = pd.DataFrame(data, columns=headers)
        print(df.head())
        # NO.   Submitter/Server        BUG details     Resolution      Screenshot
        embed = Embed(title="Bug Report - Not Yet Recorded", description="This is a preview of your current bug report.  It has not yet been recorded.", color=jiselConf['info_color'])
        embed.add_field(name="Bug ID", value="<:No:771864718939652144>")
        embed.add_field(name="Bug Submitter/Server", value="<:No:771864718939652144>")
        embed.add_field(name="Bug Details", value="<:No:771864718939652144>")
        embed.add_field(name="Bug Screenshot", value="<:No:771864718939652144>")
        bug_report_preview_msg = await ctx.message.channel.send(embed=embed)
        redis_client.set(f'{ctx.author.id}_bug_session_open', 1)
        redis_client.set(f'{ctx.author.id}_bug_report_preview_id', bug_report_preview_msg.id)
        questionnaire_embed = Embed(title="What is the ID number of this current bug you are reporting?", color=jiselConf['info_color'])
        questionnaire_embed.set_footer(text='You can type "cancel" at any time to exit this bug report session. Your incomplete bug report will not be recorded')
        questionnaire_msg = await ctx.message.channel.send(embed=questionnaire_embed)
        redis_client.set(f'{ctx.author.id}_bug_report_previous_question_id', questionnaire_msg.id)



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
        handle_trivia_message(message)
    )

async def handle_trivia_message(message):
    if message.channel.name == jiselConf['trivia_channel']:
        print('realized that this is the trivia channel------------')
        current_trivia_question_obj = get_current_trivia_question_id()
        if current_trivia_question_obj:
            private_bot_feedback_channel = get(message.guild.text_channels, name=jiselConf['bot_feed_back_channel']['name'])
            current_trivia_question_id = current_trivia_question_obj['question_id']
            print(' what is 30 seconds plus---------', current_trivia_question_obj['time_asked'])
            now = datetime.datetime.now()
            time_expire = current_trivia_question_obj['time_asked'] + datetime.timedelta(seconds=jiselConf['expiration_seconds'])
            print(time_expire)
            print(now)
            if now <= time_expire:
                print('does it think that it did not expire---------')
                answers = get_table_answers(current_trivia_question_id, None)
                lower_case_answers = [answer_row['answer'].lower() for answer_row in answers]
                if message.clean_content.lower() in lower_case_answers:
                    embed = Embed(title="That's correct!", description=f"<:PWM_yes:770642224249045032> Congratulations, <@!{message.author.id}>. You've gained 10 points!", color=4437377)
                    await message.channel.send(embed=embed)
                    result_remove_curr_question = remove_current_trivia()
                    if result_remove_curr_question:
                        embed = Embed(title="Current Question for this hour has been cleared", description=f"Winner was  <@!{message.author.id}>.", color=jiselConf['info_color'])
                        await private_bot_feedback_channel.send(embed=embed)
                        top_ten = upsert_to_trivia_leader_board(message.author.id, message.author.name, 10)
                        embed = Embed(title="Current Top 10", description="In Descending Order", color=jiselConf['info_color'])
                        tag_names = [f"<@!{_row['id']}>" for _row in top_ten]
                        scores = [str(_row['score']) for _row in top_ten]
                        embed.add_field(name="Seeker", value="\n".join(tag_names), inline=True)
                        embed.add_field(name="Score", value="\n".join(scores), inline=True)
                        await private_bot_feedback_channel.send(embed=embed)
            else:
                print('Does it even acknowlege that time has expired-------------')
                private_embed = embed = Embed(title="Current Question for this hour has already expired", description=f"<@!{message.author.id}> tried to answer an expired question.", color=16426522)
                embed = Embed(title="Current Question for this hour has already expired", description=f"There was no winner. Try again next time!", color=16426522)
                result_remove_curr_question = remove_current_trivia()
                if result_remove_curr_question:
                    await message.channel.send(embed=embed)
                    await private_bot_feedback_channel.send(embed=private_embed)


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
            return participants
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

@client.command(pass_context=True, name="trivialeaderboard")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def get_leaderboard(ctx):
    participants = get_trivia_leader_board()
    embed = Embed(title="Current Top 10", description="In Descending Order", color=jiselConf['info_color'])
    if participants:
        tag_names = [f"<@!{_row['id']}>" for _row in participants]
        scores = [str(_row['score']) for _row in participants]
        embed.add_field(name="Seeker", value="\n".join(tag_names), inline=True)
        embed.add_field(name="Score", value="\n".join(scores), inline=True)
        await ctx.message.channel.send(embed=embed)

@client.command(pass_context=True, name="alltime")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def get_leaderboard(ctx):
    participants = get_all_time()
    embed = Embed(title="Current Top 10", description="In Descending Order", color=jiselConf['info_color'])
    if participants:
        tag_names = [f"<@!{_row['id']}>" for _row in participants]
        scores = [str(_row['score']) for _row in participants]
        embed.add_field(name="Seeker", value="\n".join(tag_names), inline=True)
        embed.add_field(name="Score", value="\n".join(scores), inline=True)
        await ctx.message.channel.send(embed=embed)

def get_all_time():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            participants = []
            leaderboard_table = Table('allTimeTriviaLeaderboard', metadata, autoload=True, autoload_with=conn)
            select_st = select([leaderboard_table]).order_by(leaderboard_table.c.score.desc(), leaderboard_table.c.lastUpdated)
            res = conn.execute(select_st)
            for _row in res:
                participants.append({
                    'id': _row[0],
                    'name': _row[1],
                    'score': _row[2]
                })
            return participants
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

def upsert_to_trivia_leader_board(discord_id, discord_name, score):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            participants = []
            leaderboard_table = Table('triviaLeaderboard', metadata, autoload=True, autoload_with=conn)
            all_time = Table('allTimeTriviaLeaderboard', metadata, autoload=True, autoload_with=conn)
            update_or_insert_charge_query = f"INSERT INTO pwm.\"triviaLeaderboard\" (\"discord_id\", \"discord_name\", \"score\") VALUES ({discord_id}, \'{discord_name}\', {score}) ON CONFLICT (\"discord_id\") DO UPDATE SET \"score\" = \"triviaLeaderboard\".\"score\" + {score}, \"lastUpdated\" = CURRENT_TIMESTAMP"
            all_time_upsert_query = f"INSERT INTO pwm.\"allTimeTriviaLeaderboard\" (\"discord_id\", \"discord_name\", \"score\") VALUES ({discord_id}, \'{discord_name}\', {score}) ON CONFLICT (\"discord_id\") DO UPDATE SET \"score\" = \"allTimeTriviaLeaderboard\".\"score\" + {score}, \"lastUpdated\" = CURRENT_TIMESTAMP"
            all_time_result = conn.execute(all_time_upsert_query)
            result = conn.execute(update_or_insert_charge_query)
            select_st = select([leaderboard_table]).order_by(leaderboard_table.c.score.desc(), leaderboard_table.c.lastUpdated)
            res = conn.execute(select_st)
            for _row in res:
                participants.append({
                    'id': _row[0],
                    'name': _row[1],
                    'score': _row[2]
                })
            return participants[0:10]
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
            delete_query = "DELETE FROM pwm.\"currentQuestion\""
            res = conn.execute(delete_query)
            return True
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

@client.command(pass_context=True, name="cleartrivialeaderboard")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def clear_leaderboard(ctx):
    participants = get_trivia_leader_board()
    embed = Embed(title="Current Top 10", description="In Descending Order", color=jiselConf['info_color'])
    if participants:
        tag_names = [f"<@!{_row['id']}>" for _row in participants]
        scores = [str(_row['score']) for _row in participants]
        embed.add_field(name="Seeker", value="\n".join(tag_names), inline=True)
        embed.add_field(name="Score", value="\n".join(scores), inline=True)
        await ctx.message.channel.send(embed=embed)

    result_from_clear = clear_trivia_leaderboard()
    if result_from_clear:
        embed = Embed(title="Success", description=f"Trivia Leaderboard Cleared", color=0x00ff00)
        await ctx.message.channel.send(embed=embed)
    now = datetime.datetime.now()
    redis_client.set('weekdayend', str(now.weekday()))
    redis_client.set('hourend', str(now.hour))
    redis_client.set('minuteend', str(now.minute-1 if now.minute > 0 else 59))


def get_current_trivia_question_id():
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            curr_question_table = Table('currentQuestion', metadata, autoload=True, autoload_with=conn)
            select_st = select([curr_question_table])
            res = conn.execute(select_st)
            print('Does it even get the current question-------------')
            for _row in res:
                return {
                    "question_id": _row[1],
                    "time_asked": _row[2]
                }
            return None
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

@client.command(pass_context=True, name="currquestion")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def get_curr_question(ctx):
    current_trivia_question_obj = get_current_trivia_question_id()
    if current_trivia_question_obj:
        current_trivia_question_id = current_trivia_question_obj['question_id']
        curr_question = get_question_by_id(current_trivia_question_id)
        embed = Embed(title="It's Trivia Time!", description=f"{curr_question}", color=jiselConf['info_color'])
        private_bot_feedback_channel = get(ctx.guild.text_channels, name=jiselConf['bot_feed_back_channel']['name'])
        await private_bot_feedback_channel.send(embed=embed)

    else:
        embed = Embed(title="No Current Question at the moment", description="There is no current question at the moment. Check back later", color=jiselConf['info_color'])
        await ctx.message.channel.send(embed=embed)

@client.event
async def on_message(message):
    if message.author.id != client.user.id:
        await main(message)

    await client.process_commands(message)

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

@client.command(pass_context=True, name="forcetrivia")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def ask_a_question(ctx):
    all_questions = get_questions()
    trivia_channel = get(ctx.guild.text_channels, name=jiselConf['trivia_channel'])
    if trivia_channel:
        current_trivia_question_obj = get_current_trivia_question_id()
        if current_trivia_question_obj:
            current_trivia_question_id = current_trivia_question_obj['question_id']
            result_remove_curr_trivia = remove_current_trivia()
            if result_remove_curr_trivia:
                private_bot_feedback_channel = get(ctx.guild.text_channels, name=jiselConf['bot_feed_back_channel']['name'])
                embed = Embed(title=f"Previous Question (ID#{current_trivia_question_id}) Expired", description="A new question has been sent to the trivia channel", color=16426522)
                await private_bot_feedback_channel.send(embed=embed)

        x = random.randint(0, len(all_questions)-1)
        embed = Embed(title=f"It's Trivia Time! You have {str(jiselConf['expiration_seconds']) if jiselConf['expiration_seconds'] < 100 else str(math.floor(jiselConf['expiration_seconds']/60))} {'seconds' if jiselConf['expiration_seconds'] < 100 else 'minutes'} to answer before the following question expires:", description=f"{trivia_questions[x]['question']}", color=7506394)
        set_current_question(all_questions[x]['id'])
        await trivia_channel.send(embed=embed)

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
    if payload.member.id != client.user.id and message.channel.type == ChannelType.text and message.channel.name in ["bug-report"]:
        previous_question_id = redis_client.get(f'{payload.member.id}_bug_report_previous_question_id')
        if previous_question_id:
            previous_question = await message.channel.fetch_message(int(previous_question_id))
            if payload.message_id == previous_question.id:
                if payload.emoji.name == 'Yes' or payload.emoji.id == int(jiselConf['fancy_yes_emoji'].split(':')[1]):
                    bug_report_preview_id = redis_client.get(f'{payload.member.id}_bug_report_preview_id')
                    bug_report_preview_msg = await message.channel.fetch_message(int(bug_report_preview_id))
                    preview_embed = bug_report_preview_msg.embeds[0]
                    preview_embed.title = "Bug Report - Successfully Recorded"
                    preview_embed.description = "This bug report was successfully recorded."
                    await send_to_google_sheet(bug_report_preview_msg)
                    await bug_report_preview_msg.edit(embed=preview_embed)
                    await message.delete()
                    await emoji_success_feedback(bug_report_preview_msg)
                    for key in redis_client.scan_iter(f'{payload.member.id}_bug_*'):
                        redis_client.delete(key)
                elif payload.emoji.name == 'No':
                    questionnaire_embed = Embed(title="You really don't have to tap on <:No:771864718939652144> to upload more attachments", description="Just keep uploading your screenshots until you're ready to hit <:Yes:771864479461539840>", color=jiselConf['info_color'])
                    questionnaire_embed.set_footer(text='You can type "cancel" at any time to exit this bug report session. Your incomplete bug report will not be recorded')
                    questionnaire_message = await message.channel.send(embed=questionnaire_embed)
                    await previous_question.delete()
                    redis_client.set(f'{payload.member.id}_bug_report_previous_question_id', questionnaire_message.id)
                    await questionnaire_message.add_reaction(':Yes:771864479461539840')
                    await questionnaire_message.add_reaction(':No:771864718939652144')


async def send_to_google_sheet(message):
    bug_report_embed = message.embeds[0]
    if message.channel.type == ChannelType.text and message.channel.name in ["bug-report"]:
        if message.guild.id == jiselConf['snk_guild_id']:
            wks = gc.open("SNK bug report chart").worksheet("Sheet1")
        else:
            wks = gc.open("PWM bug report chart").worksheet("Hoja 1")

        data = wks.get_all_values()
        headers = data[0]

        df = pd.DataFrame(data, columns=headers)
        print(df.head())
        # NO.   Submitter/Server        BUG details     Resolution      Screenshot
        bug_number = re.sub("NO.|NO|No.|No", '', bug_report_embed.fields[0].value).strip()
        bug_submitter = re.sub("Submitter/Server:", '', bug_report_embed.fields[1].value).strip()
        bug_details = re.sub("BUG details:", '', bug_report_embed.fields[2].value).strip()
        try:
            screenshots = re.sub("Screenshot:|Screenshot", '', bug_report_embed.fields[3].value).strip().split("\n")
        except IndexError:
            screenshots = ""
        bug_resolution = ""
        row = [bug_number, bug_submitter, bug_details, bug_resolution]
        if screenshots:
            row.append(f"=IMAGE(\"{screenshots[0].strip()}\")")
        wks.insert_row(row, df.shape[0] + 1, value_input_option='USER_ENTERED')
        if len(screenshots) > 1:
            for index, screenshot in enumerate(screenshots[1:]):
                row = ["Continuation", "", "", ""]
                row.append(f"=IMAGE(\"{screenshot.strip()}\")")
                wks.insert_row(row, df.shape[0] + 2 + index, value_input_option='USER_ENTERED')


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
                gya_image = gyazo_client.get_image(re.sub(f'https://gyazo.com/', '', code_uri.strip()))
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


def check_if_text_contains_codes(message):
    for text in re.split(r"\s+|\n", message):
        if len(text) == 8 and text[0:3] in jiselConf['code_prefixes']:
            return True
    return False

@client.command(pass_context=True, name="veteranswho")
async def get_all_veteran_hosters(ctx):
    veteran_members = get(ctx.guild.roles, name="Veteran Hoster").members
    msg= []
    for member in veteran_members:
        member_server = '*unassigned*' if get_server(member.id) == 0 else get_server(member.id)
        member_tag = f'<@{member.id}>' if member.id not in jiselConf['event_codes_team'] else f'{member.display_name}'
        member_charge = get_charge(member.id)
        msg.append(f"{member_tag}        |   {member.id}        |      {member_server}         |        {member_charge}")
    embed = Embed(title=f"Member                ID                             Server            Charge", description='\n'.join(msg), color=0x00ff00)
    await ctx.send(embed=embed)
@client.command(pass_context=True, name="server")
async def assign_hoster_server_db(ctx, hoster_tag: Member, server_name):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)

    with db.connect() as conn:
        update_or_insert_server_query = f"INSERT INTO pwm.\"hosterServerMapping\" (\"discordID\", \"server\") VALUES ({hoster_tag.id}, \'{server_name}\') ON CONFLICT (\"discordID\") DO UPDATE SET \"server\" = '{server_name}'"
        result = conn.execute(update_or_insert_server_query)

@client.command(pass_context=True, name="docs")
async def output_available_docs(ctx):
    commands_and_desc = {
        "+perms <@ user ID>  <insert perm here>": "Gives perms. perms include `all`, `read`, `send`, `embed`, `attach`, `external`, `react`, `cinvite`, `mchannel`, `mperm`, `mweb`, `TTS`, `mmsg`, `rhistory`, `mention`, `exreact`",
        "-perms <@ user ID>  <insert perm here>": "Removes perms. perms include `all`, `read`, `send`, `embed`, `attach`, `external`, `react`, `cinvite`, `mchannel`, `mperm`, `mweb`, `TTS`, `mmsg`, `rhistory`, `mention`, `exreact`",
        "+charge <@ user ID> <Number>": "Gives the mentioned veteran hoster <Number> code requests",
        "+charge?": "Gets the mentioned veteran hoster's currently allowed code requests",
        "+code [one or more three letter prefixes]": "+code ABC GLC WXL DEF",
        "+return <one code>": "+return WXL12345",
        "+timechannel <name> <Etc/GMT-2 or other timezone>": "name must be a string and not a tag",
        "+veteranswho": "Gives a list of veteran hosters' discord tags, discord ID, and Current Hosting Servers",
        "+server <@ mentioned hoster> <server name>": "Assigns a server name to the mentioned hoster",
        "+whichserver <@ mentioned hoster>": "Gets hoster's current server",
        "+updatecomplete day/month/year ": "+updatecomplete 26/7/2020 moves a card from Codes Sent Trello List to EC-Logs or makes a new one if Jiselicious detects a new sent code that been newly used and uploaded",
        "+hoster <Name>": "+hoster Facebook would give Facebook's current stats for the past week",
    }

    msg = []
    for c in commands_and_desc:
        msg.append(f'**{c}**\n                    |                       {commands_and_desc[c]}')
    embed = Embed(title=f"Commands and Descriptions", description='\n'.join(msg), color=0x00ff00)
    await ctx.send(embed=embed)


@client.command(pass_context=True, name="whichserver")
async def get_hoster_server(ctx, hoster_tag: Member):
    server_name = get_server(hoster_tag.id)
    await emoji_success_feedback(ctx.message)
    await ctx.send(f"{hoster_tag.name} is currently hosting in {server_name}")


def get_server(user_id):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")

    try:
        with db.connect() as conn:
            hoster_server_table = Table('hosterServerMapping', metadata, autoload=True, autoload_with=conn)
            select_st = select([hoster_server_table.c.server]).where(hoster_server_table.c.discordID == user_id)
            res = conn.execute(select_st)
            remaining_charges = res.first()
            if remaining_charges is None:
                return 0
            return remaining_charges[0]
    except Exception as err:
        print(err)

def check_if_any_ec_log_card_contains_message_codes_already(ec_logs, text_detected):
    ec_logs_card_list = ec_logs.list_cards()
    for card in ec_logs_card_list:
        card_codes = []
        for text in re.split(r"\s+|\n", card.description):
            if len(text) == 8 and text[0:3] in jiselConf['code_prefixes']:
                card_codes.append(text)
        check_if_text_includes_any_code = [code for code in card_codes if code in text_detected]
        if len(check_if_text_includes_any_code) > 0:
            return True
    return False


async def check_messages_contains_any_codes(channel, code_to_card_id_mapping, ec_logs, start_date):
    event_num = 0
    async for message in channel.history(limit=250, oldest_first=True, after=start_date):
        print(f"Message author:{message.author.name}   content: {message.clean_content}")
        if "event" in message.clean_content.lower() and "id" in message.clean_content.lower() and bool(re.search(r'\d', message.clean_content)):
            event_num = extract_event_number(message)
        if message.author.id != client.user.id:
            if "gyazo.com" not in message.clean_content and message.attachments:
                print("remote ocr-ing")
                new_card_needed = False
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
                    else:
                        new_card_needed= True
                if new_card_needed:
                    codes_used = []
                    for pic in message.attachments:
                        text_detected = detect_text_uri(pic.url)
                        if check_if_text_contains_codes(text_detected) and not check_if_any_ec_log_card_contains_message_codes_already(ec_logs, text_detected):
                            for text in re.split(r"\s+|\n", text_detected):
                                if len(text) == 8 and text[0:3] in jiselConf['code_prefixes']:
                                    codes_used.append(text)
                        else:
                            new_card_needed = False
                    if new_card_needed:
                        new_card = ec_logs.add_card(message.author.name, message.clean_content)
                        new_card.change_pos("bottom")
                        codes_sent = "Codes:\n" + "       ".join(codes_used)
                        hoster_server = get_server(message.author.id)
                        new_card.set_description(f"Server: {hoster_server}" + "\n" + new_card.description + f"\n{codes_sent}" + f"\n#{event_num}")
            elif "gyazo.com" in message.clean_content:
                codes = list(set(get_all_codes_from_gyazo_link(message)))
                if not check_if_any_ec_log_card_contains_message_codes_already(ec_logs, '   '.join(codes)):
                    event_number = extract_event_number(message)
                    hoster_server = get_server(message.author.id)
                    card_content = f"Server: {hoster_server}" + "\n" + message.clean_content.split('\n')[1] + "\n" + '   '.join(codes) + "\n\n#" + str(event_number)
                    new_card = ec_logs.add_card(message.author.nick or message.author.name, card_content)
                    new_card.change_pos("bottom")

@client.command(pass_context=True, name="getquestion")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Admin")
async def get_answers_to_question(ctx, *args):
    question = None
    question_id = None
    items = []
    potential_name_or_id = ' '.join(args).split("|")[0]
    if potential_name_or_id.strip().isnumeric():
        question_id = potential_name_or_id
    else:
        question = potential_name_or_id


    try:
        answers_to_question = []
        table_answers = get_table_answers(question_id, question)
        for item_name in table_answers:
            answers_to_question.append("▫️" + item_name['answer'])
        if question_id:
            question = get_question_by_id(question_id)
        else:
            question_id = get_id_of_question(question)
        i = 0
        embed_sets = []
        max_n = math.ceil(len(table_answers) / 20)
        while i < max_n:
            begin_num = i * 20
            embed = Embed(title=f"Question ID#{question_id}" if i == 0 else "Continued", description=f"{question}", color=0x00ff00)
            answer_ids = '\n'.join([str(answer_row['id']) for answer_row in table_answers[begin_num:begin_num + 20]])
            answer_texts = '\n'.join([answer_row['answer'] for answer_row in table_answers[begin_num:begin_num + 20]])
            embed.add_field(name='Answer ID', value=f"{answer_ids}", inline=True)
            embed.add_field(name='Answer', value=f"{answer_texts}", inline=True)
            embed_sets.append(embed)
            i += 1
        for embed in embed_sets:
            await ctx.message.channel.send(embed=embed)
    except Exception as err:
        print(err)

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
                question = row[1]
            return question
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

def get_id_of_question(question):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            questions_table = Table('triviaQuestions', metadata, autoload=True, autoload_with=conn)
            select_st = select([questions_table]).where(questions_table.c.question == question)
            res = conn.execute(select_st)
            for row in res:
                question = row[1]
                question_id = row[0]
                break
            return question_id
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()


def get_table_answers(question_id, question):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            questions_table = Table('triviaQuestions', metadata, autoload=True, autoload_with=conn)
            if question_id:
                condition = questions_table.c.id == question_id
            else:
                condition = questions_table.c.question == question
            select_st = select([questions_table]).where(condition)
            res = conn.execute(select_st)
            for row in res:
                question = row[1]
                question_id = row[0]
            answers_table = Table('triviaAnswers', metadata, autoload=True, autoload_with=conn)
            select_st = select([answers_table]).where(answers_table.c.question_id == question_id)
            res = conn.execute(select_st)
            answers_to_question = []
            for row in res:
                answers_to_question.append({
                    'id': row.id,
                    'answer': row.answer
                })
            return answers_to_question
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

@client.command(pass_context=True, name="createquestion")
async def create_question(ctx, *args):
    question=""
    items = []
    if "|" in args:
        question = ' '.join(args).split("|")[0]
        items = ' '.join(args).split("|")[1:]
    else:
        question = ' '.join(args)
    question = question.strip()
    answers_to_question = []
    question_id = create_db_questions(question, items, answers_to_question)
    embed_sets = []
    i = 0
    max_n = math.ceil(len(answers_to_question) / 20)
    while i < max_n:
        begin_num = i * 20
        embed = Embed(title=f"Question ID#{question_id} Created" if i == 0 else "Continued", description=question, color=0x00ff00)
        answer_ids = '\n'.join([str(answer_row['id']) for answer_row in answers_to_question[begin_num:begin_num + 20]])
        answer_texts = '\n'.join([answer_row['answer'] for answer_row in answers_to_question[begin_num:begin_num + 20]])
        embed.add_field(name='Answer ID', value=f"{answer_ids}")
        embed.add_field(name='Answer', value=f"{answer_texts}")
        embed_sets.append(embed)
        i += 1
    for embed in embed_sets:
        await ctx.message.channel.send(embed=embed)


def create_db_questions(question, items, answers_to_question):
    try:
        db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=
        jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
        db = create_engine(db_string)
        metadata = MetaData(schema="pwm")

        with db.connect() as conn:
            questions_table = Table('triviaQuestions', metadata, autoload=True, autoload_with=conn)
            insert_statement = questions_table.insert().values(question=question)
            res = conn.execute(insert_statement)
            question_id = res.inserted_primary_key[0]


            answers_table = Table('triviaAnswers', metadata, autoload=True, autoload_with=conn)
            select_st = select([answers_table])

            for item in items:
                insert_statement = answers_table.insert().values(answer=item.strip(), question_id=question_id)
                conn.execute(insert_statement)
            select_st = select([answers_table]).where(answers_table.c.question_id == question_id)
            res = conn.execute(select_st)
            for row in res:
                answers_to_question.append({
                    "id": row.id,
                    "answer": row.answer
                })
            return question_id
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

@client.command(pass_context=True, name="answerquestion")
async def add_answers_question(ctx, *args):
    question_id = None
    question = ""

    items = []
    question = ' '.join(args).split("|")[0]
    items = ' '.join(args).split("|")[1:]

    try:
        if question.strip().isnumeric():
            question_id = int(question.strip())
        question_answers = []
        gathered_question = add_to_db_question(question_id, question.strip(), items, question_answers)
        embed_sets = []
        i = 0
        max_n = math.ceil(len(question_answers) / 20)
        while i < max_n:
            begin_num = i * 20
            embed = Embed(title=f"Added to Question ID#{question_id} " if i == 0 else "Continued", description=gathered_question['question'], color=0x00ff00)
            answer_ids = '\n'.join(
                [str(answer_row['id']) for answer_row in question_answers[begin_num:begin_num + 20]])
            answer_texts = '\n'.join(
                [answer_row['answer'] for answer_row in question_answers[begin_num:begin_num + 20]])
            embed.add_field(name='Answer ID', value=f"{answer_ids}")
            embed.add_field(name='Answer', value=f"{answer_texts}")
            embed_sets.append(embed)
            i += 1
        for embed in embed_sets:
            await ctx.message.channel.send(embed=embed)
    except Exception as err:
        print(err)

def add_to_db_question(question_id, question, items, question_answers):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")

    try:
        with db.connect() as conn:
            questions_table = Table('triviaQuestions', metadata, autoload=True, autoload_with=conn)
            if question_id:
                condition = questions_table.c.id == question_id
            else:
                condition = questions_table.c.question == question
            select_st = select([questions_table]).where(condition)
            res = conn.execute(select_st)
            gathered_question = [{column: value for column, value in rowproxy.items()} for rowproxy in res][0]


            answers_table = Table('triviaAnswers', metadata, autoload=True, autoload_with=conn)
            for item in items:
                insert_statement = answers_table.insert().values(answer=item.strip(), question_id=gathered_question['id'])
                conn.execute(insert_statement)
            select_st = select([answers_table]).where(answers_table.c.question_id == gathered_question['id'])
            res = conn.execute(select_st)
            for row in res:
                question_answers.append({
                    'id': row.id,
                    'answer': row.answer
                })

            return gathered_question

    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

def delete_question_by_id(question_id):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            questions_table = Table('triviaQuestions', metadata, autoload=True, autoload_with=conn)
            delete_query = f"DELETE FROM pwm.\"triviaQuestions\" WHERE id={question_id}"
            res = conn.execute(delete_query)
            delete_answers_query = f"DELETE FROM pwm.\"triviaAnswers\" WHERE \"question_id\"={question_id}"
            res2 = conn.execute(delete_answers_query)
            return True
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

@client.command(pass_context=True, name="deleteanswer")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def delete_answer(ctx, id):
    result_rom_deletion = delete_answer_by_id(id)
    if result_rom_deletion:
        embed = Embed(title=f"Answer #{id} Deleted:", color=0x00ff00)
        await ctx.message.channel.send(embed=embed)

@client.command(pass_context=True, name="stop")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def stop_trivia(ctx):
    if ctx.message.channel.name == jiselConf['bot_feed_back_channel']:
        try:
            redis_client.set('start', 'no')
            await emoji_success_feedback(ctx.message)
        except:
            await ctx.send("Sorry, something went wrong with stopping the trivia.")


@client.command(pass_context=True, name="start")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def start_trivia(ctx):
    if ctx.message.channel.name == jiselConf['bot_feed_back_channel']:
        try:
            redis_client.set('start', 'yes')
            await emoji_success_feedback(ctx.message)
        except:
            await ctx.send("Sorry, something went wrong with starting the trivia.")


def delete_answer_by_id(answer_id):
    db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
    db = create_engine(db_string)
    metadata = MetaData(schema="pwm")
    try:
        with db.connect() as conn:
            delete_answers_query = f"DELETE FROM pwm.\"triviaAnswers\" WHERE \"id\"={answer_id}"
            res2 = conn.execute(delete_answers_query)
            return True
    except Exception as err:
        print(err)
        if conn:
            conn.close()
        db.dispose()

@client.command(pass_context=True, name="delete")
@commands.has_any_role('Jiselicious', 'Moderator', 'Assistant Admin', "Veteran Hoster")
async def delete_question(ctx, id):
    gathered_question = get_question_by_id(id)
    result_from_deletion = delete_question_by_id(id)
    if result_from_deletion:
        embed = Embed(title=f"Question ID#{id} Deleted:", description=gathered_question, color=0x00ff00)
        await ctx.message.channel.send(embed=embed)

@client.command(pass_context=True, name="listquestions")
async def get_questions_table(ctx):
    list_rows = get_questions()
    description_rows = []

    for row in list_rows:
        description_rows.append(f"#{row['id']}: {row['question']}")
    max_n = math.ceil(len(description_rows) / 20)
    embed_sets = []
    i = 0
    while i < max_n:
        begin_num = i*20
        embed = Embed(title=f"Existing Questions" if i == 0 else "Continued", description='\n'.join(description_rows[begin_num:begin_num+20]), color=0x00ff00)
        embed_sets.append(embed)
        i += 1
    for embed in embed_sets:
        await ctx.message.channel.send(embed=embed)

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
async def update_week_host(ctx, week_number=None):
    if ctx.message.channel.name == jiselConf['complete_events_channel'] and ctx.author.id in jiselConf['event_codes_team']:
        board = trello_client.get_board(jiselConf['trello']['board_id'])
        most_recent_week_list_name = [week_list.name for week_list in board.get_lists("all") if week_list.name.startswith("Week")][0]
        used_week_number = int(re.findall('\d+', most_recent_week_list_name)[0])
        if week_number:
            used_week_number = week_number
        latest_week_list = [t_list for t_list in board.get_lists("all") if t_list.name == f'Week {used_week_number}'][0]
        cards_latest_week = latest_week_list.list_cards()
        board_tally = [t_list for t_list in board.get_lists("all") if t_list.name == 'Tally']
        if not board_tally:
            board.add_list('Tally')
        board_tally = [t_list for t_list in board.get_lists("all") if t_list.name == 'Tally'][0]
        for card in cards_latest_week:
            names_to_look_for = [card.name] if "and" not in card.name else re.split(',|and', card.name)
            for searching_name in names_to_look_for:
                found_name_in_tally = [t_card for t_card in board_tally.list_cards() if t_card.name in searching_name]
                if not found_name_in_tally:
                    date_started=datetime.datetime.today().strftime("%d/%b/%y").upper()
                    board_tally.add_card(f"{searching_name}", f"Started on: {date_started}\n\n**Week**: {used_week_number}\n\nEvents done this week: 1\nEvents done this month: 1\nTotal events hosted: 1")
                elif f'**Week**: {used_week_number}' not in found_name_in_tally[0].description:
                    card_section = found_name_in_tally[0].description.split("\n")
                    is_veteran = '[VETERAN]' in found_name_in_tally[0].description
                    veteran_index = 1 if is_veteran else 0
                    veteran_line = "[VETERAN]"+"\n" if is_veteran else ""
                    started_line = card_section[0 + veteran_index]
                    week_status = card_section[2 + veteran_index]
                    week_events = card_section[4 + veteran_index]
                    new_week_number = 1 if 'Processing' not in week_status else int((re.findall('\d+', week_events) or [0])[0]) + 1
                    month_events = card_section[5 + veteran_index]
                    new_month_number = int((re.findall('\d+', month_events) or [0])[0]) + 1
                    total_events = card_section[6 + veteran_index]
                    new_total_number = int((re.findall('\d+', total_events) or [0])[0]) + 1
                    found_name_in_tally[0].set_description(f"{veteran_line}{started_line}\n\n**Week**: Processing to {used_week_number}\n\nEvents done this week: {new_week_number}\nEvents done this month: {new_month_number}\nTotal events hosted: {new_total_number}")
        for t_card in board_tally.list_cards():
            card_section = t_card.description.split("\n")
            is_veteran = '[VETERAN]' in t_card.description
            veteran_index = 1 if is_veteran else 0
            most_recent_week_list = [week_list for week_list in board.get_lists("all") if week_list.name.startswith("Week")][0]
            found_name_in_curr_week = [w_card for w_card in most_recent_week_list.list_cards() if t_card.name in w_card.name]
            if not found_name_in_curr_week:
                card_section[4 + veteran_index] = "Events done this week: -"
            card_section[2 + veteran_index] = f"**Week**: {used_week_number}"
            whole_card_desc = "\n".join(card_section)
            t_card.set_description(whole_card_desc)
        await emoji_success_feedback(ctx.message)


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
# client.run(jiselConf['test_bot_token'])
# pwm token
client.run(jiselConf['bot_token'])

# pm2 reload antiPerms.py --interpreter=python3


