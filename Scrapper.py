import asyncio
import base64
import io
import time
from collections import defaultdict
from threading import Thread

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


class Scrapper:
    __URL: str = "https://api.hypixel.net/v2/skyblock/auctions?page={}"
    __ENDED_URL: str = "https://api.hypixel.net/v2/skyblock/auctions_ended"
    __INTERVAL: int = 60 - 1  # to recalibrate
    __OFFSET: int = 14  # to account for initial update times

    def __init__(self) -> None:
        self.__session: aiohttp.ClientSession
        self.__lock = asyncio.Lock()
        self.__last_updated: int = 0

        # auction data
        self.__index: dict[str: str] = {}
        self.__auctions: dict = defaultdict(dict)
        self.__enchantments: dict[str: set] = defaultdict(set)

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
    async def __get_new(self) -> list[dict]:
        new_auctions: list[dict] = []
        page_num: int = 0

        while True:
            url: str = self.__URL.format(page_num)
            page: dict = await self.__fetch_page(url)
            auctions: list[dict] = page["auctions"]

            for auction in auctions:
                # new auctions are prepended but non-bin auctions remain in the same index
                if auction["uuid"] in self.__index:
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

    def __process_enchantments(self, item_data: nbt.TAG_List) -> dict[str: int]:
        enchantments: dict = {}
        if not ("enchantments" in item_data["tag"]["ExtraAttributes"]):
            return enchantments

        raw_enchantments: nbt.TAG_Compound = item_data["tag"]["ExtraAttributes"]["enchantments"]
        enchantments = {enchant: level.value for enchant, level in raw_enchantments.iteritems()}

        # update enchantments master list
        for enchant, level in enchantments.items():
            self.__enchantments[enchant].add(level)

        return enchantments

    async def __process_auction(self, auction: dict) -> [str, dict]:
        item_bytes: str = auction["item_bytes"]
        decoded: bytes = base64.b64decode(item_bytes)
        fileobj: io.BytesIO = io.BytesIO(decoded)
        nbtfile: nbt.NBTFile = nbt.NBTFile(fileobj=fileobj)

        item_data: nbt.TAG_List = nbtfile["i"][0]
        item_id: str = item_data["tag"]["ExtraAttributes"]["id"].value
        auction_uuid: str = auction["uuid"]

        del auction["item_bytes"]
        del auction["uuid"]
        auction["item_data"] = item_data
        auction["enchantments"] = self.__process_enchantments(item_data)

        return item_id, auction_uuid, auction

    @time_func("Process time")
    async def __process_auctions(self, auctions: list[dict], index: dict[str: str] = {}, old_auctions: dict[str: dict] = defaultdict(dict)) -> None:
        async def update_dicts(new_index: dict[str: str], new_auctions: dict[str: dict]):
            async with self.__lock:
                self.__index = new_index
                self.__auctions = new_auctions

        # declaring variables
        item_id: str
        auction_data: dict
        auction_uuid: str

        # synchronous auction processing
        for auction in auctions:
            item_id, auction_uuid, auction_data = await self.__process_auction(auction)

            if auction_uuid in self.__index:
                raise Exception("double entry")

            index[auction_uuid] = item_id
            old_auctions[item_id][auction_uuid] = auction_data

        await update_dicts(index, old_auctions)

    @time_func("Remove ended")
    async def __remove_auctions(self, ended: list, index: dict[str: str], auctions: dict[str: dict]) -> None:
        # sync
        for auction_uuid in ended:
            # theoretically should always work after first run to sync
            if auction_uuid not in self.__index:
                print("ended not in db")
                continue

            item_id: str = self.__index[auction_uuid]

            del index[auction_uuid]
            del auctions[item_id][auction_uuid]

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
            new_index: dict[str: str] = self.__index.copy()
            new_auctions: dict[str: dict] = self.__auctions.copy()

            async with aiohttp.ClientSession() as self.__session:
                # shrink dicts before modifying
                ended: list[str] = await self.__get_ended()
                await self.__remove_auctions(ended, new_index, new_auctions)

                # update dicts
                new: list[dict] = await self.__get_new()
                await self.__process_auctions(new, new_index, new_auctions)

        async with aiohttp.ClientSession() as self.__session:
            auctions: list = await self.__get_auctions()
            await self.__process_auctions(auctions)  # update master dicts to current

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

    async def get_auctions(self):
        async with self.__lock:
            return self.__auctions.copy()
