import logging
import os
import discord
from dotenv import load_dotenv
from g4f.client import Client
from g4f.Provider import Qwen

handler = logging.StreamHandler()

g4f = Client()

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env file.")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready() -> None:
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                response = await g4f.images.async_create_variation(
                    image=attachment.url,
                    prompt="Make the individual(s) in the image eat a hot dog",
                    model="qwen3.5-plus",
                    provider=Qwen,
                    response_format="url"
                )
                await message.reply(response.data[0].url)

client.run(DISCORD_TOKEN, log_handler=handler, log_level=logging.INFO)
