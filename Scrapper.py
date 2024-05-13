import asyncio
import aiohttp
import time

class Scrapper:
    URL = "https://api.hypixel.net/v2/skyblock/auctions?page={}"
    
    def __init__(self) -> None:
        self.session: aiohttp.ClientSession = None


    async def fetch_page(self, page_num: int = 0, last_updated: int = 0) -> dict:
        url: str = self.URL.format(page_num)
        resp: aiohttp.ClientResponse = await self.session.get(url)
    
        if (resp.status == 200):
            page: dict = await resp.json()
            
            if (not last_updated in (page["lastUpdated"], 0)):
                print(f"Page: {page_num} | Waiting 1s")
                
                await asyncio.sleep(1)
                page = await self.fetch_page(page_num, last_updated)

            #print(f"Page: {page_num}")
            return page
        
        else:
            raise Exception(f"Error code: {resp.status}")
        

    async def get_auctions(self) -> [int, list[dict]]:
        total_auctions: list = []
        tasks: list = []

        self.session = aiohttp.ClientSession()
        first_page: dict = await self.fetch_page()
        last_updated: int = first_page["lastUpdated"]
        total_pages: int = first_page["totalPages"]
        

        for page_num in range(1, total_pages):
            tasks.append(self.fetch_page(page_num, last_updated))
        
        pages: list = [first_page] + list(await asyncio.gather(*tasks)) # prepend first page
        
        for page in pages:
            auctions: list[dict] = first_page["auctions"]
            total_auctions.extend(auctions)
    
        await self.session.close()
        return last_updated, total_auctions
    
    async def debug(self):
        start: float = time.time()
        data = await self.get_auctions()
        
        time_taken: float = time.time() - start
        print(f"Time taken:\t{round(time_taken, 3)}s")
        
        return data
        



