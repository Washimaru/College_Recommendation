"""CLI entrypoint (§7): `python -m faculty_pipeline <command> [OPTS]`.

Stage subcommands (`load`/`discover`/`crawl`/`extract`/`export`/`all`) are
wired to their stage module's `run()` as each landed: `load` (M2), `discover`
(M3), `crawl` (M4), `extract` (M5), `export` and `all` (M6, this build).
`status` and `clean` were implemented ahead of their milestone (they only
touch `services.checkpoint` and the filesystem, not the stages); `status` is
reshaped here into a genuinely readable per-stage progress report (§9) now
that all five stages have real checkpoints/artifacts to report against,
rather than the raw counts dict it printed before.
"""
from __future__ import annotations

import csv
import dataclasses
import json
import shutil
import sys
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import click
import httpx

from .config import Config
from .services.checkpoint import CheckpointStore
from .services.dynamic import PlaywrightRenderer, RendererUnavailableError
from .services.http_client import HttpClient
from .services.llm import AnthropicLLM
from .services.logging_setup import configure_logging
from .services.openalex import OpenAlexApi, polite_user_agent
from .services.robots import RobotsChecker
from .services.search import build_search_provider
from .services.wikimedia import ApiRobots, MediaWikiApi
from .stages import active_faculty as active_stage
from .stages import crawl as crawl_stage
from .stages import discover as discover_stage
from .stages import export as export_stage
from .stages import extract as extract_stage
from .stages import load_filter
from .stages import notable as notable_stage

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
    config: Config = ctx.obj["config"]
    logger = ctx.obj["logger"]
    dry_run: bool = ctx.obj["dry_run"]

    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / f"{discover_stage.STAGE_NAME}.json")

    # follow_redirects: a heuristic/search candidate that 30x's to its real
    # location (very common for university sites) must resolve to that final
    # page, not be rejected for a non-200 redirect status.
    transport = httpx.Client(follow_redirects=True)
    try:
        robots = RobotsChecker(transport)
        http_client = HttpClient(config, robots, transport)
        search_provider = build_search_provider(config)
        llm = AnthropicLLM(config)
        try:
            summary = discover_stage.run(
                config,
                checkpoint,
                logger,
                http_client,
                search_provider,
                llm,
                robots,
                limit=limit,
                school_id=school_id,
                dry_run=dry_run,
            )
        except discover_stage.DiscoverError as exc:
            click.echo(f"discover failed: {exc}", err=True)
            sys.exit(1)
    finally:
        transport.close()

    prefix = "[dry-run] " if dry_run else ""
    click.echo(
        f"{prefix}discover: {summary.processed} schools processed, "
        f"{summary.skipped} skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")


@main.command()
@click.option("--limit", type=int, default=None, help="Process at most N schools")
@click.option("--school", "school_id", default=None, help="Run a single school")
@click.option(
    "--dynamic",
    is_flag=True,
    default=False,
    help="Re-read JS-rendered directories through headless Chromium (needs .[dynamic])",
)
@click.option(
    "--max-profiles",
    type=int,
    default=None,
    help="Override max_profiles_per_school for this run only (the 2s/host floor is unchanged)",
)
@click.pass_context
def crawl(
    ctx: click.Context,
    limit: int | None,
    school_id: str | None,
    dynamic: bool,
    max_profiles: int | None,
) -> None:
    """Stage 3: crawl professor profiles."""
    config: Config = ctx.obj["config"]
    if max_profiles is not None:
        # Per run, deliberately: the default is conservative because 268
        # schools x a high cap is days of someone else's bandwidth. Raising it
        # for one school whose directory is known to be worth it is a decision
        # someone makes at the command line, not a new default.
        config = replace(config, max_profiles_per_school=max_profiles)
    logger = ctx.obj["logger"]
    dry_run: bool = ctx.obj["dry_run"]

    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / f"{crawl_stage.STAGE_NAME}.json")

    # follow_redirects: a directory or profile URL that 30x's to its real
    # location must resolve there, not be rejected for a non-200 status.
    transport = httpx.Client(follow_redirects=True)
    try:
        robots = RobotsChecker(transport)
        http_client = HttpClient(config, robots, transport)
        # The browser is started once for the whole run and only when asked
        # for: launching Chromium costs seconds, and most schools never need
        # it. ExitStack keeps the non-dynamic path free of a dummy context.
        with ExitStack() as stack:
            renderer = None
            if dynamic:
                try:
                    renderer = stack.enter_context(
                        PlaywrightRenderer(
                            user_agent=config.user_agent,
                            timeout_seconds=config.request_timeout * 2,
                            delay_seconds=config.rate_limit_per_host,
                            logger=logger,
                        )
                    )
                except RendererUnavailableError as exc:
                    click.echo(f"crawl failed: {exc}", err=True)
                    sys.exit(1)
            try:
                summary = crawl_stage.run(
                    config,
                    checkpoint,
                    logger,
                    http_client,
                    limit=limit,
                    school_id=school_id,
                    dynamic=dynamic,
                    renderer=renderer,
                    dry_run=dry_run,
                )
            except crawl_stage.CrawlError as exc:
                click.echo(f"crawl failed: {exc}", err=True)
                sys.exit(1)
    finally:
        transport.close()

    prefix = "[dry-run] " if dry_run else ""
    click.echo(
        f"{prefix}crawl: {summary.processed} profile(s) fetched, "
        f"{summary.skipped} skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")


