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

#start the bot with our token
with open("token.txt") as file:
    token = file.read()
# power up our bot
bot.run(token)
# bot.run(os.getenv("TOKEN"))