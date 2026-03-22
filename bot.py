import logging
import os
import discord
import aiohttp
import re
import asyncio
import time
from dotenv import load_dotenv
from g4f import Provider
from g4f.client import AsyncClient
from g4f.providers.any_provider import AnyProvider
handler = logging.StreamHandler()

g4f_client = AsyncClient()

GITHUB_COPILOT = os.getenv("GITHUB_COPILOT")
if GITHUB_COPILOT=="true":
    if Provider.GithubCopilot.has_credentials():
       print("Logged in to Github Copilot successfully.") 
    else:
        asyncio.run(Provider.GithubCopilot.login())

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
provider=None
image_model="flux"
image_provider=None

async def check_image_url(url: str) -> bool:
    """Check if a URL points to an image by inspecting Content-Type header."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                content_type = resp.headers.get('Content-Type', '')
                return content_type.startswith('image/')
    except Exception:
        return False

async def edit_image(image_url: str, prompt: str) -> str:
    """Edit an image based on the provided image URL."""
    global last_generation_time
    async with generation_lock:
        elapsed = time.time() - last_generation_time
        if elapsed < IMAGE_GENERATION_COOLDOWN:
            print(f"Rate limit in effect. Waiting for {IMAGE_GENERATION_COOLDOWN - elapsed:.2f} seconds.", flush=True)
            await asyncio.sleep(IMAGE_GENERATION_COOLDOWN - elapsed)

        print(f"Editing image: {image_url}")
        response = await g4f_client.images.async_create_variation(
            image=image_url,
            prompt=prompt,
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

@tree.command(name="full_list", description="List available providers and their models")
async def fulllist_command(interaction: discord.Interaction):
    await interaction.response.send_message("https://raw.githubusercontent.com/maruf009sultan/g4f-working/refs/heads/main/working/working_results.txt")

@tree.command(name="info", description="Show current provider and model")
async def info_command(interaction: discord.Interaction):
    provider_info = provider if provider else "Default"
    model_info = model if model != "default" else "Default"
    image_provider_info = image_provider if image_provider else "Default"
    image_model_info = image_model if image_model != "default" else "Default"
    embed = discord.Embed(title="Current Configuration", description=f"**Text Provider:** {provider_info}\n**Text Model:** {model_info}\n**Image Provider:** {image_provider_info}\n**Image Model:** {image_model_info}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="set_provider", description="Set the provider for text responses")
async def setprovider_command(interaction: discord.Interaction, provider_name: str, type: str = "text"):
    global provider
    if type not in ["text", "image"]:
        await interaction.response.send_message("Invalid type. Use 'text' or 'image'.")
        return

    if provider_name == AnyProvider or provider_name in Provider.__dict__:
        if type == "text":
            provider = getattr(Provider, provider_name) if provider_name != AnyProvider else AnyProvider
        elif type == "image":
            image_provider = getattr(Provider, provider_name) if provider_name != AnyProvider else AnyProvider
        await interaction.response.send_message(f"Provider set to: {provider_name}")
    else:
        await interaction.response.send_message(f"Provider '{provider_name}' not found. Use /providers to see available providers.")

@tree.command(name="set_model", description="Set the model for text responses")
async def setmodel_command(interaction: discord.Interaction, model_name: str, type: str = "text"):
    global model
    if type not in ["text", "image"]:
        await interaction.response.send_message("Invalid type. Use 'text' or 'image'.")
        return
    if type == "text":
        model = model_name
    elif type == "image":
        image_model = model_name
    await interaction.response.send_message(f"Model set to: {model_name}")

@tree.command(name="edit_url", description="Edit an image with a url")
async def edit_command(interaction: discord.Interaction, image_url: str, prompt: str):
    if not await check_image_url(image_url):
        await interaction.response.send_message("The provided URL does not point to a valid image.")
        return
    await interaction.response.defer()
    try:
        image = await edit_image(image_url, prompt)
        await interaction.followup.send(image)
    except Exception as e:
        await interaction.followup.send(f"Error editing image: {str(e)}")

@tree.command(name="edit_image", description="Edit an image with an image")
async def edit_command(interaction: discord.Interaction, attachement: discord.Attachment, prompt: str):
    if not await check_image_url(attachement.url):
        await interaction.response.send_message("The provided URL does not point to a valid image.")
        return
    await interaction.response.defer()
    try:
        image = await edit_image(attachement.url, prompt)
        await interaction.followup.send(image)
    except Exception as e:
        await interaction.followup.send(f"Error editing image: {str(e)}")

@tree.command(name="reset", description="Reset provider and model to default")
async def reset_command(interaction: discord.Interaction):
    global provider, model
    provider = None
    model = "default"
    image_provider = None
    image_model = "flux"
    await interaction.response.send_message("Provider and model reset to default.")

@tree.command(name="generate_image", description="Generate an image from a prompt")
async def generate_image_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        response = await g4f_client.images.generate(
            model=image_model,
            provider=image_provider,
            prompt=prompt,
            response_format="url"
        )
        await interaction.followup.send(response.data[0].url)
    except Exception as e:
        await interaction.followup.send(f"Error generating image: {str(e)}")

@tree.command(name="help", description="Show help message")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="GlizzyBot Help", 
        description=
        """
        Author: Christopher Lo
        Mention the bot with a message to get a response.
        Use the following commands for more options:
        """
    )
    embed.add_field(value="Attach an image and '@GlizzyBot !edit [prompt]' to edit the image.", inline=False)
    embed.add_field(name="/models", value="List available models", inline=False)
    embed.add_field(name="/providers", value="List available providers", inline=False)
    embed.add_field(name="/full_list", value="List available providers and their compatible models", inline=False)
    embed.add_field(name="/info", value="Show current provider and model", inline=False)
    embed.add_field(name="/set_provider", value="Set the provider for text responses", inline=False)
    embed.add_field(name="/set_model", value="Set the model for text responses", inline=False)
    embed.add_field(name="/reset", value="Reset provider and model to default", inline=False)
    embed.add_field(name="/edit_url", value="Edit an image with a url. Alternative command for @GlizzyBot !edit", inline=False)
    embed.add_field(name="/edit_image", value="Edit an image with an attached image. Alternative command for @GlizzyBot !edit", inline=False)
    await interaction.response.send_message(embed=embed)

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
        async with message.channel.typing():
            try:
                if message.attachments and "!edit" in message.content.lower():
                    async with asyncio.timeout(120):
                        image = await edit_image(message.attachments[0].url, message.content.replace(f"<@{client.user.id}>", "").replace("!edit", "").strip())
                        await message.reply(image)
                else:
                    async with asyncio.timeout(60):
                        response = g4f_client.chat.completions.create(
                                stream=True,
                                model=model if model != "default" else None,
                                provider=provider,
                                image=message.attachments[0].url if message.attachments else None,
                                messages=[{"role": "user", "content": message.content.replace(f"<@{client.user.id}>", "").strip()}],
                        )
                        content = ""
                        async for chunk in response:
                            if chunk.choices[0].delta.content:
                                content += chunk.choices[0].delta.content
                        for i in range(0, len(content), 2000):
                            await message.reply(content[i:i+2000])
            except asyncio.TimeoutError:
                await message.reply("Sorry, the request timed out. Please try again.")
            except Exception as e:
                await message.reply(f"Error generating response: {str(e)}")
        return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                glizzy_url = await edit_image(attachment.url, "Make everyone or everything in the image eat a hot dog")
                await message.reply(glizzy_url)
        return
    
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, message.content)

    for url in urls:
        if await check_image_url(url):
            glizzy_url = await edit_image(url, "Make everyone or everything in the image eat a hot dog")
            await message.reply(glizzy_url)
            return

client.run(DISCORD_TOKEN, log_handler=handler, log_level=logging.INFO)
