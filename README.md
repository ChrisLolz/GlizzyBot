# GlizzyBot

Discord bot that makes everyone eat a glizzy and it uses qwen3.5-plus model to generate images and some other AI stuff. For face swapping, inswapper_128 is used. 

Meant for personal usage, not for large scale.

# Prerequisites
- Python 3.10+

## Setup 
- Open the Discord Developer Portal and create an application.
- Create `.env`

## Docker

- Dockerfile is provided if you want to run the bot in a container:

- Build image:

```docker build -t glizzybot .```

- Run container:

```docker run glizzybot```