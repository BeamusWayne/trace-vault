"""The ``vault`` command-line interface.

Commands
--------
* ``vault gate --baseline b.json`` — run the reference suite and gate it; exit 1
  on any regression. This is what CI runs.
* ``vault eval [--full]`` — run a suite and print the dual-axis report.
* ``vault demo`` — the headline: green suite, then two regressions the gate
  catches on two independent axes.
* ``vault version`` — print the version.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import typer

from . import __version__
from .agent import Agent, default_registry
from .gate import Baseline, load_baseline, render_gate, run_gate
from .suite import full_suite, good_suite

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="trace-vault — a record/replay reliability gate for tool-using agents.",
)

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
}


def _use_color() -> bool:
    # Color only on a real terminal; CI captures (and NO_COLOR) stay plain, so
    # the report text the tests assert on is unchanged.
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _style(text: str) -> str:
    if not _use_color():
        return text
    g, r, y, b, z = (_ANSI[k] for k in ("green", "red", "yellow", "bold", "reset"))
    out: list[str] = []
    for line in text.split("\n"):
        if line.startswith("GATE: PASS"):
            out.append(f"{b}{g}{line}{z}")
        elif line.startswith("GATE: FAIL"):
            out.append(f"{b}{r}{line}{z}")
        else:
            out.append(
                line.replace("PASS", f"{g}PASS{z}")
                .replace("FAIL", f"{r}FAIL{z}")
                .replace("*", f"{y}*{z}")
            )
    return "\n".join(out)


def _echo_report(text: str) -> None:
    typer.echo(_style(text))


def _agent() -> Agent:
    return Agent(default_registry())


@app.command()
def version() -> None:
    """Print the trace-vault version."""
    typer.echo(__version__)


@app.command()
def gate(
    baseline: Path = typer.Option(..., "--baseline", "-b", help="Path to baseline JSON."),
    full: bool = typer.Option(
        False, "--full", "-f", help="Also gate the red-path scenarios (expected to fail)."
    ),
    runs: int = typer.Option(20, help="Replays per scenario."),
    k: int = typer.Option(5, help="k for pass^k / pass@k."),
    seed: int = typer.Option(0, help="Bootstrap / sampling seed."),
) -> None:
    """Run the reference suite and gate it against a frozen baseline."""
    base = load_baseline(baseline)
    cases = full_suite() if full else good_suite()
    with tempfile.TemporaryDirectory() as tmp:
        report = run_gate(cases, _agent(), base, root=tmp, runs=runs, k=k, seed=seed)
    _echo_report(render_gate(report))
    raise typer.Exit(0 if report.passed else 1)


@app.command("eval")
def eval_cmd(
    full: bool = typer.Option(False, "--full", help="Include the red-path scenarios."),
    runs: int = typer.Option(20, help="Replays per scenario."),
    k: int = typer.Option(5),
    seed: int = typer.Option(0),
) -> None:
    """Run a suite and print the dual-axis report (no gating)."""
    cases = full_suite() if full else good_suite()
    with tempfile.TemporaryDirectory() as tmp:
        report = run_gate(cases, _agent(), Baseline(), root=tmp, runs=runs, k=k, seed=seed)
    _echo_report(render_gate(report))


@app.command()
def demo(runs: int = typer.Option(12, help="Replays per scenario.")) -> None:
    """Show that determinism and faithfulness are independent — and both gated."""
    agent = _agent()
    base = Baseline()
    typer.echo("trace-vault demo  ·  determinism is not faithfulness\n")
    with tempfile.TemporaryDirectory() as tmp:
        good = run_gate(good_suite(), agent, base, root=f"{tmp}/g", runs=runs)
        typer.echo("[1] The committed reference suite replays GREEN, offline, no key:\n")
        _echo_report(render_gate(good))
        full = run_gate(full_suite(), agent, base, root=f"{tmp}/f", runs=runs)
        typer.echo("\n[2] Add two regressions — the gate catches BOTH, on different axes:\n")
        _echo_report(render_gate(full))
    typer.echo(
        "\nTakeaway:\n"
        "  report.flaky_plan        is reproducible-broken  -> caught by DETERMINISM\n"
        "  booking.unfaithful_write is reliable-but-wrong    -> caught by FAITHFULNESS\n"
        "A single collapsed score would have hidden one of them."
    )


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
