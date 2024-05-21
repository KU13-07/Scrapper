from statistics import mean, median, mode
import discord
import os
from Scrapper import Scrapper

TOKEN = os.environ["TOKEN"]

bot: discord.Bot = discord.Bot()
scrapper: Scrapper = Scrapper()


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


async def item_id_autocomplete(ctx: discord.AutocompleteContext):
    item_ids: list[str] = await scrapper.get_items()

    return item_ids


@bot.slash_command()
async def test(ctx: discord.ApplicationContext, item_name: str = discord.Option(
    autocomplete=discord.utils.basic_autocomplete(item_id_autocomplete),
    required=True
)):
    item_id = item_name.replace(" ", "_").upper()
    auctions = await scrapper.get_auctions()
    attributes = auctions[item_id]["attributes"]

    embed = discord.Embed(title=item_name, description="\n".join(attributes))
    await ctx.respond(embed=embed)


@bot.slash_command()
async def ahstats(
        ctx: discord.ApplicationContext,
        item_name: str = discord.Option(
            autocomplete=discord.utils.basic_autocomplete(item_id_autocomplete),
            required=True,
        ),
        bin: bool = discord.Option(bool, required=False),
):
    def format_output(num: float):  # god bless stack overflow
        magnitude: int = 0
        while abs(num) >= 1000:
            magnitude += 1
            num /= 1000

        return f"{round(num, 2)} {['', 'K', 'M', 'B'][magnitude]}"

    auctions: dict = await scrapper.get_auctions()
    item_id: str = item_name.replace(" ", "_").upper()
    filtered = [
        auction["starting_bid"] if (auction["bin"] or auction["highest_bid_amount"] == 0) else auction["highest_bid_amount"]
        for auction in auctions[item_id]["entries"].values()
        if (bin is None or auction["bin"] == bin)
    ]

    await ctx.defer()

    embed = discord.Embed(title=item_id)

    fields = {
        "Count": len(filtered),
        "Cheapest": min(filtered),
        "Expensive": max(filtered),
        "Mean": mean(filtered),
        "Median": median(filtered),
        "Mode": mode(filtered)
    }

    for name, value in fields.items():
        embed.add_field(name=name, value=format_output(value), inline=False)

    await ctx.respond(embed=embed)

if __name__ == "__main__":
    scrapper.start()
    bot.run(TOKEN)
