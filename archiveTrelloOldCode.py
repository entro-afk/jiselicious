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
            eastern_time_card = dateutil.parser.parse(card_action['date']).astimezone(
                pytz.timezone('US/Eastern')).replace(tzinfo=None)
            if 'listBefore' in card_action['data'] and 'listAfter' in card_action[
                'data'] and past < eastern_time_card and eastern_time_card < future:
                if card_action['data']['listBefore']['id'] == jiselConf['trello']['list_id'] and \
                        card_action['data']['listAfter']['id'] == jiselConf['trello']['code_sent_list_id']:
                    guild = client.get_guild(jiselConf['guild_id'])
                    channel = get(guild.text_channels, name=jiselConf['event_request_channel'][0])
                    print(_row[1])
                    msg = await channel.fetch_message(_row[1])
                    emoji = get(client.emojis, name='yes')
                    await msg.add_reaction(emoji)
                    hoster_receiving_codes = client.get_user(_row[2])
                    guild = client.get_guild(jiselConf['guild_id'])
                    hoster_roles = [u.roles for u in guild.members if u.id == _row[2]] and \
                                   [u.roles for u in guild.members if u.id == _row[2]][0]
                    hoster_role_names = [role.name for role in hoster_roles]
                    is_veteran_hoster = jiselConf['veteran_hoster_role_name'] in hoster_role_names
                    if card_action['memberCreator']['username'] in jiselConf['trello'][
                        'special_sender_usernames'] and not is_veteran_hoster:
                        card_has_codes = check_if_card_contains_codes(card)
                        if not card_has_codes:
                            num_codes_needed = find_number_of_codes_needed(card)
                            append_random_codes(card, num_codes_needed)
                        await client.wait_until_ready()
                        code_giver = await client.fetch_user(int(
                            jiselConf['trello']['trello_discord_id_pair'][card_action['memberCreator']['username']]))
                        print('jisel---- none prob')
                        print(jiselConf['trello']['trello_discord_id_pair'])

                        embed = Embed(title=f"You have sent {hoster_receiving_codes} the following codes:",
                                      description=card.description, color=0x00ff00)
                        await code_giver.send(embed=embed)
                        hoster_embed = Embed(title=f"{code_giver.name} has prepared codes for your request:",
                                             description=card.description, color=0x00ff00)
                        await hoster_receiving_codes.send(embed=hoster_embed)
                        insert_statement = trello_hoster_cards_archive.insert().values(cardID=_row[0],
                                                                                       messageID=_row[1],
                                                                                       requestingHosterID=_row[2])
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
