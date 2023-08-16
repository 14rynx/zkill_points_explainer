from math import floor
import ssl

import aiohttp
import asyncio
import certifi

ssl_context = ssl.create_default_context(cafile=certifi.where())


async def get_item_data(type_id, session):
    async with session.get(f"https://esi.evetech.net/latest/universe/types/{type_id}/") as response:
        if response.status == 200:
            return await response.json(content_type=None)
        return {}


async def get_group_data(group_id, session):
    async with session.get(f"https://esi.evetech.net/latest/universe/groups/{group_id}/") as response:
        if response.status == 200:
            return await response.json(content_type=None)
        return {}


async def get_group_id(type_id, session):
    return (await get_item_data(type_id, session))["group_id"]


async def get_category_id(type_id, session):
    return (await get_group_data(await get_group_id(type_id, session), session))["category_id"]


async def get_dogma_attribute(type_id, session, attribute_id):
    for attribute in (await get_item_data(type_id, session))["dogma_attributes"]:
        if attribute["attribute_id"] == attribute_id:
            return float(attribute["value"])


def unpacker(func):
    async def wrapper(type_id, session):
        type_id = type_id["item_type_id"] if type(type_id) == dict else type_id
        return await func(type_id, session)

    return wrapper


@unpacker
async def get_rig_size(ship_type_id, session):
    try:
        if (await get_group_id(ship_type_id, session)) == 963:  # Strategic Cruisers
            return 2
        return int(await get_dogma_attribute(ship_type_id, session, 1547))
    except TypeError:
        return 1


@unpacker
async def get_meta_level(type_id, session):
    return int(await get_dogma_attribute(type_id, session, 633))


@unpacker
async def get_npc_rig_size(type_id, session):
    group_rig_sizes = {
        883: 4,  # Rorq
        547: 4,  # Carrier
        485: 4,  # Dread
        1538: 4,  # FAX
        513: 4,  # Freighter
        902: 4,  # JF
        4594: 4,  # Lancer
        659: 4,  # Super
        30: 4,  # Titan

        27: 3,  # BS
        898: 3,  # Blops
        381: 3,  # Elite Battleship
        941: 3,  # Indu Command
        900: 3,  # Marauder

        1201: 2,  # ABC
        1202: 2,  # BR
        419: 2,  # BC
        906: 2,  # Recon
        540: 2,  # Command
        26: 2,  # Cruiser
        380: 2,  # DST
        543: 2,  # Exhumer
        1972: 2,  # Flag Cruiser
        833: 2,  # Cyno
        28: 2,  # Hauler
        358: 2,  # HAC
        894: 2,  # HIC
        832: 2,  # Logi
        463: 2,  # Barge
        963: 2,  # T3C

        324: 1,
        2001: 1,  # Citizenship
        1534: 1,  # CD
        237: 1,  # Corvette
        830: 1,  # Covops
        420: 1,  # Destroyer
        893: 1,  # EAF
        1283: 1,  # Expedition Frigate
        831: 1,  # Ceptor
        541: 1,  # Dictor
        1527: 1,  # Logi Frig
        1022: 1,  # Zephyr
        31: 1,  # Shuttle
        834: 1,  # Bomber
        1305: 1,  # T3D
        29: 1  # Capsule
    }
    try:
        return group_rig_sizes[int(await get_dogma_attribute(type_id, session, 1766))]
    except (TypeError, KeyError):
        return 1


@unpacker
async def get_item_name(type_id, session):
    return (await get_item_data(type_id, session))["name"]


@unpacker
async def is_heatable(type_id, session):
    return await get_dogma_attribute(type_id, session, 1211)


@unpacker
async def is_dda(type_id, session):
    return (await get_group_id(type_id, session)) == 645


@unpacker
async def is_miner(type_id, session):
    return (await get_group_id(type_id, session)) == 54


@unpacker
async def is_structure(type_id, session):
    return (await get_category_id(type_id, session)) == 65


