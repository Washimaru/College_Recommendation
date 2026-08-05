"""CLI entrypoint (§7): `python -m faculty_pipeline <command> [OPTS]`.

Stage subcommands (`load`/`discover`/`crawl`/`extract`/`export`/`all`) are
wired to their stage module's `run()` starting in Milestone 2 — the stage
modules currently raise `NotImplementedError`, so each subcommand reports
that clearly and exits non-zero rather than pretending to do work. `status`
and `clean` are fully implemented now: they only touch `services.checkpoint`
and the filesystem, not the (not-yet-built) stages.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from .config import Config
from .services.checkpoint import CheckpointStore
from .services.logging_setup import configure_logging
from .stages import load_filter

CHECKPOINTED_STAGES = ("discover", "crawl", "extract")


@click.group()
@click.option(
    "--config",
    "config_path",
    default="config/pipeline.yaml",
    show_default=True,
    type=click.Path(),
    help="Path to pipeline.yaml",
)
@click.option(
    "--input",
    "input_override",
    default=None,
    type=click.Path(),
    help="Override school_details.json path",
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
)
@click.option("--dry-run", is_flag=True, default=False, help="Plan only; no network / no writes")
@click.pass_context
def main(
    ctx: click.Context,
    config_path: str,
    input_override: str | None,
    log_level: str,
    dry_run: bool,
) -> None:
    """Faculty directory crawl + extraction pipeline."""
    cfg = Config.load(config_path)
    if input_override is not None:
        cfg = cfg.with_overrides(input_path=Path(input_override))
    logger = configure_logging(cfg.log_dir, level=log_level)
    ctx.obj = {"config": cfg, "logger": logger, "dry_run": dry_run}


def _not_implemented(stage: str, milestone: int) -> None:
    click.echo(
        f"stage {stage!r} is not implemented yet (lands in Milestone {milestone}).",
        err=True,
    )
    sys.exit(1)


@main.command()
@click.pass_context
def load(ctx: click.Context) -> None:
    """Stage 1: load & filter US schools."""
    config: Config = ctx.obj["config"]
    logger = ctx.obj["logger"]
    dry_run: bool = ctx.obj["dry_run"]

    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / f"{load_filter.STAGE_NAME}.json")
    try:
        summary = load_filter.run(config, checkpoint, logger, dry_run=dry_run)
    except load_filter.LoadFilterError as exc:
        click.echo(f"load failed: {exc}", err=True)
        sys.exit(1)

    prefix = "[dry-run] " if dry_run else ""
    click.echo(
        f"{prefix}load: {summary.processed} schools written, "
        f"{summary.skipped} skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")


@main.command()
@click.option("--limit", type=int, default=None, help="Process at most N schools")
@click.option("--school", "school_id", default=None, help="Run a single school")
@click.pass_context
def discover(ctx: click.Context, limit: int | None, school_id: str | None) -> None:
    """Stage 2: find faculty directories."""
    _not_implemented("discover", 3)


@main.command()
@click.option("--limit", type=int, default=None)
@click.option("--school", "school_id", default=None)
@click.option("--dynamic", is_flag=True, default=False, help="Enable headless-browser fallback")
@click.pass_context
def crawl(ctx: click.Context, limit: int | None, school_id: str | None, dynamic: bool) -> None:
    """Stage 3: crawl professor profiles."""
    _not_implemented("crawl", 4)


@main.command()
@click.option("--school", "school_id", default=None)
@click.option("--no-llm", is_flag=True, default=False, help="Deterministic pass only (debug)")
@click.pass_context
def extract(ctx: click.Context, school_id: str | None, no_llm: bool) -> None:
    """Stage 4: extract + LLM-normalize."""
    _not_implemented("extract", 5)


@main.command()
@click.pass_context
def export(ctx: click.Context) -> None:
    """Stage 5: write per-school + master CSVs."""
    _not_implemented("export", 6)


@main.command(name="all")
@click.option("--resume/--no-resume", default=True, help="Skip checkpointed work (default true)")
@click.option("--force", is_flag=True, default=False, help="Ignore checkpoints and reprocess")
@click.pass_context
def run_all(ctx: click.Context, resume: bool, force: bool) -> None:
    """Run stages 1 through 5 in order."""
    _not_implemented("all", 6)


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Print checkpoint/progress summary."""
    config: Config = ctx.obj["config"]
    checkpoint_dir = Path(config.checkpoint_dir)
    if not checkpoint_dir.exists():
        click.echo("no checkpoints yet")
        return
    for stage in CHECKPOINTED_STAGES:
        store = CheckpointStore(checkpoint_dir / f"{stage}.json")
        counts = store.summary()
        click.echo(f"{stage}: {counts if counts else 'no entries'}")


@main.command()
@click.option("--yes", is_flag=True, default=False, help="Confirm deletion")
@click.pass_context
def clean(ctx: click.Context, yes: bool) -> None:
    """Clear cache/ and checkpoints/."""
    if not yes:
        click.echo("pass --yes to confirm deleting cache/ and checkpoints/", err=True)
        sys.exit(1)
    config: Config = ctx.obj["config"]
    for directory in (config.cache_dir, config.checkpoint_dir):
        shutil.rmtree(directory, ignore_errors=True)
    click.echo("cleared cache/ and checkpoints/")


if __name__ == "__main__":
    main()
