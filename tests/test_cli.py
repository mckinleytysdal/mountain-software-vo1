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
