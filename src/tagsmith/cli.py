"""Tagsmith Typer CLI — thin wrapper over the service layer."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tagsmith import __version__
from tagsmith.config import Settings, get_settings
from tagsmith.db.session import get_session, init_db
from tagsmith.gmail.auth import AuthError, run_auth_flow
from tagsmith.gmail.client import GmailClient
from tagsmith.gmail.parser import normalize_message
from tagsmith.review.display import format_message_for_review
from tagsmith.services.review_ops import ReviewOps
from tagsmith.services.sync import SyncService
from tagsmith.taxonomy.registry import TaxonomyRegistry
from tagsmith.telemetry import configure_logging, get_logger

app = typer.Typer(
    name="tagsmith",
    help="Classify unread Gmail into a managed, human-approved taxonomy.",
    no_args_is_help=True,
)
labels_app = typer.Typer(help="Gmail label helpers")
taxonomy_app = typer.Typer(help="Local taxonomy helpers")
review_app = typer.Typer(help="Review proposals and medium-confidence labels")
app.add_typer(labels_app, name="labels")
app.add_typer(taxonomy_app, name="taxonomy")
app.add_typer(review_app, name="review")

console = Console()
log = get_logger(__name__)


def _settings() -> Settings:
    settings = get_settings()
    configure_logging(settings.log_level)
    return settings


def _gmail(settings: Settings, *, interactive: bool = False) -> GmailClient:
    return GmailClient.from_settings(settings, interactive=interactive)


def _version_callback(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    """Tagsmith CLI."""


@app.command()
def auth() -> None:
    """Run desktop OAuth and store token.json in the config dir."""
    settings = _settings()
    try:
        run_auth_flow(settings)
    except AuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Authenticated.[/green] Token saved to {settings.token_path}")


@labels_app.command("list")
def labels_list() -> None:
    """List Gmail labels."""
    settings = _settings()
    try:
        gmail = _gmail(settings)
    except AuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    table = Table(title="Gmail labels")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Type")
    for label in sorted(gmail.list_labels(), key=lambda x: str(x.get("name", ""))):
        table.add_row(
            str(label.get("id", "")),
            str(label.get("name", "")),
            str(label.get("type", "")),
        )
    console.print(table)


@app.command()
def fetch(
    unread: bool = typer.Option(True, "--unread/--all", help="Fetch unread only."),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=500),
) -> None:
    """Fetch and print normalized emails (Phase 0 plumbing check)."""
    settings = _settings()
    try:
        gmail = _gmail(settings)
    except AuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    query = "is:unread" if unread else ""
    ids = gmail.list_message_ids(query=query or "", limit=limit)
    if not ids:
        console.print("[yellow]No messages.[/yellow]")
        return
    for gmail_id in ids:
        raw = gmail.get_message(gmail_id)
        email = normalize_message(raw, body_char_limit=settings.body_char_limit)
        console.print(
            Panel(
                email.classifier_payload(settings.body_char_limit),
                title=f"{email.gmail_id} · {email.subject[:60]}",
                subtitle=email.sender,
            )
        )


@app.command()
def sync(
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=500),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Actually create/apply Gmail labels. Default is dry-run.",
    ),
    reprocess: bool = typer.Option(
        False,
        "--reprocess",
        help="Reclassify messages that already have a SQLite decision.",
    ),
) -> None:
    """Classify unread mail; dry-run unless --apply."""
    settings = _settings()
    init_db(settings)
    try:
        gmail = _gmail(settings)
    except AuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    with get_session(settings) as session:
        service = SyncService(session, gmail, settings)
        try:
            result = asyncio.run(
                service.sync(limit=limit, apply=apply, reprocess=reprocess)
            )
        except Exception as exc:
            console.print(f"[red]sync failed: {exc}[/red]")
            raise typer.Exit(1) from exc

    mode = "APPLY" if apply else "DRY-RUN"
    console.print(f"[bold]{mode}[/bold] run_id={result.run_id} counts={result.counts.as_dict()}")
    for decision in result.decisions:
        conf = decision.get("confidence")
        conf_s = "null" if conf is None else f"{conf:.2f}"
        console.print(
            f"• {decision.get('action') or decision.get('route')} "
            f"| {decision.get('label_key')} ({conf_s}) "
            f"| {decision.get('subject', '')[:70]}"
        )


@taxonomy_app.command("list")
def taxonomy_list() -> None:
    """List active local taxonomy categories."""
    settings = _settings()
    init_db(settings)
    with get_session(settings) as session:
        registry = TaxonomyRegistry(session, settings)
        registry.ensure_seeded()
        table = Table(title="Active taxonomy")
        table.add_column("Key")
        table.add_column("Gmail label id")
        table.add_column("Description")
        for cat in registry.list_active():
            table.add_row(cat.key, cat.gmail_label_id or "", cat.description[:80])
        console.print(table)


@review_app.callback(invoke_without_command=True)
def review_root(ctx: typer.Context) -> None:
    """Interactive review of proposals and needs-review messages."""
    if ctx.invoked_subcommand is not None:
        return
    settings = _settings()
    init_db(settings)
    try:
        gmail = _gmail(settings)
    except AuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    with get_session(settings) as session:
        ops = ReviewOps(session, gmail, settings)
        _review_needs_review(ops)
        _review_held(ops)
        _review_proposals(ops)


def _print_message_panel(message_payload: dict[str, object], title: str) -> None:
    text = format_message_for_review(dict(message_payload), body_chars=500)
    console.print(
        Panel(
            Text(text),
            title=escape(title),
            border_style="cyan",
            width=min(100, (console.width or 100)),
        )
    )


def _prompt_existing_label(active: list[str], *, default: str | None = None) -> str:
    console.print("Active labels:")
    # Print in compact columns without Rich interpreting brackets.
    for i in range(0, len(active), 4):
        chunk = active[i : i + 4]
        console.print("  " + "  |  ".join(chunk))
    while True:
        raw = str(typer.prompt("Existing label key", default=default or "")).strip()
        if raw in active:
            return raw
        console.print(f"[red]Unknown label '{raw}'. Pick one from the list above.[/red]")


def _review_needs_review(ops: ReviewOps) -> None:
    items = ops.list_needs_review()
    if not items:
        console.print("[dim]No needs-review messages.[/dim]")
        return
    console.print(f"[bold]Needs review[/bold] ({len(items)})")
    active = ops.taxonomy.active_keys()
    for message, record in items:
        _print_message_panel(
            message.payload_json,
            title=f"{message.gmail_id} · predicted={record.predicted_key} "
            f"conf={record.confidence}",
        )
        # Escape brackets — Rich treats [a] as markup otherwise.
        console.print(
            "Actions: \\[c]onfirm  \\[p]ick another  \\[n]ew category  \\[s]kip"
        )
        choice = typer.prompt("Choice", default="s").strip().lower()
        if choice.startswith("c"):
            ops.confirm_label(message.gmail_id, apply=True)
            console.print("[green]Confirmed.[/green]")
        elif choice.startswith("p"):
            new_key = _prompt_existing_label(
                active, default=record.predicted_key or None
            )
            ops.change_label(message.gmail_id, new_key, apply=True)
            console.print(f"[green]Changed to {new_key}.[/green]")
        elif choice.startswith("n"):
            suggested = typer.prompt("Suggested key (kebab-case)")
            description = typer.prompt("One-line description")
            why = typer.prompt("Why no existing fit")
            proposal = ops.reject_and_propose(
                message.gmail_id,
                suggested_key=suggested,
                description=description,
                why=why,
            )
            console.print(
                f"[yellow]Queued proposal #{proposal.id} "
                f"{proposal.suggested_key}[/yellow]"
            )
        else:
            console.print("[dim]Skipped.[/dim]")


def _review_held(ops: ReviewOps) -> None:
    items = ops.list_held()
    if not items:
        console.print("[dim]No held messages.[/dim]")
        return
    console.print(f"[bold]Held / needs decision[/bold] ({len(items)})")
    console.print(
        "[dim]These have AI/needs-review in Gmail but no confident category yet.[/dim]"
    )
    active = ops.taxonomy.active_keys()
    for message, record in items:
        predicted = record.predicted_key if record else None
        conf = record.confidence if record else None
        rationale = record.rationale if record else ""
        _print_message_panel(
            message.payload_json,
            title=f"held {message.gmail_id} · predicted={predicted} conf={conf}",
        )
        if rationale:
            console.print(Panel(Text(rationale), title="model rationale", border_style="dim"))
        console.print("Actions: \\[e]xisting label  \\[n]ew category  \\[s]kip")
        choice = typer.prompt("Choice", default="s").strip().lower()
        if choice.startswith("e"):
            default = None
            blob = (rationale or "").lower()
            for key in active:
                if key.replace("-", " ") in blob or key in blob:
                    default = key
                    break
            label_key = _prompt_existing_label(active, default=default)
            ops.resolve_held_with_existing(message.gmail_id, label_key, apply=True)
            console.print(f"[green]Filed under '{label_key}'.[/green]")
            # Refresh active keys in case user somehow activated during session.
            active = ops.taxonomy.active_keys()
        elif choice.startswith("n"):
            suggested = typer.prompt("New key (kebab-case)")
            description = typer.prompt("One-line description")
            why = typer.prompt("Why no existing fit")
            ops.resolve_held_with_new(
                message.gmail_id,
                suggested_key=suggested,
                description=description,
                why=why,
                apply=True,
            )
            console.print(f"[green]Created and applied '{suggested}'.[/green]")
            active = ops.taxonomy.active_keys()
        else:
            console.print("[dim]Skipped.[/dim]")


def _review_proposals(ops: ReviewOps) -> None:
    proposals = ops.list_proposals()
    if not proposals:
        console.print("[dim]No pending proposals.[/dim]")
        return
    console.print(f"[bold]Proposals[/bold] ({len(proposals)})")
    active = ops.taxonomy.active_keys()
    for view in proposals:
        p = view.proposal
        if view.message:
            _print_message_panel(
                view.message.payload_json,
                title=f"Proposal #{p.id} · {view.message.subject[:50]}",
            )
        console.print(
            Panel(
                Text(
                    f"suggested_key: {p.suggested_key}\n"
                    f"description: {p.description}\n"
                    f"why: {p.why_no_existing_fit}\n"
                    f"rationale: {p.rationale}"
                ),
                title=escape(f"Proposal #{p.id} details"),
                border_style="yellow",
                width=min(100, (console.width or 100)),
            )
        )
        console.print(
            "Actions: \\[e]xisting label  \\[a]pprove new  \\[r]eject  \\[s]kip"
        )
        choice = typer.prompt("Choice", default="s").strip().lower()
        if choice.startswith("e"):
            # Heuristic default when rationale mentions a known label.
            default = None
            blob = f"{p.rationale} {p.why_no_existing_fit}".lower()
            for key in active:
                if key.replace("-", " ") in blob or key in blob:
                    default = key
                    break
            label_key = _prompt_existing_label(active, default=default)
            ops.assign_existing_label(p.id or 0, label_key, apply=True)
            console.print(
                f"[green]Assigned existing label '{label_key}' "
                f"and closed proposal #{p.id}.[/green]"
            )
        elif choice.startswith("a"):
            key = typer.prompt("Key", default=p.suggested_key)
            desc = typer.prompt("Description", default=p.description)
            result = asyncio.run(
                ops.approve_proposal(
                    p.id or 0,
                    apply=True,
                    key_override=key if key != p.suggested_key else None,
                    description_override=desc if desc != p.description else None,
                )
            )
            console.print(
                f"[green]Approved.[/green] Reclassified held: {result.counts.as_dict()}"
            )
        elif choice.startswith("r"):
            ops.reject_proposal(p.id or 0)
            console.print("[yellow]Rejected.[/yellow]")
        else:
            console.print("[dim]Skipped.[/dim]")


@review_app.command("list")
def review_list() -> None:
    """List pending proposals and needs-review messages."""
    settings = _settings()
    init_db(settings)
    with get_session(settings) as session:
        # Gmail not required for listing local queue.
        from tagsmith.review.queue import ReviewService

        queue = ReviewService(session)
        TaxonomyRegistry(session, settings).ensure_seeded()
        props = queue.list_pending_proposals()
        needs = queue.list_needs_review()
        held = queue.list_held()
    console.print(
        f"Proposals: {len(props)} | Needs review: {len(needs)} | Held: {len(held)}"
    )
    for p in props:
        console.print(f"  proposal #{p.id} {p.suggested_key} ← {p.gmail_id}")
    for message, need_record in needs:
        console.print(
            f"  needs-review {message.gmail_id} predicted={need_record.predicted_key} "
            f"conf={need_record.confidence}"
        )
    for message, held_record in held:
        predicted = held_record.predicted_key if held_record else None
        console.print(
            f"  held {message.gmail_id} predicted={predicted} · {message.subject[:60]}"
        )


def run() -> None:
    app()


if __name__ == "__main__":
    run()
