import discord
from discord.ext import commands

import os

#import all of the cogs
from music_cog import music_cog

bot = commands.Bot(command_prefix='#')

#remove the default help command so that we can write out own
bot.remove_command('help')

#register the class with the bot
bot.add_cog(music_cog(bot))

# load in the token from within hiroku
token = os.environ('TOKEN') # use this if you're using the TOKEN within heroku
# token = os.getenv('TOKEN') # use this if you're running from docker

# power up our bot
bot.run(token)
