"""warden command-line interface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import load_config
from .runtime.orchestrator import Orchestrator
from .runtime.session_store import SessionStore
from .runtime.subagents import all_subagents


app = typer.Typer(
    help="warden — autonomous open-source maintainer agent platform.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the warden version."""

    console.print(f"warden {__version__}")


@app.command()
def health() -> None:
    """Report current environment and registered subagents."""

    config = load_config()
    table = Table(title="warden health", show_lines=True)
    table.add_column("key", style="bold")
    table.add_column("value")
    table.add_row("anthropic_base_url", config.anthropic_base_url)
    table.add_row("model", config.model)
    table.add_row("has_model_credentials", str(config.has_model_credentials))
    table.add_row("github_token_present", str(bool(config.github_token)))
    table.add_row("approval_mode", config.approval_mode)
    table.add_row("data_dir", str(config.data_dir))
    table.add_row("registered_subagents", ", ".join(spec.name for spec in all_subagents()))
    console.print(table)


@app.command()
def audit(
    last: int = typer.Option(10, "--last", min=1, help="Number of audit events to show."),
) -> None:
    """Tail the most recent audit events."""

    config = load_config()
    store = SessionStore(config.data_dir / "sessions.sqlite3")
    events = store.tail_events(limit=last)
    if not events:
        console.print("[dim]No audit events recorded yet.[/dim]")
        return
    for event in events:
        console.print(
            f"[bold]{event.created_at.isoformat()}[/bold]"
            f" · session={event.session_id} · {event.kind}"
        )
        console.print_json(json.dumps(event.payload, default=str))


@app.command(name="list-subagents")
def list_subagents() -> None:
    """Show the registered specialist subagents."""

    table = Table(title="Registered subagents", show_lines=True)
    table.add_column("name", style="bold")
    table.add_column("description")
    table.add_column("tools")
    table.add_column("skills")
    for spec in all_subagents():
        table.add_row(
            spec.name,
            spec.description,
            ", ".join(spec.allowed_tools),
            ", ".join(spec.skills),
        )
    console.print(table)


@app.command()
def triage(
    repo: str = typer.Option(..., help="GitHub owner/name, e.g. JithendraNara/example."),
    issue: int = typer.Option(..., help="Issue number to triage."),
    title: str = typer.Option(..., help="Issue title."),
    body_file: Path | None = typer.Option(
        None,
        "--body-file",
        help="Path to a file containing the issue body. Reads stdin if omitted.",
    ),
) -> None:
    """Run the triage workflow against a single issue."""

    body = body_file.read_text() if body_file else typer.get_text_stream("stdin").read()

    from .workflows.triage import TriageRequest, run_triage

    async def _run() -> None:
        orchestrator = Orchestrator()
        async for event in run_triage(
            orchestrator,
            TriageRequest(
                repo=repo,
                issue=issue,
                issue_title=title,
                issue_body=body,
            ),
        ):
            console.print(f"[cyan]{event.kind}[/cyan] {event.data}")

    asyncio.run(_run())


@app.command()
def eval(  # noqa: A001 - CLI command shadows builtin intentionally
    only: str | None = typer.Option(None, help="Run a single scenario by id."),
) -> None:
    """Run the built-in scenario evaluation."""

    from evals.run_eval import run_eval  # type: ignore[import-not-found]

    exit_code = run_eval(only=only)
    raise typer.Exit(code=exit_code)


@app.command(name="agent-triage")
def agent_triage(
    repo: str = typer.Option(..., help="GitHub owner/name, e.g. JithendraNara/example."),
    issue: int = typer.Option(..., help="Issue number to triage."),
    live: bool = typer.Option(
        False,
        "--live",
        help="Drive the Claude Agent SDK + MiniMax thinker (requires credentials).",
    ),
) -> None:
    """Run the agentic triage loop end-to-end against a real GitHub issue."""

    from .workflows.agentic_triage import run_agentic_triage

    result = run_agentic_triage(repo=repo, issue_number=issue, use_live_model=live)
    _print_outcome(result.session_id, result.outcome)


@app.command(name="agent-investigate")
def agent_investigate(
    repo_root: Path = typer.Option(
        ..., "--root", exists=True, file_okay=False, dir_okay=True, help="Local repo root."
    ),
    title: str = typer.Option(..., help="Issue title to drive the investigation."),
    body_file: Path | None = typer.Option(
        None,
        "--body-file",
        help="Path to a file containing the issue body. Reads stdin if omitted.",
    ),
) -> None:
    """Run the agentic investigation loop over a local repository."""

    from .workflows.agentic_investigation import run_agentic_investigation

    body = body_file.read_text() if body_file else typer.get_text_stream("stdin").read()
    result = run_agentic_investigation(
        repo_root=repo_root,
        issue_title=title,
        issue_body=body,
    )
    _print_outcome(result.session_id, result.outcome)


@app.command(name="agent-code")
def agent_code(
    repo_root: Path = typer.Option(
        ..., "--root", exists=True, file_okay=False, dir_okay=True, help="Local repo root."
    ),
    target: str = typer.Option(..., help="Target file path relative to the repo root."),
    goal: str = typer.Option(..., help="High-level description of the required fix."),
    evidence_file: Path | None = typer.Option(
        None,
        "--evidence-file",
        help="Path to a file with supporting evidence (issue body, logs).",
    ),
) -> None:
    """Run the agentic coding loop to draft a patch proposal."""

    from .workflows.agentic_coding import run_agentic_coding

    evidence = evidence_file.read_text() if evidence_file else typer.get_text_stream("stdin").read()
    result = run_agentic_coding(
        repo_root=repo_root,
        target_file=target,
        goal=goal,
        evidence=evidence,
    )
    _print_outcome(result.session_id, result.outcome)


@app.command(name="agent-review")
def agent_review(
    repo: str = typer.Option(..., help="GitHub owner/name."),
    pr: int = typer.Option(..., help="Pull request number."),
) -> None:
    """Run the agentic PR review loop against GitHub."""

    from .workflows.agentic_review import run_agentic_review

    result = run_agentic_review(repo=repo, pr_number=pr)
    _print_outcome(result.session_id, result.outcome)


@app.command(name="mcp-info")
def mcp_info() -> None:
    """Show the MCP server metadata for warden tools."""

    from .mcp_server import server_metadata

    metadata = server_metadata()
    console.print(f"[bold]MCP server:[/bold] {metadata['name']} v{metadata['version']}")
    table = Table(title="Exposed tools", show_lines=True)
    table.add_column("tool", style="bold")
    table.add_column("parameters")
    table.add_column("description")
    for tool in metadata["tools"]:
        params = ", ".join(f"{k}:{v}" for k, v in tool["parameters"].items())
        table.add_row(tool["name"], params, tool["description"])
    console.print(table)


def _print_outcome(session_id: str, outcome: Any) -> None:  # noqa: ANN401
    console.print(
        f"[bold]session:[/bold] {session_id}  [bold]status:[/bold] {outcome.status}"
    )
    console.print(f"tool_calls={outcome.tool_calls} iterations={outcome.iterations}")
    if outcome.result:
        console.print_json(json.dumps(outcome.result, default=str))
    if outcome.verification and not outcome.verification.ok:
        console.print(f"[red]verification failed:[/red] {outcome.verification.reason()}")


if __name__ == "__main__":  # pragma: no cover
    app()
