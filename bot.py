import logging
import os
import discord
import aiohttp
import re
import asyncio
import time
from PIL import Image, ImageSequence
from io import BytesIO
from discord.ext import commands
from dotenv import load_dotenv
from g4f import Provider
from g4f.client import AsyncClient
from g4f.providers.any_provider import AnyProvider
import g4f.debug
import cv2
import insightface
import numpy as np

async def ensure_inswapper_model() -> None:
    if not os.path.exists("models/inswapper_128.onnx"):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://github.com/deepinsight/insightface/releases/download/v0.7/inswapper_128.onnx") as resp:
                if resp.status == 200:
                    content = await resp.read()
                    with open("models/inswapper_128.onnx", "wb") as f:
                        f.write(content)
                else:
                    raise RuntimeError("Failed to download inswapper model.")

app = insightface.app.FaceAnalysis(name="buffalo_l", root='./', providers=["CPUExecutionProvider"])
app.prepare(ctx_id=0, det_size=(640, 640), det_thresh=0.3)
app_gif = insightface.app.FaceAnalysis(name="buffalo_l", root='./', providers=["CPUExecutionProvider"])
app_gif.prepare(ctx_id=0, det_size=(128, 128), det_thresh=0.3)
asyncio.run(ensure_inswapper_model())
swapper = insightface.model_zoo.get_model('models/inswapper_128.onnx', providers=["CPUExecutionProvider"])

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
frame_step= int(os.getenv("GIF_FRAME_STEP", 1))
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

@tree.command(name="edit_image", description="Edit an image with an image")
@discord.app_commands.describe(
    prompt="The prompt to edit the image with",
    attachment="Image attachment to edit. Choose either this or provide an image URL.",
    image_url="URL of the image to edit. Choose either this or upload an image."
)
async def edit_command(
    interaction: discord.Interaction,
    prompt: str,
    attachment: discord.Attachment | None = None,
    image_url: str | None = None
):
    if attachment:
        image_url = attachment.url
    elif image_url:
        if not await check_image_url(image_url):
            await interaction.response.send_message("The provided URL does not point to a valid image.")
            return
    else:
        await interaction.response.send_message("Please provide either an image attachment or an image URL.")
        return

    await interaction.response.defer()
    try:
        image = await edit_image(image_url, prompt)
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

async def read_bytes_from_url(url: str) -> bytes:
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/gif,image/*;q=0.9,*/*;q=0.8",
    }
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to download URL: HTTP {resp.status}")
            data = await resp.read()
    if not data:
        raise RuntimeError("Downloaded URL returned empty content")
    return data

def swap_face(source_bytes: bytes, target_bytes: bytes) -> discord.File:
    """Swap target face with source face and return as a Discord file."""
    try:
        source_img = cv2.imdecode(np.frombuffer(source_bytes, np.uint8), cv2.IMREAD_COLOR)
        target_img = cv2.imdecode(np.frombuffer(target_bytes, np.uint8), cv2.IMREAD_COLOR)
        if source_img is None or target_img is None:
            raise RuntimeError("Failed to decode uploaded images")

        source_faces = app.get(source_img)
        if not source_faces:
            raise RuntimeError("No faces detected in the source image")
        target_faces = app.get(target_img)
        target_faces = sorted(target_faces, key = lambda x : x.bbox[0])
        if not target_faces:
            raise RuntimeError("No faces detected in the target image")
        
        source_face = source_faces[0]
        result = target_img.copy()
        for face in target_faces:
            result = swapper.get(result, face, source_face, paste_back=True)
        _, buffer = cv2.imencode(".jpg", result)
        return discord.File(BytesIO(buffer.tobytes()), filename="swapped.jpg")
    except Exception as e:
        raise RuntimeError(e)
    
@client.command()
async def kirkify(ctx):
    try:
        if ctx.message.attachments:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://kirkify.wtf/source.png") as resp:
                    if resp.status == 200:
                        source_bytes = await resp.read()
                    else:
                        raise RuntimeError("Failed to fetch Kirk image.")
            target = await ctx.message.attachments[0].read()
            swapped_file = await asyncio.to_thread(swap_face, source_bytes, target)
            await ctx.reply(file=swapped_file)
        else:
            await ctx.reply("Please attach an image to kirkify.")
    except Exception as e:
        await ctx.reply(str(e))

@tree.command(name="swap", description="Swap faces in an image")
@discord.app_commands.describe(
    source="Source face image upload",
    source_url="Source face image URL",
    target="Target image upload",
    target_url="Target image URL"
)
async def swap_command(
    interaction: discord.Interaction,
    source: discord.Attachment | None = None,
    source_url: str | None = None,
    target: discord.Attachment | None = None,
    target_url: str | None = None
):
    await interaction.response.defer()
    try:
        if source:
            source_bytes = await source.read()
        elif source_url:
            source_bytes = await read_bytes_from_url(source_url)
        else:
            raise ValueError("Either 'source' attachment or 'source_url' must be provided")

        if target:
            target_bytes = await target.read()
        elif target_url:
            target_bytes = await read_bytes_from_url(target_url)
        else:
            raise ValueError("Either 'target' attachment or 'target_url' must be provided")

        swapped_file = await asyncio.to_thread(swap_face, source_bytes, target_bytes)
        await interaction.followup.send(file=swapped_file)
    except Exception as e:
        await interaction.followup.send(f"Error swapping faces: {str(e)}")

