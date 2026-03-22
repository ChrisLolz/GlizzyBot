# GlizzyBot

Discord bot that makes everyone eat a glizzy and it uses qwen3.5-plus model to generate images

# Prerequisites
- Python 3.10+

## Setup 
- Open the Discord Developer Portal and create an application.
- Create `.env` and set: `DISCORD_TOKEN`

## Docker

- Dockerfile is provided if you want to run the bot in a container:

- Build image:

```docker build -t glizzybot .```

- Run container:

```docker run -e IMAGE_GENERATION_COOLDOWN="15" DISCORD_TOKEN="your-token-here" glizzybot```