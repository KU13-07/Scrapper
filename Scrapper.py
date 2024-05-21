import asyncio
import base64
import io
import time
from collections import defaultdict
from threading import Thread
import json

import aiohttp
from nbt import nbt


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


def format_var(var):
    if isinstance(var, set):
        return list(var)
    elif isinstance(var, (dict, nbt.TAG_Compound)):
        if all(key in var for key in ("quality", "uuid")):  # if is gem with uuid
            return format_var(var["quality"])

        return {k: format_var(v) for k, v in var.items()}
    elif isinstance(var, nbt.TAG_Byte_Array):
        return str(var)
    elif isinstance(var, nbt.TAG):
        var = var.value
        if isinstance(var, str) and var.startswith("{"):
            return format_var(json.loads(var))
        return var

    return var


class Scrapper:
    __URL: str = "https://api.hypixel.net/v2/skyblock/auctions?page={}"
    __ENDED_URL: str = "https://api.hypixel.net/v2/skyblock/auctions_ended"
    __INTERVAL: int = 60 - 1  # to recalibrate
    __OFFSET: int = 14  # to account for initial update times

    __SKIP_ATTRIBUTES: tuple = ("id", "uuid", "timestamp", "bossId", "spawnedFor", "originTag", "fungi_cutter_mode")
    __SKIP_PROPERTIES: tuple = ("item_bytes", "uuid", "claimed", "category", "extra", "item_lore", "claimed_bidders", "last_updated", "claimed_bidders", "auctioneer", "profile_id", "coop")

    def __init__(self) -> None:
        self.__session: aiohttp.ClientSession
        self.__lock = asyncio.Lock()
        self.__last_updated: int = 0

        # auction data
        self.__index: dict[str: str]
        self.__auctions: dict
        self.__extras: dict[str: dict[str: set]]

    async def __fetch_page(self, url: str, update: bool = False) -> dict:
        resp: aiohttp.ClientResponse = await self.__session.get(url)

        if resp.status == 200:
            page: dict = await resp.json()
            last_updated: int = page["lastUpdated"]

            if (
                    last_updated != self.__last_updated
            ):  # if this ver is more recent (should be ~60s)
                if update:  # update is true
                    self.__last_updated = last_updated
                else:
                    if last_updated < self.__last_updated:  # waiting for page to update
                        print(f"URL: {url[36:]} | Waiting 1s")

                        # not good
                        await asyncio.sleep(1)
                        page = await self.__fetch_page(url)
                    else:
                        raise Exception("Should be possible. Page is more recent")
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
                page = await self.__fetch_page(url, update=update)

                # raise Exception("last_updated is same")

            # print(f"Page: {page['page']+1}")
            return page

        else:
            raise Exception(f"Error code: {resp.status}\n{await resp.read()}")

    @time_func("Fetching time")
    async def __get_auctions(self) -> list:
        tasks: list = []
        url: str

        # getting first page
        url = self.__URL.format(0)
        first_page: dict = await self.__fetch_page(url, update=True)
        total_pages: int = first_page["totalPages"]

        # preparing remaining pages
        for page_num in range(1, total_pages):
            url = self.__URL.format(page_num)
            tasks.append(self.__fetch_page(url))

        # getting remaining pages
        pages: list = [first_page] + list(
            await asyncio.gather(*tasks)
        )  # prepend first page
        auctions: list = [auction for page in pages for auction in page["auctions"]]
        return auctions

    @time_func("Fetch new")
    async def __get_new(self, index: dict[str: str]) -> list[dict]:
        new_auctions: list[dict] = []
        page_num: int = 0

        while True:
            url: str = self.__URL.format(page_num)
            page: dict = await self.__fetch_page(url)
            auctions: list[dict] = page["auctions"]

            for auction in auctions:
                # new auctions are prepended but non-bin auctions remain in the same index
                if auction["uuid"] in index:
                    if auction["bin"]:
                        return new_auctions
                else:  # prevent adding existing non-bin in new_auctions
                    new_auctions.append(auction)

            page_num += 1

    @time_func("Fetch ended")
    async def __get_ended(self):
        page: dict = await self.__fetch_page(self.__ENDED_URL, update=True)
        auctions: list[dict] = page["auctions"]

        auction_ids = [auction["auction_id"] for auction in auctions]

        return auction_ids

    async def __process_auction(self, auction: dict) -> [str, dict]:
        item_bytes: str = auction["item_bytes"]
        decoded: bytes = base64.b64decode(item_bytes)
        fileobj: io.BytesIO = io.BytesIO(decoded)
        nbtfile: nbt.NBTFile = nbt.NBTFile(fileobj=fileobj)

        item_data: nbt.TAG_List = nbtfile["i"][0]
        extra: nbt.TAG_Compound = item_data["tag"]["ExtraAttributes"]
        item_id: str = extra["id"].value
        auction_uuid: str = auction["uuid"]

        for entry in self.__SKIP_PROPERTIES:
            if entry in auction:
                del auction[entry]


        auction["count"] = item_data["Count"]
        auction["attributes"] = {
            k: v for k, v in extra.items() if (k not in self.__SKIP_ATTRIBUTES)
        }

        return item_id, auction_uuid, auction

    @time_func("Process time")
    async def __process_auctions(self, auctions: list[dict], index: dict[str: str] = {}, old_auctions: dict[str: dict] = defaultdict(lambda: {"attributes": set(), "entries": {}}), extras: dict[str: set] = defaultdict(set)) -> None:
        async def update_dicts(new_index: dict[str: str], new_auctions: dict[str: dict], new_extras: dict[str: set]):
            async with self.__lock:
                self.__index = new_index
                self.__auctions = new_auctions
                self.__extras = new_extras

        # declaring variables
        item_id: str
        auction_data: dict
        auction_uuid: str

        # synchronous auction processing
        def update_extras(path, attributes: dict):
            for attribute, value in attributes.items():
                if not isinstance(value, dict):
                    path[attribute].add(value)
                else:
                    if not isinstance(path[attribute], dict):
                        path[attribute] = defaultdict(set)

                    update_extras(path[attribute], value)

        for auction in auctions:
            item_id, auction_uuid, auction_data = await self.__process_auction(auction)

            index[auction_uuid] = item_id
            old_auctions[item_id]["entries"][auction_uuid] = auction_data

            # print(format_var(auction["attributes"]))
            update_extras(extras, format_var(auction["attributes"]))
            # for k, v in format_var(auction["attributes"]).items():
            #     if not isinstance(v, dict):
            #         extras[k].add(v)
            #     else:
            #         if not isinstance(extras[k], dict):
            #             extras[k] = defaultdict(set)
            #
            #         for a, b in v.items():
            #             if not isinstance(b, dict):
            #                 extras[k][a].add(b)
            #             else:
            #                 if not isinstance(extras[k][a], dict):
            #                     extras[k][a] = defaultdict(set)
            #
            #                 for c, d in v.items():
            #                     extras[k][a][c].add(d)


        await update_dicts(index, old_auctions, extras)

    @time_func("Remove ended")
    async def __remove_auctions(self, ended: list, index: dict[str: str], auctions: dict[str: dict]) -> None:
        # sync
        for auction_uuid in ended:
            # theoretically should always work after first run to sync
            if auction_uuid not in index:
                print("ended not in db")
                continue

            item_id: str = index[auction_uuid]

            del index[auction_uuid]
            del auctions[item_id]["entries"][auction_uuid]

        # no index
        """
        for auction_uuid in ended:
            for item_id in self.__auctions.keys():
                if (auction_uuid in self.__auctions[item_id]):
                    del self.__auctions[item_id][auction_uuid]
                    break
                """

    async def __controller(self) -> None:
        @time_func("Update time")
        async def update() -> None:
            print("\nStarting update")

            # variables
            new_index = self.__index.copy()
            new_auctions = self.__auctions.copy()
            new_extras = self.__extras.copy()

            async with aiohttp.ClientSession() as self.__session:
                # shrink dicts before modifying
                ended: list[str] = await self.__get_ended()
                await self.__remove_auctions(ended, new_index, new_auctions)

                # update dicts
                new: list[dict] = await self.__get_new(new_index)
                await self.__process_auctions(new, new_index, new_auctions, new_extras)

        async with aiohttp.ClientSession() as self.__session:
            auctions: list = await self.__get_auctions()
            await self.__process_auctions(auctions)  # update master dicts to current

        # output each major db variable
        for data_name in ["index", "auctions", "extras"]:
            with open(f"samples/{data_name}.json", "w", encoding="utf-8") as f:
                print(data_name)
                data = getattr(self, f"_Scrapper__{data_name}")
                json.dump(format_var(data), f, indent=2)

        # calibration
        current_time: float = time.time()
        next_update: float = (
                (self.__last_updated / 1000) + self.__INTERVAL + self.__OFFSET
        )
        difference: int = int(next_update - current_time)

        print(f"Sleeping for:\t{difference}s")
        await asyncio.sleep(difference)

        while True:
            await update()

            print(f"Sleeping for:\t{self.__INTERVAL}s")
            await asyncio.sleep(self.__INTERVAL)

    def __start_loop(self):
        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        # loop.run_forever()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.__controller())

    def start(self):
        thread = Thread(target=self.__start_loop)
        thread.daemon = True
        # thread.setDaemon(True)  # if main thread closes so will it
        thread.start()

    async def get_auctions(self) -> dict[str: dict]:
        async with self.__lock:
            return self.__auctions.copy()

    async def get_items(self) -> list[str]:
        def process_id(item_id: str) -> str:
            return " ".join(word.capitalize() for word in item_id.split("_"))

        async with self.__lock:
            return [process_id(item_id) for item_id in self.__auctions.keys()]

    async def get_extras(self) -> dict[str: dict[str: set]]:
        async with self.__lock:
            return self.__extras.copy()