@main.command()
@click.option("--limit", type=int, default=None, help="Process at most N profiles")
@click.option("--school", "school_id", default=None)
@click.option("--no-llm", is_flag=True, default=False, help="Deterministic pass only (debug)")
@click.pass_context
def extract(ctx: click.Context, limit: int | None, school_id: str | None, no_llm: bool) -> None:
    """Stage 4: extract + LLM-normalize."""
    config: Config = ctx.obj["config"]
    logger = ctx.obj["logger"]
    dry_run: bool = ctx.obj["dry_run"]

    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / f"{extract_stage.STAGE_NAME}.json")
    llm = None if no_llm else AnthropicLLM(config)

    try:
        summary = extract_stage.run(
            config,
            checkpoint,
            logger,
            llm,
            limit=limit,
            school_id=school_id,
            no_llm=no_llm,
            dry_run=dry_run,
        )
    except extract_stage.ExtractError as exc:
        click.echo(f"extract failed: {exc}", err=True)
        sys.exit(1)

    prefix = "[dry-run] " if dry_run else ""
    click.echo(
        f"{prefix}extract: {summary.processed} profile(s) extracted, "
        f"{summary.skipped} skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")


@main.command()
@click.pass_context
def export(ctx: click.Context) -> None:
    """Stage 5: write per-school + master CSVs."""
    config: Config = ctx.obj["config"]
    logger = ctx.obj["logger"]
    dry_run: bool = ctx.obj["dry_run"]

    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / f"{export_stage.STAGE_NAME}.json")
    try:
        summary = export_stage.run(config, checkpoint, logger, dry_run=dry_run)
    except export_stage.ExportError as exc:
        click.echo(f"export failed: {exc}", err=True)
        sys.exit(1)

    prefix = "[dry-run] " if dry_run else ""
    click.echo(
        f"{prefix}export: {summary.processed} professor(s) written, "
        f"{summary.skipped} skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")


