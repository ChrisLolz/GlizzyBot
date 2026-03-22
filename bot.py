import logging
import os
import discord
import aiohttp
import re
import asyncio
import time
from dotenv import load_dotenv
from g4f import Provider
from g4f.client import Client
from g4f.providers.any_provider import AnyProvider
handler = logging.StreamHandler()

g4f_client = Client()

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
IMAGE_GENERATION_COOLDOWN = int(os.getenv("IMAGE_GENERATION_COOLDOWN"))

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env file.")

if not IMAGE_GENERATION_COOLDOWN:
    IMAGE_GENERATION_COOLDOWN = 15

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

last_generation_time = 0
generation_lock = asyncio.Lock()
model="default"
provider=AnyProvider

async def check_image_url(url: str) -> bool:
    """Check if a URL points to an image by inspecting Content-Type header."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                content_type = resp.headers.get('Content-Type', '')
                return content_type.startswith('image/')
    except Exception:
        return False
    
async def generate_glizzy(image_url: str) -> str:
    """Generate a glizzified image based on the provided image URL."""
    global last_generation_time
    async with generation_lock:
        elapsed = time.time() - last_generation_time
        if elapsed < IMAGE_GENERATION_COOLDOWN:
            print(f"Rate limit in effect. Waiting for {IMAGE_GENERATION_COOLDOWN - elapsed:.2f} seconds.", flush=True)
            await asyncio.sleep(IMAGE_GENERATION_COOLDOWN - elapsed)

        print(f"Generating glizzy for image: {image_url}")
        response = await g4f_client.images.async_create_variation(
            image=image_url,
            prompt="Make everyone or everything in the image eat a hot dog",
            model="qwen3.5-plus",
            provider=Provider.Qwen,
            response_format="url"
        )
        last_generation_time = time.time()
    return response.data[0].url

@tree.command(name="models", description="List available models")
async def models_command(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://raw.githubusercontent.com/maruf009sultan/g4f-working/refs/heads/main/working/working_results.txt") as resp:
            if resp.status == 200:
                text = await resp.text()
                model_list = ", ".join(line.split("|")[1].strip() for line in text.splitlines() if line.strip())
            else:
                model_list = "Failed to fetch model list."
    embed = discord.Embed(title="Available Models", description=model_list)
    await interaction.response.send_message(embed=embed)

@tree.command(name="providers", description="List available providers")
async def providers_command(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://raw.githubusercontent.com/maruf009sultan/g4f-working/refs/heads/main/working/working_results.txt") as resp:
            if resp.status == 200:
                text = await resp.text()
                provider_list = set([line.split("|")[0].strip() for line in text.splitlines() if line.strip()])
            else:
                provider_list = "Failed to fetch provider list."
    embed = discord.Embed(title="Available Providers", description=", ".join(provider_list))
    await interaction.response.send_message(embed=embed)

@tree.command(name="fulllist", description="List available providers and their models")
async def fulllist_command(interaction: discord.Interaction):
    await interaction.response.send_message("https://raw.githubusercontent.com/maruf009sultan/g4f-working/refs/heads/main/working/working_results.txt")

@tree.command(name="info", description="Show current provider and model")
async def info_command(interaction: discord.Interaction):
    await interaction.response.send_message(f"Current provider: {provider.__name__}\nCurrent model: {model}")

@tree.command(name="setprovider", description="Set the provider for text responses")
async def setprovider_command(interaction: discord.Interaction, provider_name: str):
    global provider
    if provider_name == AnyProvider or provider_name in Provider.__dict__:
        provider = getattr(Provider, provider_name) if provider_name != AnyProvider else AnyProvider
        await interaction.response.send_message(f"Provider set to: {provider_name}")
    else:
        await interaction.response.send_message(f"Provider '{provider_name}' not found. Use /providers to see available providers.")

@tree.command(name="setmodel", description="Set the model for text responses")
async def setmodel_command(interaction: discord.Interaction, model_name: str):
    global model
    model = model_name
    await interaction.response.send_message(f"Model set to: {model_name}")

@client.event
async def on_ready() -> None:
    oauth_url = discord.utils.oauth_url(client.user.id, permissions=discord.Permissions(permissions=8), scopes=["bot", "applications.commands"])
    print(f"Invite the bot using this URL: {oauth_url}")
    await tree.sync()
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if client.user in message.mentions:
        try:
            response = g4f_client.chat.completions.create(
                model=model if model != "default" else None,
                provider=provider,
                image=message.attachments[0].url if message.attachments else None,
                messages=[{"role": "user", "content": message.content.replace(f"<@{client.user.id}>", "").strip()}],
            )
            content = response.choices[0].message.content
            for i in range(0, len(content), 2000):
                await message.reply(content[i:i+2000])
        except Exception as e:
            await message.reply(f"Error generating response: {str(e)}")
        return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                glizzy_url = await generate_glizzy(attachment.url)
                await message.reply(glizzy_url)
        return
    
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, message.content)

    for url in urls:
        glizzy_url = await generate_glizzy(url)
        await message.reply(glizzy_url)
        return

client.run(DISCORD_TOKEN, log_handler=handler, log_level=logging.INFO)
