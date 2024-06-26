from statistics import mean, median, mode
import discord


async def item_id_autocomplete(ctx: discord.AutocompleteContext):
    scrapper = ctx.bot.scrapper

    item_ids = scrapper.get_item_names()

    return item_ids




class Auctions(discord.Cog):
    def __init__(self, bot):
        self.bot: discord.Bot = bot
        self.scrapper = bot.scrapper

    @discord.slash_command()
    async def e(self, ctx):
        await self.search(ctx, "Terminator")

    @discord.slash_command()
    async def search(
            self,
            ctx: discord.ApplicationContext,
            item_name: str = discord.Option(
                autocomplete=discord.utils.basic_autocomplete(item_id_autocomplete),
                required=True
            )
    ):
        item_id = item_name.replace(" ", "_").upper()
        attributes = self.scrapper.get_attributes(item_id)

        auctions = self.scrapper.get_auctions(item_id)
        embed = discord.Embed(title=item_name, description="\n".join(attributes))
        view = discord.ui.View()

        prices = [auction["price"] for auction in auctions.values() if auction["bin"]]
        embed.add_field(
            name="Median Bin Price",
            value=f"${median(prices):,}"
        )
        embed.add_field(
            name="Average Bin Price",
            value=f"${round(mean(prices)):,}"
        )


        nav_buttons = {
            "nav_first": {
                "emoji": "⏪",
                "style": discord.ButtonStyle.blurple
            },
            "nav_back": {
                "emoji": "⬅️",
                "style": discord.ButtonStyle.blurple
            },
            "nav_field": {
                "emoji": "🔎",
                "style": discord.ButtonStyle.gray
            },
            "nav_next": {
                "emoji": "➡️",
                "style": discord.ButtonStyle.blurple
            },
            "nav_last": {
                "emoji": "⏩",
                "style": discord.ButtonStyle.blurple
            }
        }
        for button_id, button_data in nav_buttons.items():
            button = discord.ui.Button(
                emoji=button_data["emoji"],
                style=button_data["style"],
                custom_id=button_id,
                row=0
            )
            view.add_item(button)

        nav_field_button: discord.ui.Button = view.get_item("nav_field")
        nav_field_button.label = f"0 / {len(auctions)}"

        # Sort Select
        sort_menu = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label="Lowest Price",
                    default=True
                ),
                discord.SelectOption(
                    label="Highest Price"
                ),
                discord.SelectOption(
                    label="Newest"
                ),
                discord.SelectOption(
                    label="Oldest"
                ),

            ],
            row=1
        )
        view.add_item(sort_menu)

        # Attribute Select
        def gen_attr_menu(default: str = None) -> discord.ui.Select:
            menu = discord.ui.Select(placeholder="Select an attribute", row=2, custom_id="select_menu")

            if len(attributes) > 0:
                for attribute in attributes:
                    menu.add_option(
                        label=attribute,
                        default=attribute == default
                    )
            else:
                menu.add_option(
                    label="placeholder"
                )
                menu.disabled = True

            return menu

        def gen_field_menu() -> discord.ui.Select:
            menu = discord.ui.Select(placeholder="Select a field", row=3, custom_id="field_menu")
            return menu

        num_buttons = {
            "num_rem_5": {
                "style": discord.ButtonStyle.red,
                "label": "- 5"
            },
            "num_rem_1": {
                "style": discord.ButtonStyle.blurple,
                "label": "- 1"
            },
            "num_field": {
                "style": discord.ButtonStyle.gray,
                "emoji": "🔎",
                "label": "0"
            },
            "num_add_1": {
                "style": discord.ButtonStyle.blurple,
                "label": "+ 1"
            },
            "num_add_5": {
                "style": discord.ButtonStyle.green,
                "label": "+ 5"
            }
        }

        def gen_num_row() -> list[discord.ui.Button]:
            generated_buttons = []
            for button_id, button_data in num_buttons.items():
                button = discord.ui.Button(
                    style=button_data["style"],
                    label=button_data["label"],
                    emoji=button_data.get("emoji"),
                    custom_id=button_id,
                    row=4
                )
                generated_buttons.append(button)
            return generated_buttons

        attr_menu = gen_attr_menu()

        async def select_callback(interaction: discord.Interaction):
            selected_attribute = interaction.data["values"][0]
            embed = discord.Embed(title=item_name)

            # cleanup
            field_menu = view.get_item("field_menu")
            view.remove_item(field_menu)

            for button_id in num_buttons:
                button = view.get_item(button_id)
                view.remove_item(button)

            new_field_menu = gen_field_menu()

            attribute_values = self.scrapper.get_attribute_values(item_id, selected_attribute)

            if isinstance(attribute_values, dict):
                for k, values in attribute_values.items():
                    embed.add_field(name=k, value=str(values))
                    new_field_menu.add_option(
                        label=k
                    )
            else:
                embed.add_field(name="value", value=str(attribute_values))
                if all(isinstance(value, int) for value in attribute_values):
                    if len(attribute_values) > 25 or max(attribute_values) > 10:  # range
                        for button in gen_num_row():
                            view.add_item(button)

                        num_field_button: discord.ui.Button = view.get_item("num_field")
                        num_field_button.label = f"0 / {max(attribute_values)}"
                    else:  # roman numerals
                        pass
                else:
                    for value in attribute_values:
                        new_field_menu.add_option(
                            label=str(value)
                        )
                    view.add_item(new_field_menu)

            select_menu = view.get_item("select_menu")
            view.remove_item(select_menu)

            new_select_menu = gen_attr_menu(selected_attribute)
            new_select_menu.callback = select_callback
            view.add_item(new_select_menu)

            await interaction.edit(embed=embed, view=view)

        attr_menu.callback = select_callback
        view.add_item(attr_menu)

        await ctx.respond(embed=embed, view=view)

    @discord.slash_command()
    async def ahstats(
            self,
            ctx: discord.ApplicationContext,
            item_name: str = discord.Option(
                autocomplete=discord.utils.basic_autocomplete(item_id_autocomplete),
                required=True,
            ),
            bin: bool = discord.Option(bool, required=False),
    ):
        def format_output(num: float):  # god bless stack overflow
            magnitude: int = 0
            while abs(num) >= 1000:
                magnitude += 1
                num /= 1000

            return f"{round(num, 2)} {['', 'K', 'M', 'B'][magnitude]}"

        auctions: dict = self.scrapper.get_index()
        item_id: str = item_name.replace(" ", "_").upper()
        filtered = [
            auction["starting_bid"] if (auction["bin"] or auction["highest_bid_amount"] == 0) else auction[
                "highest_bid_amount"]
            for auction in auctions[item_id]["entries"].values()
            if (bin is None or auction["bin"] == bin)
        ]

        await ctx.defer()

        embed = discord.Embed(title=item_id)

        fields = {
            "Count": len(filtered),
            "Cheapest": min(filtered),
            "Expensive": max(filtered),
            "Mean": mean(filtered),
            "Median": median(filtered),
            "Mode": mode(filtered)
        }

        for name, value in fields.items():
            embed.add_field(name=name, value=format_output(value), inline=False)

        await ctx.respond(embed=embed)

    @discord.slash_command()
    async def find_most(self, ctx: discord.ApplicationContext):
        index = self.scrapper.get_index
        table = {len(index[item_id]["auctions"]): item_id for item_id in index}
        most = max(table)

        await ctx.respond(f"{table[most]}: {most}")

def setup(bot):
    bot.add_cog(Auctions(bot))
