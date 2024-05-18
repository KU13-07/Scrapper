import asyncio
from threading import Thread
import aiohttp
import time
import base64
from nbt import nbt
import io
import concurrent.futures
from collections import defaultdict
import json


class Scrapper:
    __URL: str = "https://api.hypixel.net/v2/skyblock/auctions?page={}"
    __ENDED_URL: str = "https://api.hypixel.net/v2/skyblock/auctions_ended"
    __INTERVAL: int = 60 - 1  # to recalibrate
    __OFFSET: int = 14  # to account for initial update times

    def __init__(self) -> None:
        self.__session: aiohttp.ClientSession = None
        self.__lock = asyncio.Lock()

        # loop varaibles
        self.__last_updated: int = 0
        self.__index: dict[str:str] = {}
        self.__auctions: dict = defaultdict(dict)

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

    async def __get_new(self) -> list[dict]:
        new_auctions: list[dict] = []
        page_num: int = 0

        while True:
            url: str = self.__URL.format(page_num)
            page: dict = await self.__fetch_page(url, update=True)
            auctions: list[dict] = page["auctions"]

            for auction in auctions:
                # new auctions are prepended but non-bin auctions remain in the same index
                if auction["uuid"] in self.__index:
                    if auction["bin"] == True:
                        return new_auctions
                else:  # prevent adding existing non-bin in new_auctions
                    new_auctions.append(auction)

            page_num += 1

    async def __get_ended(self):
        page: dict = await self.__fetch_page(self.__ENDED_URL)
        auctions: list[dict] = page["auctions"]

        auction_ids = [auction["auction_id"] for auction in auctions]

        return auction_ids

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
        auction["item_data"] = str(item_data)

        return item_id, auction_uuid, auction

    async def __process_auctions(self, auctions: list[dict]) -> None:
        # declaring variables
        item_id: str
        auction_data: dict
        auction_uuid: str

        # synchronous auction processing
        for auction in auctions:
            item_id, auction_uuid, auction_data = await self.__process_auction(auction)

            if auction_uuid in self.__index:
                raise Exception("double entry")

            self.__auctions[item_id][auction_uuid] = auction_data
            self.__index[auction_uuid] = item_id

    async def __remove_auctions(self, ended: list) -> None:
        # sync
        for auction_uuid in ended:
            # theoretically should always work after first run to sync
            if not auction_uuid in self.__index:
                continue

            item_id: str = self.__index[auction_uuid]

            del self.__auctions[item_id][auction_uuid]
            del self.__index[auction_uuid]

        # no index
        """
        for auction_uuid in ended:
            for item_id in self.__auctions.keys():
                if (auction_uuid in self.__auctions[item_id]):
                    del self.__auctions[item_id][auction_uuid]
                    break
                """

    async def __controller(self) -> None:
        async with self.__lock:
            self.__session = aiohttp.ClientSession()

            start_time: float = time.time()
            auctions: list = await self.__get_auctions()
            print(f"Fetching time:\t{round(time.time() - start_time, 3)}s")

            start_time = time.time()
            await self.__process_auctions(auctions)
            print(f"Process time:\t{round(time.time() - start_time, 3)}s")

            await self.__session.close()

        current_time = time.time()
        next_update: float = (
            (self.__last_updated / 1000) + self.__INTERVAL + self.__OFFSET
        )
        difference: int = int(next_update - current_time)

        print(f"Sleeping for:\t{difference}s")
        await asyncio.sleep(difference)

        while True:
            async with self.__lock:
                print("\n\nStarting update")
                start_time: float = time.time()
                self.__session = aiohttp.ClientSession()

                func_time: float = time.time()
                new: list[dict] = await self.__get_new()
                print(f"Fetch new:\t{round(time.time() - func_time, 3)}s")

                func_time: float = time.time()
                await self.__process_auctions(new)
                print(f"Update dict:\t{round(time.time() - func_time, 3)}s")

                func_time: float = time.time()
                ended: list[str] = await self.__get_ended()
                print(f"Fetch ended:\t{round(time.time() - func_time, 3)}s")

                func_time: float = time.time()
                await self.__remove_auctions(ended)
                print(f"Remove ended:\t{round(time.time() - func_time, 3)}s")

                await self.__session.close()
                print(f"Time taken:\t{round(time.time() - start_time, 3)}s")

            print(f"Sleeping for:\t{self.__INTERVAL}s")
            await asyncio.sleep(self.__INTERVAL)

    def __start_loop(self):
        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        # loop.run_forever()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.__controller())

    def start(self):
        thread = Thread(target=self.__start_loop)
        thread.setDaemon(True)  # if main thread closes so will it
        thread.start()

    async def get_auctions(self):
        async with self.__lock:
            return self.__auctions.copy()