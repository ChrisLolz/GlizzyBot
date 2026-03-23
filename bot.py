import base64
import logging
import os
import discord
import aiohttp
import re
import asyncio
import time
from PIL import Image
from io import BytesIO
from discord.ext import commands
from dotenv import load_dotenv
from g4f import Provider
from g4f.client import AsyncClient
from g4f.providers.any_provider import AnyProvider
import g4f.debug
import zendriver
import tempfile
g4f.debug.logging = True

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
IMAGE_GENERATION_COOLDOWN = int(os.getenv("IMAGE_GENERATION_COOLDOWN"), 15)

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env file.")

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!', intents=intents)
tree = client.tree

last_generation_time = 0
generation_lock = asyncio.Lock()
model=os.getenv("MODEL", "default")
provider=os.getenv("PROVIDER")
image_model=os.getenv("IMAGE_MODEL")
image_provider=os.getenv("IMAGE_PROVIDER")
glizzy=True

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
    global provider, image_provider
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
    global model, image_model
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
async def edit_command(interaction: discord.Interaction, attachment: discord.Attachment, prompt: str):
    if not await check_image_url(attachment.url):
        await interaction.response.send_message("The provided URL does not point to a valid image.")
        return
    await interaction.response.defer()
    try:
        image = await edit_image(attachment.url, prompt)
        await interaction.followup.send(image)
    except Exception as e:
        await interaction.followup.send(f"Error editing image: {str(e)}")

@tree.command(name="reset", description="Reset provider and model to default")
async def reset_command(interaction: discord.Interaction):
    global provider, model, image_model, image_provider
    provider = None
    model = "default"
    image_provider = None
    image_model = None
    await interaction.response.send_message("Provider and model reset to default.")

@tree.command(name="generate_image", description="Generate an image from a prompt")
async def generate_image_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        response = await g4f_client.images.generate(
            model=image_model if image_model and image_model != "default" else None,
            provider=image_provider,
            prompt=prompt,
            response_format="url"
        )
        await interaction.followup.send(response.data[0].url)
    except Exception as e:
        await interaction.followup.send(f"Error generating image: {str(e)}")

@client.command()
async def kirkify(ctx):
    try:
        print("Kirkifying image...")
        async with aiohttp.ClientSession() as session:
            if ctx.message.attachments:
                image_url = ctx.message.attachments[0].url
            else:
                found_url = re.search(r'(https?://\S+)', ctx.message.content)
                if found_url:
                    image_url = found_url.group(0)
                else:
                    await ctx.send("Please provide a valid image URL or attach an image.")
                    return

            async with session.get(image_url) as resp:
                if resp.status != 200:
                    await ctx.reply(f"Failed to download source image: {resp.status}")
                    return
                source_bytes = await resp.read()

        img = Image.open(BytesIO(source_bytes)).convert("RGBA")
        png_buffer = BytesIO()
        img.save(png_buffer, format="PNG")
        png_bytes = png_buffer.getvalue()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(png_bytes)
            tmp_path = tmp.name

        async def on_dialog(dialog):
            print(f"Alert: {dialog.message}")
            await page.send(zendriver.cdp.page.handle_java_script_dialog(accept=True))

        for attempt in range(3):
            try:
                browser = await zendriver.start(headless=True)
                page = await browser.get("https://kirkify.wtf/")
                page.add_handler(zendriver.cdp.page.JavascriptDialogOpening, on_dialog)
                await asyncio.sleep(3)
                file_input = await page.select('input[type="file"]')
                await file_input.send_file(tmp_path)
                await asyncio.sleep(1.5)
                button = await page.find("generate")
                await button.click()
                for _ in range(3):
                    try:
                        img_element = await page.select('img[alt="kirked"]')
                        if img_element:
                            break
                    except Exception:
                        pass
                src_data = img_element.get("src")
                if src_data.startswith("data:image/png;base64,"):
                    img_data = base64.b64decode(src_data.split(",")[1])
                    await browser.stop()
                    im = Image.open(BytesIO(img_data)).convert("RGB")
                    im.thumbnail((1280, 1280))
                    compressed = BytesIO()
                    im.save(compressed, format="JPEG", quality=75, optimize=True)
                    img_data = compressed.getvalue()
                    await ctx.reply(file=discord.File(BytesIO(img_data), filename="kirkified.png"))
                    return
                else:
                    raise Exception("Unexpected image source format.")
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                await browser.stop()
        raise Exception("Try again later.")

    except Exception as e:
        await ctx.reply(f"Error processing image: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@tree.command(name="glizzy", description="Toggle glizzification of images")
async def glizzy_command(interaction: discord.Interaction):
    global glizzy
    glizzy = not glizzy
    await interaction.response.send_message(f"Glizzification turned {'on' if glizzy else 'off'}.")

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
    embed.add_field(name="/glizzy", value="Toggle glizzification of images. When on, any image attached or linked in a user message will be glizzified.", inline=False)
    embed.add_field(name="Image editing",value="Attach an image and '@GlizzyBot !edit [prompt]' to edit the image.", inline=False)
    embed.add_field(name="!kirkify", value="Attach an image or provide an image URL to kirkify it.", inline=False)
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

    await client.process_commands(message)
    if message.content.startswith("!kirkify"):
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

    if glizzy:
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
