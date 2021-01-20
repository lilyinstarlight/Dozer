"""Given an arbitrary RSS feed, get new posts from it"""
import re
import datetime

import aiohttp
import discord
import html2text
import scrapy

from .AbstractSources import Source


class FTCQA(Source):
    """The official FTC Forum Q&A threads"""
    full_name = 'FTC Q&A Answers'
    short_name = 'ftc-qa'
    base_url = 'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm'
    description = 'Answers from the official FIRST Tech Challenge Q&A forum'
    threads = {
        'Game Rules - Autonomous Period':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/game-rules-ac/remote-events/'
            'answers-game-rules-ac/83772-autonomous-period',
        'Game Rules - Driver-Controlled Period':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/game-rules-ac/remote-events/'
            'answers-game-rules-ac/83771-driver-controlled-period',
        'Game Rules - End Game':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/game-rules-ac/remote-events/'
            'answers-game-rules-ac/83770-end-game',
        'Game Rules - Gameplay (All Match Periods)':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/game-rules-ac/remote-events/'
            'answers-game-rules-ac/83774-gameplay-–-all-match-periods',
        'Game Rules - Pre-Match':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/game-rules-ac/remote-events/'
            'answers-game-rules-ac/83773-pre-match',
        'Game Rules - Scoring':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/game-rules-ac/remote-events/'
            'answers-game-rules-ac/85050-scoring',
        'Competition Rules':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/competition-rules/remote-events-aa/'
            'answers-competition-rules-aa/83786-competition-rules',
        'Robot Build Rules - Raw and Post Processed Materials':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/robot-build-rules/traditional-and-remote/'
            'answers-robot-mechanical-parts-and-materials/83759-raw-and-post-processed-materials',
        'Robot Build Rules - General':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/robot-build-rules/traditional-and-remote/'
            'answers-robot-mechanical-parts-and-materials/83757-general-robot-rules',
        'Robot Build Rules - Commercial Off the Shelf Components':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/robot-build-rules/traditional-and-remote/'
            'answers-robot-mechanical-parts-and-materials/83758-commercial-off-the-shelf-components',
        'Robot Build Rules - Sensors':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/robot-build-rules/traditional-and-remote/'
            'answers-robot-mechanical-parts-and-materials-aa/83763-sensors',
        'Robot Build Rules - Motors and Servos':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/robot-build-rules/traditional-and-remote/'
            'answers-robot-mechanical-parts-and-materials-aa/83761-motors-and-servos',
        'Robot Build Rules - Miscellaneous Robot Electrical Parts and Materials':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/robot-build-rules/traditional-and-remote/'
            'answers-robot-mechanical-parts-and-materials-aa/83760-miscellaneous-robot-electrical-parts-and-materials',
        'Robot Build Rules - Control System':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/robot-build-rules/traditional-and-remote/'
            'answers-robot-mechanical-parts-and-materials-aa/83762-control-system',
        'Software Rules':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/robot-build-rules/traditional-and-remote/'
            'answers-robot-software-rules-ab/83866-software-rules',
        'Field Setup':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/field-setup-ab/remote-events-ab/'
            'answers-field-setup-ae/83796-field-setup',
        'Judging - Judges Interview':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/the-judging-process-ac/remote-events-ac/'
            'answers-the-judging-process-ab/83808-judges-interview',
        'Judging - Engineering Portfolio':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/the-judging-process-ac/remote-events-ac/'
            'answers-the-judging-process-ab/83807-engineering-portfolio',
        'Advancement':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/advancement-ad/remote-events-ad/'
            'answers-advancement-ae/83822-advancement',
        'FIRST Innovation Challenge Rules':
            'https://ftcforum.firstinspires.org/forum/ultimate-goal-presented-by-qualcomm/first-innovation-challenge/'
            'post-your-first-innovation-questions-here/answers-first-innovation-award/85412-first-innovation-challenge-rules',
    }
    color = discord.colour.Color.orange()

    def __init__(self, aiohttp_session: aiohttp.ClientSession, bot):
        super().__init__(aiohttp_session, bot)
        self.posts_seen = set()

    async def first_run(self):
        """Fetch the current posts in the feed and add them to the posts_seen set"""
        for name, url in self.threads.items():
            response = await self.fetch(url)
            self.parse(name, url, response, True)

    async def get_new_posts(self):
        """Fetch the current posts in the feed, parse them for data and generate embeds/strings for them"""
        for name, url in self.threads.items():
            response = await self.fetch(url)
            items = self.parse(name, url, response)
            new_posts = {
                'source': {
                    'embed': [],
                    'plain': []
                }
            }
            for data in items:
                new_posts['source']['embed'].append(self.generate_embed(data))
                new_posts['source']['plain'].append(self.generate_plain_text(data))
            return new_posts

    async def fetch(self, url):
        """Use aiohttp to get the source feed"""
        response = await self.http_session.get(url=url)
        return await response.text()

    def parse(self, name, url, response, first_time=False):
        """Use scrapy to get data for new posts"""
        new_items = []
        selector = scrapy.Selector(text=response)
        for post in selector.xpath('//div[has-class("js-post__content-wrapper")]'):
            try:
                post_id = post.xpath('.//a[has-class("b-post__count")]/@href').get().split('#', 1)[1].strip()
            except IndexError:
                continue

            if first_time:
                self.posts_seen.add(post_id)
                continue

            new = self.determine_if_new(post_id)
            if not new:
                continue

            post_date = datetime.datetime.fromisoformat(post.xpath('.//div[has-class("b-post__timestamp")]/time/@datetime').get() + '-08:00')
            post_date = post_date.astimezone(datetime.timezone.utc)

            post_content = post.xpath('.//div[has-class("js-post__content-text")]').get()

            clean_regex = re.compile(r'<.*?>')

            content_regex = re.compile(
                r'.*<div class="bbcode_postedby">\s*Originally posted by(.*?)</div>\s*<div class="message">(.*?)</div>(.*)', re.I | re.M | re.S)
            content_match = re.fullmatch(content_regex, post_content)

            if not content_match:
                continue

            post_asker, post_question, post_answer = content_match.groups()

            post_asker = re.sub(clean_regex, '', post_asker).strip()
            post_question = html2text.html2text(post_question).strip()
            post_answer = html2text.html2text(post_answer).strip()

            data = {}

            data['date'] = post_date
            data['title'] = f'FTC Q&A for {name}'
            data['url'] = f'{url}#{post_id}'
            data['author'] = post_asker
            data['description'] = f'FTC Q&A for {name}\n\nAsked by **{post_asker}**:\n\n{post_question}\n\n{post_answer}'

            new_items.add(data)
        return new_items

    def determine_if_new(self, post):
        """Given a post item's id, determine if this item is new or not. Store id if new."""
        if post not in self.posts_seen:
            self.posts_seen.add(post)
            return True
        else:
            return False

    def generate_embed(self, data):
        """Given a dictionary of data, generate a discord.Embed using that data"""
        embed = discord.Embed()
        embed.title = data['title']
        embed.colour = self.color

        embed.description = data['description']

        embed.url = data['url']

        embed.set_author(name=data['author'])

        embed.timestamp = data['date']

        return embed

    def generate_plain_text(self, data):
        """Given a dictionary of data, generate a string using that data"""
        return f"{data['title']}\n" \
               f"Asked by {data['author']}:\n" \
               f"{data['description']}\n" \
               f"Link: {data['url']}"
