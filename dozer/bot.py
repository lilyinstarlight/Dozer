"""Bot object for Dozer"""


import os
import re
import sys
import traceback
from typing import Pattern

import discord
from discord.ext import commands
from loguru import logger
from sentry_sdk import capture_exception

from . import utils
from .cogs import _utils
from .cogs._utils import CommandMixin
from .context import DozerContext
from .db import db_init, db_migrate

if discord.version_info.major < 2:
    logger.error("Your installed discord.py version is too low "
                 "{vi.major}.{vi.minor}.{vi.micro}, please upgrade to at least 2.0.0".format(
                   vi=discord.version_info))
    sys.exit(1)


class InvalidContext(commands.CheckFailure):
    """
    Check failure raised by the global check for an invalid command context - executed by a bot, exceeding global rate-limit, etc.
    The message will be ignored.
    """


class Dozer(commands.Bot):
    """Botty things that are critical to Dozer working"""
    _global_cooldown = commands.Cooldown(1, 1)  # One command per second per user

    def __init__(self, config: dict, *args, **kwargs):
        self.wavelink = None
        self.dynamic_prefix = _utils.PrefixHandler(config['prefix'])
        super().__init__(command_prefix=self.dynamic_prefix.handler, *args, **kwargs)
        self.config = config
        self._restarting = False
        self.check(self.global_checks)
        self.aiohttp_sessions = []

    async def setup_hook(self) -> None:
        for ext in os.listdir('dozer/cogs'):
            cog_name = ext[:-3]
            if not ext.startswith(('_', '.')) and ext.endswith(".py") and not cog_name in self.config.get("disabled_cogs", []):
                await self.load_extension('dozer.cogs.' + cog_name)  # Remove '.py'
        await db_init(self.config['db_url'])
        await db_migrate()
        await self.tree.sync()

    async def on_ready(self):
        """Things to run when the bot has initialized and signed in"""

        logger.info(f'Signed in as {self.user.name}#{self.user.discriminator} ({self.user.id})')
        news_cog = self.get_cog("News")
        await news_cog.startup()
        await self.dynamic_prefix.refresh()
        perms = 0
        for cmd in self.walk_commands():
            if isinstance(cmd, CommandMixin):
                perms |= cmd.required_permissions.value
            else:
                logger.warning(f"Command {cmd} not subclass of Dozer type.")
        logger.debug(f'Bot Invite: {utils.oauth_url(self.user.id, discord.Permissions(perms))}')
        if self.config['is_backup']:
            status = discord.Status.dnd
        else:
            status = discord.Status.online
        activity = discord.Game(name=f"@{self.user.name} or '{self.config['prefix']}' in {len(self.guilds)} guilds")
        try:
            await self.change_presence(activity=activity, status=status)
        except TypeError:
            logger.warning("You are running an older version of the discord.py rewrite (with breaking changes)! "
                           "To upgrade, run `pip install -r requirements.txt --upgrade`")

    async def get_context(self, message: discord.Message, *, cls=DozerContext):  # pylint: disable=arguments-differ
        ctx = await super().get_context(message, cls=cls)
        return ctx

    async def on_command_error(self, context: DozerContext, exception):  # pylint: disable=arguments-differ
        if isinstance(exception, commands.NoPrivateMessage):
            await context.send(f'{context.author.mention}, This command cannot be used in DMs.')
        elif isinstance(exception, commands.UserInputError):
            await context.send(f'{context.author.mention}, {self.format_error(context, exception)}')
        elif isinstance(exception, commands.NotOwner):
            await context.send(f'{context.author.mention}, {exception.args[0]}')
        elif isinstance(exception, commands.MissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in
                                exception.missing_permissions]
            await context.send(f'{context.author.mention}, you need {utils.pretty_concat(permission_names)} permissions to run this command!')
        elif isinstance(exception, commands.BotMissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in
                                exception.missing_permissions]
            await context.send(f'{context.author.mention}, I need {utils.pretty_concat(permission_names)} permissions to run this command!')
        elif isinstance(exception, commands.CommandOnCooldown):
            await context.send(f'{context.author.mention}, That command is on cooldown! Try again in {exception.retry_after:.2f}s!')
        elif isinstance(exception, commands.MaxConcurrencyReached):
            types = {discord.ext.commands.BucketType.default: "`Global`",
                     discord.ext.commands.BucketType.guild: "`Guild`",
                     discord.ext.commands.BucketType.channel: "`Channel`",
                     discord.ext.commands.BucketType.category: "`Category`",
                     discord.ext.commands.BucketType.member: "`Member`", discord.ext.commands.BucketType.user: "`User`"}
            await context.send(
                f'{context.author.mention}, That command has exceeded the max {types[exception.per]} concurrency limit of '
                f'`{exception.number}` instance! Please try again later.')
        elif isinstance(exception, (commands.CommandNotFound, InvalidContext)):
            pass  # Silent ignore
        else:
            await context.send('```\n' + ''.join(traceback.format_exception_only(type(exception), exception)).strip() + '\n```')
            if isinstance(context.channel, discord.TextChannel):
                logger.error('Error in command <{c.command}> ({g.name!r}({g.id}) {chn}({chn.id}) {a}({a.id}) {c.message.content})'.format(
                             c=context, g=context.guild, a=context.author, chn=context.channel))
            else:
                logger.error('Error in command <{c.command}> (DM {recipient}({recipient.id}) {content})'.format(
                              c=context, recipient=context.channel.recipient, content=context.message.content))
            logger.error(''.join(traceback.format_exception(type(exception), exception, exception.__traceback__)))

    async def on_error(self, event_method, *args, **kwargs):
        """Don't ignore the error, causing Sentry to capture it."""
        print(f'Ignoring exception in {event_method}', file=sys.stderr)
        traceback.print_exc()
        capture_exception()

    @staticmethod
    def format_error(ctx: DozerContext, err: Exception, *, word_re: Pattern = re.compile('[A-Z][a-z]+')):
        """Turns an exception into a user-friendly (or -friendlier, at least) error message."""
        type_words = word_re.findall(type(err).__name__)
        type_msg = ' '.join(map(str.lower, type_words))

        if err.args:
            return f'{type_msg}: {utils.clean(ctx, err.args[0])}'
        else:
            return type_msg

    def global_checks(self, ctx: DozerContext):
        """Checks that should be executed before passed to the command"""
        if ctx.author.bot:
            raise InvalidContext('Bots cannot run commands!')
        retry_after = self._global_cooldown.update_rate_limit()
        if retry_after and not hasattr(ctx, "is_pseudo"):  # bypass ratelimit for su'ed commands
            raise InvalidContext('Global rate-limit exceeded!')
        return True

    def run(self, *args, **kwargs):
        token = self.config['discord_token']
        del self.config['discord_token']  # Prevent token dumping
        super().run(token)

    async def shutdown(self, restart: bool = False):
        """Shuts down the bot"""
        self._restarting = restart
        await self.close()
        self.loop.stop()

    async def close(self):
        """performs cleanup and actually shuts down the bot"""
        logger.info("Bot is shutting down...")
        await super().close()
        for ses in self.aiohttp_sessions:
            await ses.close()

    def add_aiohttp_ses(self, ses):
        """add an aiohttp session to the session registry"""
        self.aiohttp_sessions.append(ses)
        return ses
