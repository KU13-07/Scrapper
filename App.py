from statistics import mean, median, mode
import discord
import asyncio
import time
import math
from Scrapper import Scrapper

TOKEN = ""

bot: discord.Bot = discord.Bot()
scrapper: Scrapper = Scrapper()


@bot.event
async def on_ready():
    scrapper.start()
    print(f"We have logged in as {bot.user}")


async def item_id_autocomplete(ctx: discord.AutocompleteContext):
    auctions: dict = await scrapper.get_auctions()
    item_ids: list = auctions.keys()

    return item_ids


@bot.slash_command()
async def test(
    ctx: discord.ApplicationContext,
    item_id: str = discord.Option(
        autocomplete=discord.utils.basic_autocomplete(item_id_autocomplete),
        required=True,
    ),
    bin: bool = discord.Option(bool, required=False),
):
    auctions: dict[list] = await scrapper.get_auctions()
    filtered = [
        auction["starting_bid"]
        for auction in auctions[item_id].values()
        if (bin == None or auction["bin"] == bin)
    ]
    
    await ctx.defer()

    embed = discord.Embed(title=item_id)

    embed.add_field(name="Count", value=f"{len(filtered):,}", inline=False)
    embed.add_field(name="Cheapest", value=f"{min(filtered):,}", inline=False)
    embed.add_field(name="Expensive", value=f"{max(filtered):,}", inline=False)
    embed.add_field(name="Mean", value=f"{int(mean(filtered)):,}", inline=False)
    embed.add_field(name="Median", value=f"{int(median(filtered)):,}", inline=False)
    embed.add_field(name="Mode", value=f"{int(mode(filtered)):,}", inline=False)

    await ctx.respond(embed=embed)

@bot.slash_command()
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f"hi")

if __name__ == "__main__":
    bot.run(TOKEN)