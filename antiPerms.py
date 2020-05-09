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
async def perms(ctx, member: Member or Role, *args):
    if ctx.author.id in jiselConf['perms_magic']:
        current_channel_perms = member.permissions_in(ctx.message.channel)
        overwrite = PermissionOverwrite()
        permission_options = {
            'read': 'read_messages',
            'speak': 'send_messages',
            'embed': 'embed_links',
            'attach': 'attach_files',
            'external': 'external_emojis',
            'react': 'add_reactions'
        }
        for perm_option in permission_options:
            if perm_option in args:
                setattr(overwrite, permission_options[perm_option], False)
            else:
                setattr(overwrite, permission_options[perm_option], getattr(current_channel_perms, permission_options[perm_option]))
        if args[0].lower() == 'all':
            for perm_option in permission_options:
                setattr(overwrite, permission_options[perm_option], False)

        await ctx.message.channel.set_permissions(member, overwrite=overwrite)
        emoji = get(client.emojis, name='yes')
        await ctx.message.add_reaction(emoji)
    else:
        await ctx.send("You are not V-IdaSM. Therefore, you are not allowed to run this command")



# test token
# client.run(channelsConf['test_bot_token'])
# pwm token
client.run(jiselConf['bot_token'])

# pm2 reload jisel.py --interpreter=python3