@main.command(name="all")
@click.option("--resume/--no-resume", default=True, help="Skip checkpointed work (default true)")
@click.option("--force", is_flag=True, default=False, help="Ignore checkpoints and reprocess")
@click.pass_context
def run_all(ctx: click.Context, resume: bool, force: bool) -> None:
    """Run stages 1 through 5 in order (§7).

    `--resume`/`--no-resume` and `--force` name the same lever the doc's two
    bullets describe separately: whether a checkpointed stage (discover/
    crawl/extract) picks up where it left off. Here `--force` and
    `--no-resume` do the same thing — delete that stage's checkpoint file
    before running it, so every item is retried from scratch — because nothing
    in §7 distinguishes a "skip resuming for this run" mode from "erase and
    start over"; inventing two different mechanisms for an underspecified
    pair of flags would be undocumented behavior no one asked for. This *is*
    destructive to checkpoint history (unlike `clean`, it does not require
    `--yes`, since `--force` is itself the explicit ask) and is called out
    plainly before it runs. It also does not touch the append-only
    `data/*.jsonl` files those checkpoints gate, so reprocessing an
    already-`done` item appends a duplicate row rather than replacing one —
    there is no compaction pass (§9 names one as aspirational, not
    implemented); that risk is stated up front rather than silently eaten.

    In `--dry-run`, a stage whose required upstream artifact doesn't exist
    yet (e.g. `discover` needs `data/schools.jsonl`, which plain `load
    --dry-run` never writes — dry runs don't write anything, by design)
    stops the chain with a clear note and exit code 0 instead of a stack
    trace, so `--dry-run all` can plan from a completely empty environment
    (§11's smoke test) as well as from a partially-run one.
    """
    config: Config = ctx.obj["config"]
    logger = ctx.obj["logger"]
    dry_run: bool = ctx.obj["dry_run"]
    prefix = "[dry-run] " if dry_run else ""

    checkpoint_dir = Path(config.checkpoint_dir)
    if force or not resume:
        removed = []
        for stage_name in CHECKPOINTED_STAGES:
            path = checkpoint_dir / f"{stage_name}.json"
            if path.exists():
                path.unlink()
                removed.append(str(path))
        if removed:
            click.echo(f"--force: cleared checkpoint(s): {', '.join(removed)}")
        click.echo(
            "note: discover/crawl/extract append to their data/*.jsonl files; forcing a "
            "reprocess of already-done items can append duplicate rows (no compaction pass "
            "exists yet)."
        )

    # -- Stage 1: load ----------------------------------------------------
    checkpoint = CheckpointStore(checkpoint_dir / f"{load_filter.STAGE_NAME}.json")
    try:
        summary = load_filter.run(config, checkpoint, logger, dry_run=dry_run)
    except load_filter.LoadFilterError as exc:
        click.echo(f"all: load failed: {exc}", err=True)
        sys.exit(1)
    click.echo(
        f"{prefix}load: {summary.processed} schools written, {summary.skipped} skipped, "
        f"{summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")

    # -- Stages 2-3: discover, crawl (share one HTTP transport) -----------
    # llm/search_provider are only constructed for real when not dry_run:
    # both stages' dry_run branch returns before touching either, and
    # constructing a real AnthropicLLM would require ANTHROPIC_API_KEY even
    # though a planning-only run makes no LLM calls.
    transport = httpx.Client(follow_redirects=True)
    try:
        robots = RobotsChecker(transport)
        http_client = HttpClient(config, robots, transport)
        search_provider = build_search_provider(config)
        llm = None if dry_run else AnthropicLLM(config)

        checkpoint = CheckpointStore(checkpoint_dir / f"{discover_stage.STAGE_NAME}.json")
        try:
            summary = discover_stage.run(
                config,
                checkpoint,
                logger,
                http_client,
                search_provider,
                llm,  # type: ignore[arg-type]
                robots,
                dry_run=dry_run,
            )
        except discover_stage.DiscoverError as exc:
            if dry_run:
                click.echo(f"{prefix}discover: cannot plan yet — {exc}")
                return
            click.echo(f"all: discover failed: {exc}", err=True)
            sys.exit(1)
        click.echo(
            f"{prefix}discover: {summary.processed} schools processed, {summary.skipped} "
            f"skipped, {summary.failed} failed"
        )
        for note in summary.notes:
            click.echo(f"  note: {note}")

        checkpoint = CheckpointStore(checkpoint_dir / f"{crawl_stage.STAGE_NAME}.json")
        try:
            summary = crawl_stage.run(config, checkpoint, logger, http_client, dry_run=dry_run)
        except crawl_stage.CrawlError as exc:
            if dry_run:
                click.echo(f"{prefix}crawl: cannot plan yet — {exc}")
                return
            click.echo(f"all: crawl failed: {exc}", err=True)
            sys.exit(1)
        click.echo(
            f"{prefix}crawl: {summary.processed} profile(s) fetched, {summary.skipped} "
            f"skipped, {summary.failed} failed"
        )
        for note in summary.notes:
            click.echo(f"  note: {note}")
    finally:
        transport.close()

    # -- Stage 4: extract --------------------------------------------------
    checkpoint = CheckpointStore(checkpoint_dir / f"{extract_stage.STAGE_NAME}.json")
    try:
        summary = extract_stage.run(
            config,
            checkpoint,
            logger,
            None if dry_run else AnthropicLLM(config),
            no_llm=dry_run,  # dry_run's early return never branches on this; it only
            # avoids extract's `llm is None` guard without needing a real API key.
            dry_run=dry_run,
        )
    except extract_stage.ExtractError as exc:
        if dry_run:
            click.echo(f"{prefix}extract: cannot plan yet — {exc}")
            return
        click.echo(f"all: extract failed: {exc}", err=True)
        sys.exit(1)
    click.echo(
        f"{prefix}extract: {summary.processed} profile(s) extracted, {summary.skipped} "
        f"skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")

    # -- Stage 5: export ----------------------------------------------------
    checkpoint = CheckpointStore(checkpoint_dir / f"{export_stage.STAGE_NAME}.json")
    try:
        summary = export_stage.run(config, checkpoint, logger, dry_run=dry_run)
    except export_stage.ExportError as exc:
        if dry_run:
            click.echo(f"{prefix}export: cannot plan yet — {exc}")
            return
        click.echo(f"all: export failed: {exc}", err=True)
        sys.exit(1)
    click.echo(
        f"{prefix}export: {summary.processed} professor(s) written, {summary.skipped} "
        f"skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Print a per-stage progress report (§9): done/failed/pending for the
    three checkpointed stages (discover/crawl/extract), plus artifact-based
    status for the two that aren't (load overwrites `data/schools.jsonl`
    wholesale each run; export overwrites `output/*.csv` the same way — §9
    lists only discover/crawl/extract as checkpointed)."""
    config: Config = ctx.obj["config"]
    data_dir = Path(config.data_dir)
    checkpoint_dir = Path(config.checkpoint_dir)

    click.echo("== faculty-pipeline status ==")
    click.echo(_load_status_line(data_dir))
    click.echo(
        _checkpoint_status_line(
            checkpoint_dir,
            discover_stage.STAGE_NAME,
            pool=_count_jsonl_lines(data_dir / "schools.jsonl"),
            pool_label="school(s) in data/schools.jsonl",
        )
    )
    click.echo(
        _checkpoint_status_line(
            checkpoint_dir,
            crawl_stage.STAGE_NAME,
            # Unlike discover/extract, crawl's item pool (enumerated profile
            # URLs) isn't fixed in advance — it's rediscovered by
            # re-enumerating each school's directory on every run, so there
            # is no "of N" total to report a meaningful `pending` against.
            pool=None,
            pool_label="profile url(s); pool is re-enumerated each run, not fixed",
        )
    )
    click.echo(
        _checkpoint_status_line(
            checkpoint_dir,
            extract_stage.STAGE_NAME,
            pool=_count_jsonl_lines(data_dir / "profiles_raw.jsonl"),
            pool_label="raw profile(s) in data/profiles_raw.jsonl",
        )
    )
    click.echo(_export_status_line(Path(config.output_dir)))


def _count_jsonl_lines(path: Path) -> int | None:
    """`None` (not `0`) when the file doesn't exist, so callers can tell
    "not run yet" apart from "ran, produced nothing"."""
    if not path.exists():
        return None
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _load_status_line(data_dir: Path) -> str:
    count = _count_jsonl_lines(data_dir / "schools.jsonl")
    if count is None:
        return "load     : not run yet (no data/schools.jsonl)"
    return (
        f"load     : {count} school(s) in data/schools.jsonl "
        "(not checkpointed; overwritten each run)"
    )


def _checkpoint_status_line(
    checkpoint_dir: Path, stage: str, *, pool: int | None, pool_label: str
) -> str:
    path = checkpoint_dir / f"{stage}.json"
    if not path.exists():
        return f"{stage:9s}: not run yet (no checkpoints/{stage}.json)"
    counts = CheckpointStore(path).summary()
    done = counts.get("done", 0)
    failed = counts.get("failed", 0)
    if pool is None:
        return f"{stage:9s}: done {done}, failed {failed}  ({pool_label})"
    pending = max(pool - done - failed, 0)
    return f"{stage:9s}: done {done}, failed {failed}, pending {pending}  (of {pool} {pool_label})"


def _export_status_line(output_dir: Path) -> str:
    master_path = output_dir / "master.csv"
    if not master_path.exists():
        return "export   : not run yet (no output/master.csv)"
    with master_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    schools = {row["school_id"] for row in rows}
    line = (
        f"export   : {len(rows)} professor(s) across {len(schools)} school(s) "
        "in output/master.csv"
    )
    coverage_path = output_dir / "coverage.csv"
    if coverage_path.exists():
        with coverage_path.open(newline="", encoding="utf-8") as f:
            coverage_rows = list(csv.DictReader(f))
        incomplete = sum(1 for row in coverage_rows if row.get("incomplete") == "true")
        line += (
            f"; {incomplete} of {len(coverage_rows)} school(s) with clean data incomplete "
            "— see output/coverage.csv"
        )
    return line


@main.command()
@click.option("--yes", is_flag=True, default=False, help="Confirm deletion")
@click.pass_context
def clean(ctx: click.Context, yes: bool) -> None:
    """Clear cache/ and checkpoints/ (§7). Destructive and irreversible —
    refuses without `--yes`, and states exactly which directories it will
    remove before doing anything."""
    config: Config = ctx.obj["config"]
    cache_dir = Path(config.cache_dir)
    checkpoint_dir = Path(config.checkpoint_dir)

    if not yes:
        click.echo(
            f"this will permanently delete {cache_dir}/ and {checkpoint_dir}/ "
            "(HTML/search/LLM cache and all stage checkpoints). "
            "Re-run with --yes to confirm.",
            err=True,
        )
        sys.exit(1)

    for directory in (cache_dir, checkpoint_dir):
        shutil.rmtree(directory, ignore_errors=True)
    click.echo(f"cleared {cache_dir}/ and {checkpoint_dir}/")


if __name__ == "__main__":
    main()


@main.command()
@click.option("--limit", type=int, default=None, help="Process at most N schools")
@click.option("--school", "school_id", default=None, help="Run a single school")
@click.option("--per-school", type=int, default=notable_stage.DEFAULT_LIMIT,
              help="Cap professors kept per school (default 20)")
@click.option("--tier-out", default="../data-pipeline/sources/notable_faculty.json",
              help="Where to fold the results for the catalog build")
@click.option("--write-tier/--no-write-tier", default=True,
              help="Write the committed tier file after the run")
@click.pass_context
def notable(
    ctx: click.Context,
    limit: int | None,
    school_id: str | None,
    per_school: int,
    tier_out: str,
    write_tier: bool,
) -> None:
    """Notable faculty: named professors per school, from Wikipedia + Wikidata."""
    config: Config = ctx.obj["config"]
    logger = ctx.obj["logger"]
    dry_run: bool = ctx.obj["dry_run"]

    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / f"{notable_stage.STAGE_NAME}.json")

    transport = httpx.Client(follow_redirects=True)
    try:
        # ApiRobots exempts exactly the two API endpoints and delegates every
        # other URL to the real checker - see services/wikimedia.py for why the
        # API is not what robots.txt's `Disallow: /w/` is aimed at. Everything
        # else (rate limit, cache, backoff) is the ordinary client.
        robots = ApiRobots(RobotsChecker(transport))
        http_client = HttpClient(config, robots, transport)
        api = MediaWikiApi(http_client, logger)
        try:
            summary = notable_stage.run(
                config, checkpoint, logger, api,
                limit=limit, school_id=school_id, per_school=per_school, dry_run=dry_run,
            )
        except notable_stage.NotableError as exc:
            click.echo(f"notable failed: {exc}", err=True)
            sys.exit(1)
    finally:
        transport.close()

    prefix = "[dry-run] " if dry_run else ""
    click.echo(
        f"{prefix}notable: {summary.processed} school(s) resolved, "
        f"{summary.skipped} skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")

    if write_tier and not dry_run:
        written = notable_stage.write_tier_file(config.data_dir, tier_out)
        click.echo(f"  wrote {written} school(s) with faculty to {tier_out}")


@main.command("active-faculty")
@click.option("--limit", type=int, default=None, help="Process at most N schools")
@click.option("--school", "school_id", default=None, help="Run a single school")
@click.option("--per-school", type=int, default=active_stage.DEFAULT_LIMIT,
              help="Cap researchers kept per school (default 20)")
@click.option("--catalog", default="../data-pipeline/out/universities.json",
              help="Catalog to read each school's degree families from, for the "
                   "plausibility check that keeps astronomers off a music college")
@click.option("--notable-faculty", default="../data-pipeline/sources/notable_faculty.json",
              help="Notable-faculty tier file, read for award records that set priority")
@click.option("--tier-out", default="../data-pipeline/sources/active_faculty.json")
@click.option("--write-tier/--no-write-tier", default=True)
@click.pass_context
def active_faculty(
    ctx: click.Context,
    limit: int | None,
    school_id: str | None,
    per_school: int,
    catalog: str,
    notable_faculty: str,
    tier_out: str,
    write_tier: bool,
) -> None:
    """Active faculty: who researches here now, and on what (OpenAlex)."""
    config: Config = ctx.obj["config"]
    logger = ctx.obj["logger"]
    dry_run: bool = ctx.obj["dry_run"]

    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / f"{active_stage.STAGE_NAME}.json")

    # The degree families each school actually awards. Without them nothing is
    # rejected, which is the safe direction: a missing catalog fact is not
    # evidence against a person.
    programs: dict[str, set[str]] = {}
    catalog_path = Path(catalog)
    if catalog_path.exists():
        for record in json.loads(catalog_path.read_text(encoding="utf-8")):
            families = {p["name"] for p in (record.get("programs") or [])}
            if families:
                programs[record["id"]] = families
        click.echo(f"  degree families loaded for {len(programs)} school(s)")
    else:
        click.echo(f"  note: no catalog at {catalog_path}; nothing will be rejected as implausible")

    # Awards ride in from the notable stage's tier file, which carries
    # Wikidata's P166 for anyone with a Wikipedia article. No extra requests,
    # and it is the only award data that exists at scale — ORCID's
    # distinctions section is empty in practice.
    honours: dict[str, dict[str, list[str]]] = {}
    notable_path = Path(notable_faculty)
    if notable_path.exists():
        for school, record in json.loads(notable_path.read_text(encoding="utf-8")).items():
            by_name = {
                person["name"]: person["awards"]
                for person in record.get("notable_faculty", [])
                if person.get("awards")
            }
            if by_name:
                honours[school] = by_name
        click.echo(f"  award records loaded for {len(honours)} school(s)")
    else:
        click.echo(f"  note: no notable faculty at {notable_path}; nothing will be prioritised "
                   "by award")

    transport = httpx.Client(follow_redirects=True)
    try:
        robots = ApiRobots(RobotsChecker(transport))
        # The contact address rides in the User-Agent, not the query string,
        # so cached responses stay addressable. See `polite_user_agent`.
        polite = dataclasses.replace(
            config,
            user_agent=polite_user_agent(config.user_agent, config.openalex_mailto),
        )
        http_client = HttpClient(polite, robots, transport)
        api = OpenAlexApi(http_client, logger, mailto=config.openalex_mailto)
        try:
            summary = active_stage.run(
                config, checkpoint, logger, api,
                programs_by_school=programs, honours_by_school=honours,
                limit=limit, school_id=school_id,
                per_school=per_school, dry_run=dry_run,
            )
        except active_stage.ActiveFacultyError as exc:
            click.echo(f"active-faculty failed: {exc}", err=True)
            sys.exit(1)
    finally:
        transport.close()

    prefix = "[dry-run] " if dry_run else ""
    click.echo(
        f"{prefix}active-faculty: {summary.processed} school(s) resolved, "
        f"{summary.skipped} skipped, {summary.failed} failed"
    )
    for note in summary.notes:
        click.echo(f"  note: {note}")

    if write_tier and not dry_run:
        written = active_stage.write_tier_file(config.data_dir, tier_out)
        click.echo(f"  wrote {written} school(s) to {tier_out}")
