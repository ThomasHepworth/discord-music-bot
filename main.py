import discord
import os
from discord.ext import commands

# import other functions
# from annoy_jack import annoy_jack
# import all of the cogs
# from music_cog import music_cog
from new_music_bot import Music

bot = commands.Bot(command_prefix='#')

# remove the default help command so that we can write out own
bot.remove_command('help')

# register the class with the bot
bot.add_cog(Music(bot))
# bot.add_cog(annoy_jack(bot))

# load in the token from within hiroku
# token = os.environ['TOKEN'] # use this if you're using the TOKEN within heroku
token = os.getenv('TOKEN') # use this if you're running from docker

#start the bot with our token
# with open("token.txt") as file:
#     token = file.read()

# power up our bot
bot.run(token)
