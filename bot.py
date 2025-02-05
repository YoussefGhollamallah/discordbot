import discord
import os
from dotenv import load_dotenv
load_dotenv()

print("Lancement du bot...")

bot = discord.Client(intents=discord.Intents.all())


@bot.event
async def on_ready():
    print("Bot connecté")

@bot.event
async def on_message(message: discord.Message):
    if message.content.lower() == "bonjour" or message.content.lower() == "salut":
        channel = message.channel
        author = message.author
        await channel.send("Salut ! " + author.mention + )



bot.run(os.getenv("DISCORD_ENV"))

