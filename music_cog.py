import asyncio
import functools
import itertools
import math
import random
from collections import namedtuple
from datetime import datetime, timedelta

import discord
import yt_dlp
from async_timeout import timeout
from discord.ext import commands

# Silence useless bug reports messages
yt_dlp.utils.bug_reports_message = lambda: ''


def parse_duration(duration: int):
    d = datetime(1,1,1) + timedelta(seconds=int(duration))
    time_index = namedtuple("Time", ['Days', 'Hours', 'Minutes', 'Seconds'])
    # pull out our song duration
    duration = time_index(d.day-1, d.hour, d.minute, d.second)
    return ", ".join([f"{duration._fields[n]}: {t}" for n, t in enumerate(duration) if t>0])


def parse_minutes(duration: int):
    """
    Simpler parser that neatly formats an input into
    minutes and seconds
    """
    remainder = duration % 60
    minutes = (duration-remainder)/60
    return f'{int(minutes)} min {remainder} sec'

class VoiceError(Exception):
    pass

class YTDLError(Exception):
    pass

class YTDLSource(discord.PCMVolumeTransformer): # volume control class...
    YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist':'True'} # ydl settings

    FFMPEG_OPTIONS = { # ffmpeg audio playback options
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 
        'options': '-vn'
        }

    ytdl = yt_dlp.YoutubeDL(YDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data
         
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.raw_duration = data.get('duration')
        self.url = data.get('webpage_url')
        self.stream_url = data.get('url')

    def __str__(self):
        return '**{0.title}**'.format(self)

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()
        search = search.replace("ytsearch:", "")
        prefix = "ytsearch:"  # update this to an if statement to check if link has been submitted
        partial = functools.partial(cls.ytdl.extract_info, f"{prefix}{search}", download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None: # raise an error if YTDL returns NULL
            raise YTDLError(f"Couldn't find anything that matches: `{search}`")

        if 'entries' not in data:
            webpage_url = data['webpage_url']
        else:
            webpage_url = None
            for entry in data['entries']:
                webpage_url = entry['url']
                break

            if webpage_url is None:
                raise YTDLError(f"Couldn't find anything that matches: `{search}`")

        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError(f"Couldn't fetch: `{webpage_url}`")

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError(f"Couldn't retrieve any matches for: {webpage_url}. /nYou might be searching for something that's 18+.")

        return cls(ctx, discord.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)


### start updating and checking from here...
class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (discord.Embed(title='🎵  Now playing  🎵',
                               description=f'```yaml\n{self.source.title}\n```',
                               color=discord.Color.blurple())
                 .add_field(name='Duration', value=parse_minutes(self.source.raw_duration))
                 .add_field(name='Requested by', value=self.requester.mention)
                 .add_field(name='URL', value=f'[Click]({self.source.url})')
                 .set_thumbnail(url=self.source.thumbnail))

        return embed

class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]
    
    def index_song(self, index: int):
        # item = self.item
        # return self._queue[index]
        return list(self._queue)


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()

            if not self.loop:
                # Try to get the next song within 3 minutes.
                # If no song will be added to the queue in time,
                # the player will disconnect due to performance
                # reasons.
                try:
                    async with timeout(300):  # one minute
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    return

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            await self.current.source.channel.send(embed=self.current.create_embed())

            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None



class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('This command can\'t be used in DM channels.')

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send('An error occurred: {}'.format(str(error)))

    @commands.command(name='join', invoke_without_subcommand=True)
    async def _join(self, ctx: commands.Context):
        """Joins a voice channel."""

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='summon')
    @commands.has_permissions(manage_guild=True)
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        """Summons the bot to a voice channel.
        If no channel was specified, it joins your channel.
        """

        if not channel and not ctx.author.voice:
            raise VoiceError('You are neither connected to a voice channel nor specified a channel to join.')

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect', 'quit'])
    @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):
        """Clears the queue and leaves the voice channel."""

        if not ctx.voice_state.voice:
            return await ctx.send('Not connected to any voice channel.')

        await ctx.voice_state.stop()
        await ctx.message.add_reaction('🕊️')
        del self.voice_states[ctx.guild.id]

    @commands.command(name='volume')
    async def _volume(self, ctx: commands.Context, *, volume: int):
        """Sets the volume of the player."""

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        if 0 > volume > 100:
            return await ctx.send('Volume must be between 0 and 100')

        ctx.voice_state.volume = volume / 100
        await ctx.send(f'Volume of the player set to {volume}%')

    @commands.command(name='now', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context):
        """Displays the currently playing song."""

        await ctx.send(embed=ctx.voice_state.current.create_embed())

    @commands.command(name='pause') # not currently working
    @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context):
        """Pauses the currently playing song."""

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='resume') # not currently working
    @commands.has_permissions(manage_guild=True)
    async def _resume(self, ctx: commands.Context):
        """Resumes a currently paused song."""

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='stop') # not currently working
    @commands.has_permissions(manage_guild=True)
    async def _stop(self, ctx: commands.Context):
        """Stops playing song and clears the queue."""

        ctx.voice_state.songs.clear()

        if not ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction('⏹')

    @commands.command(name='clear') # not currently working
    @commands.has_permissions(manage_guild=True)
    async def _stop(self, ctx: commands.Context):
        """Clears the current queue."""

        ctx.voice_state.songs.clear()
        await ctx.send("Song queue cleared ☕")

    @commands.command(name='skip') # not currently working
    async def _skip(self, ctx: commands.Context):
        """Vote to skip a song. The requester can automatically skip.
        3 skip votes are needed for the song to be skipped.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('Not playing any music right now...')

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction('⏭')
            ctx.voice_state.skip()

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send(f'Skip vote added, currently at **{total_votes}/3**')

        else:
            await ctx.send('You have already voted to skip this song.')

    # @commands.command(name='queue', aliases=["queue", "q"], help="Shows info on the current queue.")
    @commands.command(aliases=["queue", "q"], help="Shows info on the current queue.")
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        """Shows the player's queue.
        You can optionally specify the page to show. Each page contains 10 elements.
        """

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        timer = 0
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += f'`{i + 1}.` [**{song.source.title}**]({song.source.url}) -- `{parse_minutes(song.source.raw_duration)}`\n'
            timer += song.source.raw_duration

        embed = (discord.Embed(description='**{} track(s)** -- `{}`:\n\n{}'.format(len(ctx.voice_state.songs), parse_minutes(timer), queue))
                 .set_footer(text=f'Viewing page {page}/{pages}'))
        await ctx.send(embed=embed)

    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Shuffles the queue."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('✅')

    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int = 1):
        """Removes a song from the queue at a given index."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        # await ctx.send(f'🎵 Removing `{ctx.voice_state.songs.index_song}`')
        # await ctx.send(f'{ctx.voice_state.songs.source.title}')
        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction('✅')

    @commands.command(name='loop')
    async def _loop(self, ctx: commands.Context):
        """Loops the currently playing song.
        Invoke this command again to unloop the song.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop
        await ctx.message.add_reaction('✅')

    @commands.command(aliases=['play', 'p'])
    async def _play(self, ctx: commands.Context, *, search: str):
        """Plays a song.
        If there are songs in the queue, this will be queued until the
        other songs finished playing.
        This command automatically searches from various sites if no URL is provided.
        A list of these sites can be found here: https://rg3.github.io/youtube-dl/supportedsites.html
        """

        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                await ctx.send(f'An error occurred while processing this request: {str(e)}')
            else:
                song = Song(source)

                await ctx.voice_state.songs.put(song)
                await ctx.message.add_reaction('🎵')
                await ctx.send(f'🔊 Queued: {str(source)}')

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('You are not connected to any voice channel.')

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError('Bot is already in a voice channel.')
