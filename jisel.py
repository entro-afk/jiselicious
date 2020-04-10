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

client = commands.Bot(command_prefix='!')
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

credentials = ServiceAccountCredentials.from_json_keyfile_name(
         jiselConf['goog'], scope) # Your json file here

gc = gspread.authorize(credentials)


@client.event
async def on_ready():
    print('Bot is ready.')


@client.event
async def on_message(message):
    if message.channel.name in jiselConf['event_request_channel'] and "Server:".upper() in message.clean_content.upper():
        board = trello_client.get_board(jiselConf['trello']['board_id'])
        request_list = board.get_list(jiselConf['trello']['list_id'])
        request_list.add_card(message.author.nick or message.author.name, message.clean_content)
    if message.channel.name in ["bug-report","event-submissions"]:
        wks = gc.open("PWM bug report chart").worksheet("Hoja 1")

        data = wks.get_all_values()
        headers = data[0]

        df = pd.DataFrame(data, columns=headers)
        print(df.head())

        # NO.	Submitter/Server	BUG details	Resolution	Screenshot
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
                            if r.content_type == 'image/jpeg':
                                result = await r.read()
                                row.append(f"=IMAGE(\"{message.attachments[0].url}\")")
                                wks.insert_row(row, df.shape[0] + 1, value_input_option='USER_ENTERED')
            else:
                wks.insert_row(row, df.shape[0] + 1, value_input_option='USER_ENTERED')
        elif message.attachments:
            async with aiohttp.ClientSession() as session:
                async with session.get(message.attachments[0].url) as r:
                    if r.status == 200:
                        result = await r.read()
                        row = ["", "", "", "", f"=IMAGE(\"{message.attachments[0].url}\")"]
                        wks.insert_row(row, df.shape[0] + 1, value_input_option='USER_ENTERED')



# test token
# client.run(channelsConf['test_bot_token'])
# pwm token
client.run(jiselConf['bot_token'])

# pm2 reload jisel.py --interpreter=python3
