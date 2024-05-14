import asyncio
from threading import Thread
import aiohttp
import time
import base64
from nbt import nbt
import io
import concurrent.futures
from collections import defaultdict


class Scrapper:
    URL: str = "https://api.hypixel.net/v2/skyblock/auctions?page={}"
    ENDED_URL: str = "https://api.hypixel.net/v2/skyblock/auctions_ended"
    INTERVAL: int = 60
    OFFSET: int = 7  # to account for scrape & update time

    def __init__(self) -> None:
        self.session: aiohttp.ClientSession = None
        self.total_pages: int

        # loop varaibles
        self.last_updated: int = 0
        self.index: dict[str:str] = {}
        self.auctions: dict = defaultdict(list)

    async def fetch_page(self, url: str, last_updated: int = 0) -> dict:
        resp: aiohttp.ClientResponse = await self.session.get(url)

        if resp.status == 200:
            page: dict = await resp.json()

            if not last_updated in (page["lastUpdated"], 0):
                print(f"Page: {page['page']+1} | Waiting 1s")

                await asyncio.sleep(1)
                page = await self.fetch_page(url, last_updated)

            # print(f"Page: {page['page']+1}")
            return page

        else:
            raise Exception(f"Error code: {resp.status}")

    async def get_auctions(self) -> [int, list[dict]]:
        tasks: list = []
        url: str

        self.session = aiohttp.ClientSession()

        url = self.URL.format(0)
        first_page: dict = await self.fetch_page(url)
        last_updated: int = first_page["lastUpdated"]
        self.total_pages = first_page["totalPages"]

        for page_num in range(1, self.total_pages):
            url = self.URL.format(page_num)
            tasks.append(self.fetch_page(url, last_updated))

        pages: list = [first_page] + list(
            await asyncio.gather(*tasks)
        )  # prepend first page
        total_auctions: list = [
            auction for page in pages for auction in page["auctions"]
        ]

        await self.session.close()
        return last_updated, total_auctions

    async def get_new(self):
        pass

    async def get_ended(self):
        self.session = aiohttp.ClientSession()

        page: dict = await self.fetch_page(self.ENDED_URL)
        auctions: list[dict] = page["auctions"]

        auction_ids = [auction["auction_id"] for auction in auctions]

        await self.session.close()

        return auction_ids

    async def process_auction(self, auction: dict) -> [str, dict]:
        item_bytes: str = auction["item_bytes"]
        decoded: bytes = base64.b64decode(item_bytes)
        fileobj: io.BytesIO = io.BytesIO(decoded)
        nbtfile: nbt.NBTFile = nbt.NBTFile(fileobj=fileobj)

        item_data: nbt.TAG_List = nbtfile["i"][0]
        item_id: str = item_data["tag"]["ExtraAttributes"]["id"]
        item_uuid: str = auction["uuid"]

        del auction["item_bytes"]
        auction["item_data"] = str(item_data)

        return item_id, item_uuid, auction

    async def process_auctions(self, auctions: list[dict]) -> None:
        start_time = time.time()

        item_id: str
        auction_data: dict
        item_uuid: str

        for auction in auctions:
            item_id, item_uuid, auction_data = await self.process_auction(auction)

            self.auctions[item_id].append(auction_data)
            self.index[item_uuid] = item_id

        print(f"Process time:\t{round(time.time() - start_time, 3)}s")

    async def controller(self) -> None:
        start_time: float = time.time()
        self.last_updated, total_auctions = await self.get_auctions()
        print(f"Time taken:\t{round(time.time() - start_time, 3)}s")

        await self.process_auctions(total_auctions)

        difference: float = time.time() - self.last_updated / 1000
        next_update: int = int((self.INTERVAL - difference) + self.OFFSET)

        print("Sleeping")
        await asyncio.sleep(next_update)

        while True:
            start_time: float = time.time()
            print("Starting auctions")

            await self.get_auctions()

            end_time: float = time.time()
            print(f"Time taken:\t{end_time-start_time}")

            await asyncio.sleep(self.INTERVAL)

    def start_loop(self):
        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        # loop.run_forever()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.controller())

    def start(self):
        thread = Thread(target=self.start_loop)
        thread.setDaemon(True)  # if main thread closes so will it
        thread.start()
