from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord.enums import ButtonStyle
from redbot.core.config import Config

from ..vexutils import get_vex_logger

if TYPE_CHECKING:
    from ..poll import Poll

log = get_vex_logger(__name__)


class OptionButton(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction):
        async def update_vote():
            assert isinstance(self.view, PollView)
            await self.view.config.guild(
                interaction.guild  # type:ignore
            ).poll_user_choices.set_raw(  # type:ignore
                self.view.poll_settings.unique_poll_id,
                interaction.user.id,  # type:ignore
                value=self.label,
            )

        assert isinstance(self.view, PollView)

        current_choice = await self.view.get_user_voter_vote(
            interaction.guild, interaction.user.id  # type:ignore
        )

        if self.view.poll_settings.allow_vote_change is False and current_choice is not None:
            msg = (
                f"You've already voted for `{current_choice}`, and you can't change your vote in "
                "this poll."
            )
        elif current_choice == self.label:
            msg = f"You're already voting for `{self.label}`!"
        elif current_choice is not None:
            msg = f"You've already voted, so I've **changed** your vote to `{self.label}`."
            await update_vote()
        else:
            msg = f"You've voted for `{self.label}`."
            await update_vote()
        await interaction.response.send_message(msg, ephemeral=True)


class PollView(discord.ui.View):
    """View for an active poll. This is persistent-compatible."""

    def __init__(self, config: Config, poll_settings: "Poll"):
        super().__init__(timeout=None)

        log.debug(f"PollView created for {poll_settings}")

        for option in poll_settings.options:
            if not option.name:
                continue
            self.add_item(
                OptionButton(
                    style=option.style,
                    label=option.name,
                    custom_id=poll_settings.unique_poll_id[:70] + "_" + option.name[:29],
                )
            )

        self.poll_settings = poll_settings
        self.config = config

        if poll_settings.view_while_live is False:
            self.remove_item(self.view_results_btn)  # type:ignore  # yes this does work

    async def get_user_voter_vote(self, guild: discord.Guild, user_id: int) -> Optional[str]:
        """Get the vote of a user in a poll."""
        return (
            (await self.config.guild(guild).poll_user_choices())
            .get(self.poll_settings.unique_poll_id, {})
            .get(str(user_id), None)  # everything is a string in config
        )

    @discord.ui.button(label="Meine Wahl sehen", custom_id="view_vote", style=ButtonStyle.grey, row=2)
    async def view_my_vote_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show the user their current vote, if any."""
        choice = await self.get_user_voter_vote(
            interaction.guild, interaction.user.id  # type:ignore
        )
        if choice is None:
            await interaction.response.send_message("Du hast an dieser Umfrage noch nicht teilgenommen!", ephemeral=True)
        else:
            change = (
                "Ändere deine Wahl im den du einen neuen Button wählst."
                if self.poll_settings.allow_vote_change
                else ""
            )
            await interaction.response.send_message(
                f"Deine Wahl liegt aktuell bei `{choice}`. " + change,
                ephemeral=True,
            )

    @discord.ui.button(
        label="Ergebnisse sehen", custom_id="view_results", style=ButtonStyle.grey, row=2
    )
    async def view_results_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show the results of the poll."""
        choice = await self.get_user_voter_vote(
            interaction.guild, interaction.user.id  # type:ignore
        )
        if choice is None:
            await interaction.response.send_message(
                "Um die Ergebnisse zusehen, musst du selbst an der Umfrage teilnehmen .", ephemeral=True
            )
            return

        results = await self.poll_settings.get_results()

        sorted_results = {
            k: v for k, v in sorted(results.items(), key=lambda x: x[1], reverse=True)
        }

        await interaction.response.send_message(
            "**Ergebnisse der Umfrage**:\n" + "\n".join(f"{k}: {v}" for k, v in sorted_results.items()),
            ephemeral=True,
        )
