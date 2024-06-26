import base64
import io
from nbt import nbt
from collections import defaultdict
from Utilities import *


class Processor:
    IGNORE_ATTRS = ("uuid", "timestamp", "bossId", "spawnedFor", "recipient_id")

    @classmethod
    def nbt_to_dict(cls, data: nbt.TAG):
        match type(data):
            case nbt.TAG_Compound:
                result = {
                    k: cls.nbt_to_dict(data[k])
                    for k in data
                }
            case nbt.TAG_List:
                result = [
                    cls.nbt_to_dict(item)
                    for item in data
                ]
            case nbt.TAG_Byte_Array:
                result = str(data.value)
            case _:
                result = data.value
        return result

    @classmethod
    def flatten_gems(cls, data) -> dict:
        return str(data)

    @classmethod
    def decode(cls, raw_bytes: str) -> tuple[str, int, dict]:
        decoded = base64.b64decode(raw_bytes)
        file_obj = io.BytesIO(decoded)
        nbt_data: nbt.TAG_Compound = nbt.NBTFile(fileobj=file_obj)["i"][0]

        extras = nbt_data["tag"]["ExtraAttributes"]
        item_id = extras.pop("id").value
        count = nbt_data.pop("Count").value
        for k in cls.IGNORE_ATTRS:
            if k in extras:
                del extras[k]

        extras = cls.nbt_to_dict(extras)
        if "gems" in extras:
            extras["gems"] = cls.flatten_gems(extras["gems"])

        return item_id, count, extras

    @classmethod
    async def process_item(cls, auction: dict) -> tuple[str, str]:
        uuid = auction.pop("uuid")

        raw_bytes = auction.pop("item_bytes")
        item_id, count, auction["extras"] = cls.decode(raw_bytes)

        auction["count"] = count

        return uuid, item_id

    @classmethod
    def update_attributes(cls, path, attr):
        for k, v in attr.items():
            match v:
                case dict():
                    if not isinstance(path[k], dict):
                        path[k] = defaultdict(set)

                    cls.update_attributes(path[k], v)
                case list():
                    if any(isinstance(item, dict) for item in v):
                        if not isinstance(path[k], list):
                            path[k] = list(path[k])
                        path[k].extend(v)
                    elif isinstance(path[k], list):
                        path[k].extend(v)
                    else:
                        path[k].update(v)
                case _:
                    path[k].add(v)

    @classmethod
    def get_category(cls, item_id: str, items):
        if "category" in items.get(item_id, ()):
            return items[item_id]["category"]
        else:
            return item_id

    @classmethod
    @time_func("Process time")
    async def process_auctions(cls, auctions: list, items: dict, index: dict, attributes: dict):
        for auction in auctions:
            uuid, item_id = await cls.process_item(auction)
            index[item_id][uuid] = auction  # add auction to index

            if not auction["extras"]:
                continue

            category = cls.get_category(item_id, items)
            cls.update_attributes(attributes[category], auction["extras"])

