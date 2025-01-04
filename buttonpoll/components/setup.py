from __future__ import annotations

import datetime
import os
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

import discord
from discord import Interaction, SelectOption, TextChannel, Thread, ui
from discord.enums import ButtonStyle
from redbot.core.commands import parse_timedelta

from ..poll import Poll, PollOption
from .poll import PollView

if TYPE_CHECKING:
    from ..buttonpoll import ButtonPoll

from ..vexutils.chat import datetime_to_timestamp


class StartSetupView(discord.ui.View):
    def __init__(
        self,
        *,
        author: discord.Member,
        channel: discord.TextChannel | discord.Thread,
        cog: "ButtonPoll",
    ):
        super().__init__(timeout=300)  # 5 minutes

        self.author = author
        self.channel = channel
        self.cog = cog

    @discord.ui.button(label="Start poll", style=ButtonStyle.primary)
    async def btn_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_modal(
            SetupModal(author=self.author, channel=self.channel, cog=self.cog)
        )

        button.disabled = True
        await interaction.message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author.id:
            return True

        await interaction.response.send_message(
            "Du kannst dies nicht tun.", ephemeral=True
        )
        return False


class SetupModal(ui.Modal, title="Umfrage setup"):
    def __init__(
        self,
        *,
        author: discord.Member,
        channel: TextChannel | Thread,
        cog: "ButtonPoll",
    ) -> None:
        super().__init__(timeout=600)  # 10 minutes

        self.author = author
        self.channel = channel
        self.cog = cog

    question = ui.TextInput(
        label="Frage",
        placeholder="Wie lautet die Frage?",
        max_length=256,
    )
    description = ui.TextInput(
        label="Beschreibung",
        placeholder="Gebe eine Beschreibung an",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000,
    )
    time = ui.TextInput(
        label="Umfrage Dauer",
        placeholder="Beispiele - '1 day', '1 minute', '4 hours'",
        max_length=32,
    )
    options = ui.TextInput(
        label="Optionen",
        placeholder="Gebe 2 bis 5 Optionen an. Nexte Option next Zeile.",
        max_length=80 * 5,  # each option is limited to 80 characters
        style=discord.TextStyle.paragraph,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration = parse_timedelta(self.time.value or "")
        except Exception:
            await interaction.response.send_message(
                "Es wurde kein gültiges Zeitformat verwendet! Nutze ein gültiges!",
                ephemeral=True,
            )
            return
        if duration is None:
            await interaction.response.send_message(
                "Es wurde kein gültiges Zeitformat verwendet! Nutze ein gültiges!",
                ephemeral=True,
            )
            return

        str_options = str(self.options.value).split("\n")
        if len(str_options) < 2:
            await interaction.response.send_message("Es müssen mindestens 2 Optionen gegeben sein.", ephemeral=True)
            return
        elif len(str_options) > 5:
            await interaction.response.send_message(
                "Du kannst nur maximal 5 Optionen angeben!", ephemeral=True
            )
            return

        options: list[PollOption] = []
        for str_option in str_options:
            if len(str_option) > 80:
                return await interaction.response.send_message(
                    "Eine Option ist zulang. Maximale Zeichen 80.",
                    ephemeral=True,
                )
            if str_option in [i.name for i in options]:  # if in already added options
                return await interaction.response.send_message(
                    "Du hast eine Option zweimal genannt!", ephemeral=True
                )
            option = PollOption(str_option, discord.ButtonStyle.primary)
            options.append(option)

        await interaction.response.send_message(
            "Großartig! Jetzt nur ein paar kurze Fragen.",
            view=SetupYesNoView(
                author=self.author,
                channel=self.channel,
                cog=self.cog,
                question=self.question.value or "",
                description=self.description.value or "",
                time=duration,
                options=options,
            ),
            ephemeral=True,
        )


class SetupYesNoView(discord.ui.View):
    def __init__(
        self,
        *,
        timeout: Optional[float] = 300,
        author: discord.Member,
        channel: discord.TextChannel | discord.Thread,
        cog: "ButtonPoll",
        question: str,
        description: str,
        time: timedelta,
        options: list[PollOption],
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.channel = channel
        self.cog = cog

        self.vote_change: bool | None = None
        self.view_while_live: bool | None = None
        self.send_msg_when_over: bool | None = None

        self.question = question
        self.description = description
        self.time = time
        self.options = options

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.author.id:
            return True

        await interaction.response.send_message(
            "You don't have permission to do that.", ephemeral=True
        )
        return False

    @discord.ui.select(
        placeholder="Umfrage Änderungen",
        options=[
            SelectOption(
                label=" Ja",
                description="Nutzer können ihre Stimme ändern.",
                value="yes",
            ),
            SelectOption(
                label= "Nein",
                description="Nutzer können ihre Stimme nicht ändern.",
                value="no",
            ),
        ],
    )
    async def btn_vote_change(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.vote_change = select.values[0] == "yes"
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Live Ergebnisse anzeigen",
        options=[
            SelectOption(
                label="Ja",
                description="Nutzer könne Live sehen, wer für was gestimmt hat.",
                value="yes",
            ),
            SelectOption(
                label="Nein",
                description="Nutzer können nicht sehen, wer für was gestimmt hat.",
                value="no",
            ),
        ],
    )
    async def btn_view_while_live(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        self.view_while_live = select.values[0] == "yes"
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Nachricht senden, wenn Umfrage vorbei?",
        options=[
            SelectOption(
                label="Neue senden",
                description="Sendet eine Nachricht, sobald die Umfrage vorbei ist.",
            ),
            SelectOption(
                label="Bearbeiten",
                description="Bearbeitet einfach die Nachricht.",
            ),
        ],
    )
    async def btn_send_msg_when_over(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        self.send_msg_when_over = select.values[0] == "Send new"
        await interaction.response.defer()

    @discord.ui.button(label="Submit & start poll!", style=ButtonStyle.primary)
    async def btn_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.vote_change is None:
            await interaction.response.send_message(
                "Du hast keine Angabe bei Änderungen gemacht.", ephemeral=True
            )
            return

        if self.view_while_live is None:
            await interaction.response.send_message(
                "Du hast keine Angabe bei Live Ergebnisse gemacht.", ephemeral=True
            )
            return

        if self.send_msg_when_over is None:
            await interaction.response.send_message(
                "Du hast keine Angabe bei Nachricht sendne gemacht.", ephemeral=True
            )
            return

        await interaction.response.defer()

        self.stop()

        unique_poll_id = (  # rand hex, interaction ID, first 25 chars of sanitised question
            os.urandom(5).hex()
            + "_"
            + str(interaction.id)
            + "_"
            + "".join(c for c in self.question if c.isalnum())[:25]
        )
        poll_finish = datetime.datetime.now(datetime.timezone.utc) + self.time

        guild = self.channel.guild
        channel = self.channel

        poll = Poll(
            unique_poll_id=unique_poll_id,
            guild_id=guild.id,
            channel_id=channel.id,
            question=self.question,
            description=self.description,
            options=self.options,
            allow_vote_change=self.vote_change,
            view_while_live=self.view_while_live,
            send_msg_when_over=self.send_msg_when_over,
            poll_finish=poll_finish,
            cog=self.cog,
            view=None,  # type:ignore
        )
        poll.view = PollView(self.cog.config, poll)

        e = discord.Embed(
            colour=await self.cog.bot.get_embed_color(channel),  # type:ignore
            title=poll.question,
            description=poll.description or None,
        )
        e.add_field(
            name=(
                f"Ends at {datetime_to_timestamp(poll.poll_finish)}, "
                f"{datetime_to_timestamp(poll.poll_finish, 'R')}"
            ),
            value=(
                "Du hast eine Auswahl getroffen, "
                + (
                    "du kannst deine Wahl ändern."
                    if poll.allow_vote_change
                    else "du kannst deine Wahl nicht mehr ändern."
                )
                + (
                    "\nDu kannst nun Live sehen, wer für was gestimmmt hat."
                    if poll.view_while_live
                    else "\nDas Ergebnisse dieser Umfrage kannst du am Ende sehen."
                )
            ),
        )

        m = await channel.send(embed=e, view=poll.view)  # type:ignore

        poll.set_msg_id(m.id)
        async with self.cog.config.guild(guild).poll_settings() as poll_settings:
            poll_settings[poll.unique_poll_id] = poll.to_dict()
        self.cog.polls.append(poll)
