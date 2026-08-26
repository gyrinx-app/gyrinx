"""The wealth strip: the money figures, the one that can have no answer,
and the Trade Points that are not money at all.

No database — a component is a template and a set of props, and what a gang
with no budget shows is decided before a request exists. The strip is drawn
from a Gang on some screens and from a rendered GangSheet on others, so both
are stood in for here by plain objects carrying the same names: what matters
is that the two cannot disagree, because both are asked the same question.
"""

from types import SimpleNamespace

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str, **context) -> str:
    """Compile a call site the way the loader would, then render it."""
    return Template(CottonCompiler().process(source)).render(Context(context))


def gang(**overrides):
    figures = {
        "rating": 500,
        "credits": 120,
        "stash_rating": 30,
        "wealth": 650,
        "credits_unlimited": False,
        "trade_points_left": 0,
        "visiting_trading_post": True,
    }
    return SimpleNamespace(**(figures | overrides))


def strip(**overrides) -> str:
    return render(
        '<c-n26.wealth :sheet="sheet" />',
        sheet=gang(**overrides),
    )


class TestTheFigures:
    def test_all_four_are_drawn_in_the_order_of_the_sum(self):
        html = strip()
        assert [
            html.index("500¢"),
            html.index("120¢"),
            html.index("30¢"),
            html.index("650¢"),
        ] == sorted(
            [
                html.index("500¢"),
                html.index("120¢"),
                html.index("30¢"),
                html.index("650¢"),
            ]
        )

    def test_a_gang_that_has_spent_everything_reads_nought(self):
        """Nought credits is a figure, not an absence: the gang had a budget
        and has used it, which is exactly the state the em dash must not be
        confused with."""
        html = strip(credits=0)
        assert "0¢" in html
        assert "Unlimited credits" not in html


class TestTradePoints:
    """Not money, and not part of the sum beside them: what the gang may
    spend at a trading post until the trip ends. They lead the strip, cut
    off from the money by a rule of their own, and carry no unit."""

    def test_they_are_drawn_before_every_money_figure(self):
        html = strip(trade_points_left=4)
        assert html.index(">4<") < html.index("500¢")

    def test_they_carry_no_currency(self):
        html = strip(trade_points_left=4)
        assert ">4<" in html
        assert "4¢" not in html

    def test_a_rule_separates_them_from_the_money(self):
        assert "border-r" in strip()

    def test_a_gang_that_overspent_shows_what_it_owes(self):
        """Overspending is allowed — the purchase asks first — so the
        figure has to be able to go below nought and say so."""
        html = strip(trade_points_left=-2)
        assert ">-2<" in html

    def test_no_action_open_draws_a_dash_rather_than_a_nought(self):
        """The post is shut to a gang whose fighters have not visited it,
        which is a different state from a visit that has spent everything
        — and a nought would read as the second."""
        html = strip(trade_points_left=None, visiting_trading_post=False)
        assert "No Visit Trading Post action open" in html
        assert "&mdash;" in html or "—" in html

    def test_a_visit_that_has_spent_everything_still_reads_nought(self):
        html = strip(trade_points_left=0, visiting_trading_post=True)
        assert ">0<" in html
        assert "No Visit Trading Post action open" not in html


class TestAGangWithNoBudget:
    """Founding without a ceiling is a real state — the player buys what they
    own and the gang's number is its rating — and in it the credits figure
    counts nothing."""

    def test_the_credits_figure_says_so_instead_of_showing_a_number(self):
        html = strip(credits=0, credits_unlimited=True)
        assert "Unlimited credits" in html
        assert "&mdash;" in html or "—" in html

    def test_the_other_three_figures_are_unaffected(self):
        html = strip(credits_unlimited=True)
        assert "500¢" in html
        assert "30¢" in html
        assert "650¢" in html

    def test_something_that_never_heard_the_question_keeps_its_number(self):
        """The flag is asked positively, so a caller passing figures with no
        such attribute draws the credits it always drew rather than silently
        turning every gang's credits into a dash."""
        html = render(
            '<c-n26.wealth :sheet="sheet" />',
            sheet=SimpleNamespace(rating=500, credits=120, stash_rating=30, wealth=650),
        )
        assert "120¢" in html
        assert "Unlimited credits" not in html


class TestTheCount:
    """The count stands beside the strip in <c-n26.gang-figures> as the
    control that opens the roster's own tally, and it counts models rather
    than money."""

    def figures(self, count=9) -> str:
        from n26.core.render import RosterGroup, RosterLine, RosterSummary

        return render(
            '<c-n26.gang-figures :gang="sheet" :summary="summary" />',
            sheet=gang(),
            summary=RosterSummary(
                groups=[RosterGroup(profile="Ganger", category="Ganger", count=count)],
                models=[RosterLine(name=f"Model {n}", rating=55) for n in range(count)],
                count=count,
                rating=55 * count,
            ),
        )

    def test_the_count_carries_no_currency(self):
        html = self.figures()
        assert ">9<" in html
        assert "9¢" not in html

    def test_the_count_is_the_control_that_opens_the_tally(self):
        """One thing to look at and one thing to click: the figure a reader
        glances at is the button holding the breakdown behind it."""
        html = self.figures()
        assert "Models in the gang" in html
        assert "Roster breakdown: 9 models in the gang" in html

    def test_a_gang_of_one_is_not_announced_as_one_models(self):
        html = self.figures(count=1)
        assert "Roster breakdown: 1 model in the gang" in html

    def test_the_count_comes_off_the_tally_it_opens(self):
        """Nothing is told the count separately, so the number on the button
        and the total in the tally cannot fall out of step."""
        html = self.figures(count=3)
        assert ">3<" in html
        assert "3 models in the gang" in html
