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
from discord import File, Member, Role, PermissionOverwrite
import requests
import time
import asyncio
import threading
from typing import Union

client = commands.Bot(command_prefix='-')


with open(r'jiselConf.yaml') as file:
    # The FullLoader parameter handles the conversion from YAML
    # scalar values to Python the dictionary format
    jiselConf = yaml.load(file, Loader=yaml.FullLoader)

    print(jiselConf)


@client.event
async def on_ready():
    print('Bot is ready.')


@client.command(pass_context=True)
async def perms(ctx, member: Union[Member, Role], *args) :
    if ctx.author.id in jiselConf['perms_magic']:
        if args[0].isdigit():
            given_channel = client.get_channel(args[0])
        else:
            given_channel = ctx.message.channel
        current_channel_perms = hasattr(member, 'permissions_in') and member.permissions_in(given_channel) or member.members[0].permissions_in(given_channel)
        overwrite = PermissionOverwrite()
        permission_options = {
            'speak': 'speak',
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
                setattr(overwrite, permission_options[perm_option], False)
            else:
                setattr(overwrite, permission_options[perm_option], getattr(current_channel_perms, permission_options[perm_option]))
        if args[0].lower() == 'all':
            for perm_option in permission_options:
                setattr(overwrite, permission_options[perm_option], False)

        await given_channel.set_permissions(member, overwrite=overwrite)
        emoji = get(client.emojis, name='yes')
        await ctx.message.add_reaction(emoji)
    else:
        await ctx.send("You are not V-IdaSM. Therefore, you are not allowed to run this command")



# test token
# client.run(channelsConf['test_bot_token'])
# pwm token
client.run(jiselConf['bot_token'])

# pm2 reload jisel.py --interpreter=python3
