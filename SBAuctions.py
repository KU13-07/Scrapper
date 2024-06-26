import asyncio
from collections import defaultdict
from threading import Thread
import json
from Processor import Processor
from Scrapper import Scrapper
from Utilities import *


class SBAuctions:
    __INTERVAL = 60 - 1  # to recalibrate
    __OFFSET = 14  # to account for initial update times

    def __init__(self):
        self.scrapper = Scrapper()

        self.__items = None
        self.__index = defaultdict(dict)
        self.__attributes = defaultdict(lambda: defaultdict(set))  # {"sword": {"lvl": (1, 2, 3...)}}

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

        async with self.scrapper:
            # update items index
            self.__items = await self.scrapper.get_items()

            # shrink dicts first to save memory
            ended: list = await self.scrapper.get_ended()
            await self.__remove_auctions(ended, self.__index)

            # update dicts
            auction_uuids = [auction for auctions in self.__index.values() for auction in auctions]
            new: list = await self.scrapper.get_new(auction_uuids)
            await Processor.process_auctions(new, self.__items, self.__index, self.__attributes)

    def __save(self, auctions: list):
        with open("samples/raw.json", "w") as f:
            json.dump(auctions, f, indent=2)
        with open("samples/items.json", "w") as f:
            json.dump(self.__items, f, indent=2)
        with open("samples/index.json", "w") as f:
            json.dump(format_output(self.__index), f, indent=2)
        with open("samples/attributes.json", "w") as f:
            json.dump(format_output(self.__attributes), f, indent=2)

    def __calc_delay(self) -> int:
        current_time: float = time.time()
        next_update: float = (
                (self.scrapper.get_last_updated() / 1000) + self.__INTERVAL + self.__OFFSET
        )

        return int(next_update - current_time)

    async def controller(self) -> None:
        async with self.scrapper:
            self.__items = await self.scrapper.get_items()
            auctions = await self.scrapper.get_auctions()
            await Processor.process_auctions(auctions, self.__items, self.__index, self.__attributes)

        # Output db for debug
        self.__save(auctions)

        # calibration
        difference = self.__calc_delay()
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
        loop.run_until_complete(self.controller())

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

    def get_category(self, item_id: str):
        if "category" in self.__items.get(item_id, ()):
            return self.__items[item_id]["category"]
        else:
            return item_id

    def get_attributes(self, item_id: str):
        category = self.get_category(item_id)
        attributes = self.__attributes[category].keys()

        return attributes

    def get_attribute_values(self, item_id: str, attribute: str):
        values = self.__index[item_id]["attributes"][attribute]
        return values

    def get_auctions(self, item_id: str):
        auctions = self.__index[item_id].copy()
        return auctions

    def get_index(self):
        # For the love of god please don't use this
        # FOR DEBUGGING ONLY
        index = self.__index.copy()
        return index


if __name__ == "__main__":
    auctions = SBAuctions()
    asyncio.run(auctions.controller())


