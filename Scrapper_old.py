import asyncio
import base64
import io
import time
from collections import defaultdict
from threading import Thread
import aiohttp
from nbt import nbt
import json
import builtins


def format_output(var):
    match var:
        case set():
            var = list(var)
        case dict():
            var = {k: format_output(v) for k, v in var.items()}
    return var


def time_func(message: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time: float = time.time()
            result = await func(*args, **kwargs)
            end_time: float = time.time()

            output: str = f"{(message + ":").ljust(16)}{{}}s"
            print(output.format(round(end_time - start_time, 3)))
            return result

        return wrapper
    return decorator


def update_attributes(path: dict, item_attributes: dict):
    for attr, value in item_attributes.items():
        try:
            match type(value):
                case builtins.dict:
                    if not isinstance(path[attr], dict):
                        path[attr] = defaultdict(set)

                    update_attributes(path[attr], value)
                case builtins.list:
                    path[attr].update(value)
                case _:
                    path[attr].add(value)
        except Exception as e:
            with open("path.json", "w", encoding="utf-8") as f:
                json.dump(format_output(path), f, indent=2)
            with open("item_attributes.json", "w", encoding="utf-8") as f:
                json.dump(format_output(item_attributes), f, indent=2)

            raise Exception(e)


class Scrapper:
    __URL = "https://api.hypixel.net/v2/skyblock/auctions?page={}"
    __ENDED_URL = "https://api.hypixel.net/v2/skyblock/auctions_ended"
    __ITEMS_URL = "https://api.hypixel.net/v2/resources/skyblock/items"
    __INTERVAL = 60 - 1  # to recalibrate
    __OFFSET = 14  # to account for initial update times
    __SKIP_ATTRIBUTES = ("active", "hideInfo", "hideRightClick", "noMove", "timestamp", "id", "uuid", "bossId", "spawnedFor", "originTag", "fungi_cutter_mode", "effects", "necromancer_souls", "uniqueId", "recipient_name", "recipient_id")

    def __init__(self) -> None:
        self.__session: aiohttp.ClientSession
        self.__last_updated: int = 0

        # auction data
        self.__items: dict
        self.__index: dict
        self.__attributes: dict

    async def __fetch(self, url: str, update: bool = False) -> dict:
        resp: aiohttp.ClientResponse = await self.__session.get(url)

        if resp.status == 200:
            page: dict = await resp.json()
            last_updated: int = page["lastUpdated"]

            if last_updated != self.__last_updated:  # if this ver is more recent (should be ~60s)
                if update:  # update is true
                    self.__last_updated = last_updated
                else:
                    if last_updated < self.__last_updated:  # waiting for page to update
                        print(f"URL: {url[36:]} | Waiting 1s")

                        # not good
                        await asyncio.sleep(1)
                        page = await self.__fetch(url)
                    else:
                        raise Exception("Shouldn't be possible. Page is more recent")
            elif (
                    last_updated == self.__last_updated and update
            ):  # if ver is same and update is true
                print(
                    url[36:],
                    int(self.__last_updated / 1000),
                    int(last_updated / 1000),
                    int(time.time()),
                    int(last_updated / 1000 + self.__INTERVAL - time.time()),
                    int(last_updated / 1000 + self.__INTERVAL),
                    sep="\t|\t",
                )
                await asyncio.sleep(1)
                page = await self.__fetch(url, update=update)

                # raise Exception("last_updated is same")

            # print(f"Page: {page['page']+1}")
            return page

        else:
            raise Exception(f"Error code: {resp.status}\n{url}\n{await resp.read()}")

    @time_func("Fetching time")
    async def __get_auctions(self) -> list:
        tasks: list = []
        url: str

        # getting first page
        url = self.__URL.format(0)
        first_page: dict = await self.__fetch(url, update=True)
        total_pages: int = first_page["totalPages"]

        # preparing remaining pages
        for page_num in range(1, total_pages):
            url = self.__URL.format(page_num)
            tasks.append(self.__fetch(url))

        # getting remaining pages
        pages: list = [first_page] + list(
            await asyncio.gather(*tasks)
        )  # prepend first page
        auctions: list = [auction for page in pages for auction in page["auctions"]]
        return auctions

    @time_func("Items time")
    async def __get_items(self) -> dict:
        url = self.__ITEMS_URL
        resp = await self.__fetch(url, True)
        items: list[dict] = resp["items"]

        formatted_items = {}
        for item in items:
            item_id = item.pop("id")
            formatted_items[item_id] = item

        return formatted_items

    @time_func("Fetch new")
    async def __get_new(self, index: dict) -> list:
        new_auctions = []
        page_num = 0

        while True:
            url = self.__URL.format(page_num)
            page = await self.__fetch(url)
            page_auctions: list = page["auctions"]

            for auction in page_auctions:
                # new auctions are prepended but non-bin auctions remain in the same position in api
                if any(auction["uuid"] in index[item_id]["auctions"] for item_id in index):  # new or non-bin
                    if auction["bin"]:  # found first real repeating
                        return new_auctions
                else:  # prevent adding existing non-bin in new_auctions
                    new_auctions.append(auction)

            page_num += 1

    @time_func("Fetch ended")
    async def __get_ended(self):
        page: dict = await self.__fetch(self.__ENDED_URL, update=True)
        auctions: list[dict] = page["auctions"]

        auction_ids = [auction["auction_id"] for auction in auctions]

        return auction_ids

    def __process_item(self, item):
        def flatten_gems(gems: nbt.TAG_Compound) -> dict:
            flattened = {}
            specials = {}

            for k, v in gems.items():
                if k != "unlocked_slots" and isinstance(v, nbt.TAG_Compound):
                    v = v["quality"]
                if k.endswith("_gem"):
                    slot = k[:-4]
                    specials[slot] = v
                    continue

                flattened[k] = v

            # cleanup _gem scenarios
            for slot, gem in specials.items():
                quality = flattened[slot]
                flattened[slot] = {
                    "gem": gem,
                    "quality": quality
                }

            return flattened

        match type(item):
            case nbt.TAG_List:
                item = [self.__process_item(nested) for nested in item]
            case nbt.TAG_Compound | builtins.dict:
                new_dict = dict()
                for k, v in item.items():
                    if k in self.__SKIP_ATTRIBUTES:
                        continue
                    elif k == "petInfo":
                        v = json.loads(v.value)
                        new_dict = self.__process_item(v)
                        continue
                    elif k == "gems":
                        v = flatten_gems(v)

                    new_dict[k] = self.__process_item(v)
                item = new_dict
            case nbt.TAG_Byte_Array:
                return str(item)
            case nbt.TAG_String:
                item = item.value
            case builtins.float:
                item = int(item)
            case _:
                if isinstance(item, nbt.TAG):
                    item = item.value

        if isinstance(item, float):
            item = int(item)

        return item
    
    async def __process_auction(self, auction_data: dict) -> tuple[str, str, dict, dict]:
        raw_bytes = auction_data["item_bytes"]
        decoded = base64.b64decode(raw_bytes)
        file_obj = io.BytesIO(decoded)
        nbt_data = nbt.NBTFile(fileobj=file_obj)["i"][0]
        attributes = self.__process_item(nbt_data["tag"]["ExtraAttributes"])

        uuid: str = auction_data["uuid"]
        item_id: str = nbt_data["tag"]["ExtraAttributes"]["id"].value

        if item_id == "PET":
            pet_type = attributes.pop("type")
            item_id = f"{pet_type}_PET"
        elif "RUNE" in item_id:  # account for UNIQUE_RUNE
            runes_data = attributes.pop("runes")
            attributes["level"] = next(iter(runes_data.values()))

            rune_type = next(iter(runes_data))
            item_id = f"{rune_type}_RUNE"

        new_data = {
            "name": auction_data["item_name"],
            "tier": auction_data["tier"],
            "bin": True if auction_data["bin"] else False,
            "price": auction_data["starting_bid"] if auction_data["bin"] else auction_data["highest_bid_amount"],
            "count": nbt_data["Count"].value,
            "start": auction_data["start"],
            "end": auction_data["end"],
            "attributes": attributes
        }



        return uuid, item_id, new_data, attributes

    @time_func("Process time")
    async def __process_auctions(self, auctions: list, index: dict) -> None:
        for auction in auctions:
            uuid, item_id, auction_data, item_attributes = await self.__process_auction(auction)

            if uuid not in index[item_id]:  # If uuid not already in index
                index[item_id]["auctions"][uuid] = auction_data  # Add auction to index
            else:  # Shouldn't be possible
                raise Exception("Auction already in index")

            # Update attributes
            if item_attributes:
                update_attributes(index[item_id]["attributes"], item_attributes)

        self.__index = index

    @time_func("Remove ended")
    async def __remove_auctions(self, ended: list, index: dict) -> None:
        # remove ended from active auctions
        for uuid in ended:
            for item_id in index:  # for every item_id
                if uuid in index[item_id]:  # if auction item is this item type
                    del index[item_id][uuid]
                    break
            else:
                # first sync gets all current
                # next sync removes ended from those
                # repeat
                # should only occur when started and ended in between
                with open("ended.txt", "a") as f:
                    f.write(uuid + "\n")
                # print("ended not in db")

    @time_func("Update time")
    async def __update(self) -> None:
        print("\nStarting update")

        # variables
        new_index = self.__index.copy()

        async with aiohttp.ClientSession() as self.__session:
            self.__index = await self.__get_items()

            # shrink dicts before modifying
            ended: list = await self.__get_ended()
            await self.__remove_auctions(ended, new_index)

            # update dicts
            new: list = await self.__get_new(new_index)
            await self.__process_auctions(new, new_index)

    async def __controller(self) -> None:
        new_index = defaultdict(lambda: {"attributes": defaultdict(set), "auctions": defaultdict(dict)})

        async with aiohttp.ClientSession() as self.__session:
            self.__items = await self.__get_items()
            auctions: list = await self.__get_auctions()
            await self.__process_auctions(auctions, new_index)  # update master dicts to current

        # Output db for debug
        with open("samples/raw.json", "w") as f:
            json.dump(auctions, f, indent=2)
        with open("samples/index.json", "w") as f:
            json.dump(format_output(self.__index), f, indent=2)
        with open("samples/items.json", "w") as f:
            json.dump(self.__items, f, indent=2)

        # calibration
        current_time: float = time.time()
        next_update: float = (
                (self.__last_updated / 1000) + self.__INTERVAL + self.__OFFSET
        )
        difference: int = int(next_update - current_time)

        print(f"Sleeping for:\t{difference}s")
        await asyncio.sleep(difference)

        while True:
            await self.__update()

            print(f"Sleeping for:\t{self.__INTERVAL}s")
            await asyncio.sleep(self.__INTERVAL)

    def __start_loop(self):
        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        # loop.run_forever()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.__controller())

    def start(self):
        thread = Thread(target=self.__start_loop)
        thread.daemon = True  # If main thread closes so will it
        # thread.setDaemon(True)
        thread.start()

    def get_item_name(self, item_id: str) -> str:
        if item_id in self.__items:
            return self.__items[item_id]["name"]

        return " ".join([word.capitalize() for word in item_id.split("_")])

    def get_item_names(self):
        item_names = [self.get_item_name(item_id) for item_id in self.__index]

        return item_names

    def get_attributes(self, item_id: str):
        attributes = self.__index[item_id]["attributes"].keys()
        return attributes

    def get_attribute_values(self, item_id: str, attribute: str):
        values = self.__index[item_id]["attributes"][attribute]
        return values

    def get_auctions(self, item_id: str):
        auctions = self.__index[item_id]["auctions"].copy()
        return auctions

    def get_index(self):
        # For the love of god please don't use this
        # FOR DEBUGGING ONLY
        index = self.__index.copy()
        return index

