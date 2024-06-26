import aiohttp
import asyncio
from Utilities import time_func


class Scrapper:
    __API_URL = "https://api.hypixel.net/v2/"
    __URL = __API_URL + "skyblock/auctions?page={}"
    __ENDED_URL = __API_URL + "skyblock/auctions_ended"
    __ITEMS_URL = __API_URL + "resources/skyblock/items"
    __DELAY = 2  # re-fetch delay

    def __init__(self):
        self.__session = None
        self.__last_updated = 0

    async def __fetch(self, url: str, update: bool = False, override: bool = False) -> dict:
        resp: aiohttp.ClientResponse = await self.__session.get(url)

        if resp.status != 200:
            raise Exception(f"Unable to reach page.\nError code: {resp.status}\n{url}\n{await resp.read()}")

        page: dict = await resp.json()
        last_updated: int = page["lastUpdated"]

        if override:
            return page

        if last_updated > self.__last_updated:  # if this ver is more recent (should be ~60s)
            if update:
                self.__last_updated = last_updated
            else:
                print(self.__last_updated, last_updated)
                raise Exception("Page is more recent. This shouldn't be possible (Unless startup).")
        elif not (last_updated == self.__last_updated and not update):  # Waiting for update
            print(f"URL: {url[36:]} | Waiting {self.__DELAY}s")
            await asyncio.sleep(self.__DELAY)
            page = await self.__fetch(url, update=update)

        return page

    @time_func("Fetch items index")
    async def get_items(self) -> dict:
        url = self.__ITEMS_URL
        resp = await self.__fetch(url, override=True)  # Different schedule

        items = {}
        for item in resp["items"]:
            item_id = item.pop("id")
            items[item_id] = item

        return items

    @time_func("Fetch all auctions")
    async def get_auctions(self) -> list:
        url = self.__URL.format(0)
        first_page = await self.__fetch(url, update=True)
        total_pages: int = first_page["totalPages"]

        # preparing remaining pages tasks
        tasks = []
        for page_num in range(1, total_pages):
            url = self.__URL.format(page_num)
            tasks.append(self.__fetch(url))

        # get remaining pages
        pages: list = [first_page] + list(await asyncio.gather(*tasks))
        auctions = [auction for page in pages for auction in page["auctions"]]
        return auctions

    @time_func("Fetch new auctions")
    async def get_new(self, auction_uuids: list) -> list:
        new_auctions = []
        page_num = 0

        while True:
            url = self.__URL.format(page_num)
            page = await self.__fetch(url)
            auctions: list = page["auctions"]

            for auction in auctions:
                # new auctions are prepended but non-bin auctions remain in the same position in api
                if auction["uuid"] in auction_uuids:
                    if auction["bin"]:  # found first real repeating
                        return new_auctions
                else:
                    new_auctions.append(auction)

            page += 1

    @time_func("Fetch ended")
    async def get_ended(self) -> list:
        page = await self.__fetch(self.__ENDED_URL, update=True)
        auctions: list = page["auctions"]

        auction_ids = [auction["auction_id"] for auction in auctions]
        return auction_ids

    def get_last_updated(self) -> int:
        return self.__last_updated

    async def __aenter__(self):
        self.__session = aiohttp.ClientSession()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.__session.close()

