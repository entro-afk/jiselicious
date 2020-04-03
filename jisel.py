from discord.ext import commands
import yaml
from trello import TrelloClient


client = commands.Bot(command_prefix='!')
with open(r'jiselConf.yaml') as file:
    # The FullLoader parameter handles the conversion from YAML
    # scalar values to Python the dictionary format
    jiselConf = yaml.load(file, Loader=yaml.FullLoader)

    print(jiselConf)


trello_client = TrelloClient(
    api_key=jiselConf['trello']['api_key'],
    api_secret=jiselConf['trello']['api_secret'],
    token=jiselConf['trello']['token'],
)


@client.event
async def on_ready():
    print('Bot is ready.')


@client.event
async def on_message(message):
    if message.channel.name in jiselConf['event_request_channel'] and "Server:".upper() in message.clean_content.upper():
        board = trello_client.get_board(jiselConf['trello']['board_id'])
        request_list = board.get_list(jiselConf['trello']['list_id'])
        request_list.add_card(message.author.nick, message.clean_content)


# test token
# client.run(channelsConf['test_bot_token'])
# pwm token
client.run(jiselConf['bot_token'])

# pm2 reload jisel.py --interpreter=python3
