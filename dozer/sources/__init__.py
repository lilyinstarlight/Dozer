"""A collection of sources for various FIRST-related news sources"""

from .RSSSources import *
from .TwitchSource import TwitchSource
from .RedditSource import RedditSource
from .ForumSources import FTCQA
from .AbstractSources import Source, DataBasedSource

sources = [TwitchSource, RedditSource, FTCQA]
sources += [source for source in RSSSource.__subclasses__() if not source.disabled]
