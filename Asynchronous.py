import asyncio
import aiohttp
import tracemalloc
import timeit

async def get_auctions() -> [int, list[dict]]:
    total_auctions: list = []
    last_updated: int = 0 # exceeds 4 byte limit

    async with aiohttp.ClientSession() as session:
        page_num: int = 0
        url = "https://api.hypixel.net/v2/skyblock/auctions?page={}"

        while True:
            resp: aiohttp.ClientResponse = await session.get(url.format(page_num))
            if (resp.status == 200):
                page: dict = await resp.json()
            
                if (last_updated in (0, page["lastUpdated"])): # if last_updated is 0 or current
                    if (last_updated == 0):
                        last_updated = page["lastUpdated"]

                    auctions: list[dict] = page["auctions"]
                    total_auctions.extend(auctions)

                    page_num += 1
                    if (page_num == page["totalPages"]):
                        return last_updated, total_auctions
                    
                    print(f"Page: {page_num}")
                else:
                    print("Mismatch update times!")
            else:
                print("Unable to get url")

async def main():
    last_updated, auctions = await get_auctions()
    

if __name__ == "__main__":
    run_time = timeit.timeit(lambda: asyncio.run(main()), number=5)
    print(run_time)


