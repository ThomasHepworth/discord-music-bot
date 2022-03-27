import discord
import os
from discord.ext import commands

# import our music cog
from music_cog import Music

bot = commands.Bot(command_prefix='#')

# remove the default help command so that we can write out own
bot.remove_command('help')

# register the class with the bot
bot.add_cog(Music(bot))

# load in the token from within hiroku
token = os.environ['TOKEN'] # use this if you're using the TOKEN within heroku
# token = os.getenv('TOKEN') # use this if you're running from docker

# with open("token.txt") as file:
#     token = file.read()

# power up our bot
bot.run(token)
