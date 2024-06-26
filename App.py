import discord
import os
from SBAuctions import SBAuctions

TOKEN = os.environ["TOKEN"]

bot: discord.Bot = discord.Bot(intents=discord.Intents.all())
auctions = SBAuctions()


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


@bot.slash_command()
async def reload(ctx: discord.ApplicationContext):
    bot.reload_extension("cogs.auctions")
    await ctx.respond("Done")

if __name__ == "__main__":
    auctions.start()

    bot.scrapper = auctions
    bot.load_extension("cogs.auctions")

    bot.run(TOKEN)
