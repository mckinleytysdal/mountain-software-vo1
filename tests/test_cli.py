import pytest

from mountain_software.cli import build_parser


@pytest.mark.parametrize(
    "argv",
    [
        ["routes", "load"],
        ["weather", "cells"],
        ["weather", "collect"],
        ["weather", "backfill", "--region", "burstall", "--start", "2026-10-01"],
        ["terrain", "compute", "--route", "x"],
        ["exposure", "run", "--route", "x", "--as-of", "2026-10-16T06:00"],
    ],
)
def test_commands_parse(argv):
    args = build_parser().parse_args(argv)
    assert callable(args.func)


def test_rate_limit_is_reported_not_crashed(monkeypatch, capsys):
    from mountain_software import cli
    from mountain_software.weather import openmeteo

    def boom(args):
        raise openmeteo.RateLimited("Daily API request limit exceeded.")

    parser = cli.build_parser()
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    parser._subparsers._group_actions[0].choices["weather"]._subparsers._group_actions[0].choices["cells"].set_defaults(func=boom)
    assert cli.main(["weather", "cells"]) == 2
    assert "rate limit" in capsys.readouterr().out