def swap_gif(source_bytes: bytes, gif_bytes: bytes) -> BytesIO:
    """Swap faces in a GIF and return as a BytesIO object."""
    try:
        frames = []
        new_frames = []
        durations = []

        with Image.open(BytesIO(gif_bytes)) as im:
            for idx, frame in enumerate(ImageSequence.Iterator(im)):
                if idx % frame_step == 0:
                    frames.append(frame.convert("RGB"))
                    durations.append(frame.info.get('duration', 100) * frame_step)
        if not frames:
            raise RuntimeError("No frames found in GIF")

        source_img = cv2.imdecode(np.frombuffer(source_bytes, np.uint8), cv2.IMREAD_COLOR)
        if source_img is None:
            raise RuntimeError("Failed to decode source image")
        source_faces = app_gif.get(source_img)
        if not source_faces:
            raise RuntimeError("No faces detected in the source image")
        source_face = source_faces[0]

        for i in range(len(frames)):
            try:
                frame_np = np.array(frames[i])
                target_img = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
                
                target_faces = app_gif.get(target_img)
                if not target_faces:
                    print(f"No faces detected in frame {i}, skipping face swap.")
                    new_frames.append(frames[i])
                    continue
                
                target_faces = sorted(target_faces, key=lambda x: x.bbox[0])
                result = target_img.copy()
                for face in target_faces:
                    result = swapper.get(result, face, source_face, paste_back=True)
                
                result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
                new_frames.append(Image.fromarray(result_rgb))
            except Exception as e:
                print(f"Error processing frame {i}: {str(e)}")
                new_frames.append(frames[i])
                continue
        
        if not new_frames:
            raise RuntimeError("Face swapping failed for all frames")

        output = BytesIO()
        new_frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=new_frames[1:],
            optimize=False,
            duration=durations,
            loop=0,
            disposal=2
        )
        output.seek(0)
        if output.getbuffer().nbytes > 10 * 1024 * 1024:
            print("Output GIF exceeds 10MB, reducing quality to fit within Discord limits.")
            resized_frames = []
            for frame in new_frames:
                resized_frame = frame.resize((frame.width // 2, frame.height // 2), Image.Resampling.LANCZOS)
                resized_frames.append(resized_frame)
            output = BytesIO()
            resized_frames[0].save(
                output,
                format="GIF",
                save_all=True,
                append_images=resized_frames[1:],
                optimize=True,
                duration=durations,
                loop=0,
                disposal=2
            )
            output.seek(0)
        return output
    except Exception as e:
        raise RuntimeError(e)

@tree.command(name="swap_gif", description="Swap faces in a GIF")
@discord.app_commands.describe(
    source="Source face image upload",
    gif="Target GIF upload. Choose either this or provide a URL.",
    gif_url="Target GIF URL. Choose either this or upload a file.",
)
async def swap_gif_command(
    interaction: discord.Interaction,
    source: discord.Attachment,
    gif: discord.Attachment | None = None,
    gif_url: str | None = None
):
    await interaction.response.defer()
    try:
        start = time.time()
        source_bytes = await source.read()
        if gif:
            gif_bytes = await gif.read()
        elif gif_url:
            gif_bytes = await read_bytes_from_url(gif_url)
        else:
            raise ValueError("Either 'gif' attachment or 'gif_url' must be provided")
        async with asyncio.timeout(300):
            swapped_gif = await asyncio.to_thread(swap_gif, source_bytes, gif_bytes)
        print(f"GIF face swap completed in {time.time() - start:.2f} seconds")
        await interaction.followup.send(file=discord.File(swapped_gif, filename="swapped.gif"))
    except TimeoutError:
        await interaction.followup.send("Face swapping process took too long and timed out. Please try again with a smaller GIF or fewer faces.")
    except Exception as e:
        await interaction.followup.send(f"Error swapping faces in GIF: {str(e)}")

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
    embed.add_field(name="/swap", value="Swaps the face in the target image with the face in the source image", inline=False)
    embed.add_field(name="/swap_gif", value="Swaps the face in the target GIF with the face in the source image.", inline=False)
    embed.add_field(name="/generate_image", value="Generate an image from a prompt.", inline=False)
    embed.add_field(name="/models", value="List available models", inline=False)
    embed.add_field(name="/providers", value="List available providers", inline=False)
    embed.add_field(name="/full_list", value="List available providers and their compatible models", inline=False)
    embed.add_field(name="/info", value="Show current provider and model", inline=False)
    embed.add_field(name="/set_provider", value="Set the provider for text responses", inline=False)
    embed.add_field(name="/set_model", value="Set the model for text responses", inline=False)
    embed.add_field(name="/reset", value="Reset provider and model to default", inline=False)
    embed.add_field(name="/edit_image", value="Edit an image with an attached image or url. Alternative command for @GlizzyBot !edit", inline=False)
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