async def get_points(kill_id):
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        async with session.get(f"https://zkillboard.com/api/killID/{kill_id}/") as response:
            if not response.status == 200:
                return
            zkill_data = await response.json(content_type=None)

        killmail_id = zkill_data[0]['killmail_id']
        killmail_hash = zkill_data[0]['zkb']['hash']

        async with session.get(
                f"https://esi.evetech.net/latest/killmails/{killmail_id}/{killmail_hash}/?datasource=tranquility") as response:
            if not response.status == 200:
                return
            esi_data = await response.json(content_type=None)

        base_points = 5 ** (await get_rig_size(esi_data["victim"]["ship_type_id"], session))

        print(f"Ship Base Points: {base_points}")

        # Items on Victim Ship Stuff
        print("Looking at Items:")
        danger = 0
        for item in esi_data["victim"]["items"]:
            type_id = item["item_type_id"]
            quantity = item.get("quantity_dropped", 0) + item.get("quantity_destroyed", 0)

            if await get_category_id(type_id, session) != 7:
                continue

            if "flag" in item and 11 <= item["flag"] < 35 or 125 <= item["flag"] < 129:
                meta = 1 + await get_meta_level(type_id, session) // 2

                if await is_heatable(item, session) or await is_dda(item, session):
                    print(f"   {quantity}x {await get_item_name(type_id, session)} added {meta}")
                    danger += quantity * meta

                if await is_miner(item, session):
                    print(f"   {quantity}x {await get_item_name(type_id, session)} subtracted {meta}")
                    danger -= quantity * meta

        points = base_points + danger
        if danger < 4:
            points *= max(0.01, danger / 4)  # If the ship has more than 4 heatable modules this doesn't do anything
            print(f"=> Ship was of low danger, reduced points by ({max(0.01, danger / 4)}) to {points}")
        else:
            print(f"=> Increased Points to {floor(points)} (by {danger}) due to items fitted.")

        # Reducing things by amount of Attackers
        attackers_amount = len(esi_data["attackers"])
        involved_penalty = max(1.0, attackers_amount ** 2 / 2)

        print(f"Kill has {attackers_amount} attackers")
        points /= involved_penalty
        print(
            f"=> Reducing points by {100 * (1 - 1 / involved_penalty):.1f} % to {floor(points)} for the amount of attackers")

        # Looking at the Size of each Attacker
        characters = 0
        attackers_total_size = 0
        for attacker in esi_data["attackers"]:
            if await is_structure(attacker["ship_type_id"], session):
                print("Structure on Killmail => Giving 1 Point and throwing everything else out the window.")
                return 1

            if "character_id" in attacker:
                characters += 1
                group_id = await get_group_id(attacker["ship_type_id"], session)
                rig_size = await get_rig_size(attacker["ship_type_id"], session)
                print(await get_item_name(attacker["ship_type_id"], session), group_id, rig_size)
                if group_id == 29:  # Capsule
                    attackers_total_size += 5 ** (rig_size + 1)
                else:
                    attackers_total_size += 5 ** rig_size
                print(attackers_total_size)

        if characters == 0:
            print("NPC Killmail -> Giving 1 Point and throwing everything else out the window.")
            return 1

        average_size = max(1.0, attackers_total_size / attackers_amount)
        print(f"Average attacker size is {average_size}, victim size is {base_points}")
        ship_size_modifier = min(1.2, max(0.5, base_points / average_size))
        points = floor(points * ship_size_modifier)
        if ship_size_modifier > 1:
            print(
                f"=> Increasing points by {100 * (ship_size_modifier - 1):.1f} % to {points} for the size of attackers")
        elif ship_size_modifier < 1:
            print(
                f"=> Reducing points by {100 * (1 - ship_size_modifier):.1f} % to {points} for the size of attackers")

        if points < 1:
            print("The kill was worthless, but I have to give one point anyway")
            return 1

        return floor(points)


def explain(kill_id):
    points = asyncio.run(get_points(kill_id))
    print(f"Resulted in {points}")


explain(110850977)
