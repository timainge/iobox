"""
Command-line interface for the iobox application.

This module provides a user-friendly CLI for interacting with iobox functionality.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import typer

from iobox import __version__
from iobox.accounts import set_active_account
from iobox.auth import set_active_mode
from iobox.file_manager import (
    SyncState,
    check_for_duplicates,
    create_output_directory,
    download_email_attachments,
    save_email_to_markdown,
)
from iobox.markdown import convert_email_to_markdown
from iobox.markdown_converter import convert_thread_to_markdown
from iobox.modes import CLI_COMMANDS_BY_MODE, AccessMode, get_mode_from_env
from iobox.providers import EmailProvider, EmailQuery, get_provider

# Create a Typer app
app = typer.Typer(help="Gmail to Markdown converter")

# Add the version option to the main Typer app
version_callback = typer.Option(
    False,
    "--version",
    "-v",
    help="Show version and exit",
    callback=lambda value: typer.echo(f"iobox version {__version__}") or exit(0) if value else None,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _email_data_to_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Convert an EmailData dict (``from_`` key) to legacy format (``from`` key).

    Existing modules (markdown_converter, file_manager) expect the sender to
    live under the ``"from"`` key, but :class:`EmailData` uses ``"from_"``
    because ``from`` is a Python keyword.  This helper bridges the two.
    """
    result = dict(data)
    if "from_" in result and "from" not in result:
        result["from"] = result.pop("from_")
    return result


def _parse_dates(
    days: int | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[date | None, date | None]:
    """Convert CLI date parameters into ``(after, before)`` date objects.

    * When ``start_date`` is given it takes precedence over ``days``.
    * ``days`` is relative to today.
    * Returns ``(None, None)`` when no date constraints are provided.
    """
    after: date | None = None
    before: date | None = None

    if start_date:
        # Accept YYYY/MM/DD format
        parts = start_date.replace("-", "/").split("/")
        after = date(int(parts[0]), int(parts[1]), int(parts[2]))
    elif days is not None:
        after = date.today() - timedelta(days=days)

    if end_date:
        parts = end_date.replace("-", "/").split("/")
        before = date(int(parts[0]), int(parts[1]), int(parts[2]))

    return after, before


def _get_provider(ctx: typer.Context) -> EmailProvider:
    """Return the provider stored on the Typer context."""
    return ctx.obj["provider"]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def version():
    """Display the current version of iobox."""
    typer.echo(f"iobox version {__version__}")


@app.command()
def auth_status(ctx: typer.Context):
    """Check the status of email provider authentication."""
    current_mode = ctx.obj.get("mode", AccessMode.standard) if ctx.obj else AccessMode.standard
    current_account = ctx.obj.get("account", "default") if ctx.obj else "default"
    provider_name = ctx.obj.get("provider_name", "gmail") if ctx.obj else "gmail"

    typer.echo("\nAuthentication Status")
    typer.echo("-------------------")
    typer.echo(f"Provider: {provider_name}")
    typer.echo(f"Access mode: {current_mode.value}")
    typer.echo(f"Account: {current_account}")

    if provider_name == "outlook":
        from iobox.providers.outlook_auth import check_outlook_auth_status

        status = check_outlook_auth_status()
        typer.echo(f"Authenticated: {status['authenticated']}")
        typer.echo(f"Client ID configured: {status['client_id_configured']}")
        typer.echo(f"Tenant ID: {status['tenant_id']}")
        typer.echo(f"Token file exists: {status['token_file_exists']}")
        typer.echo(f"Token path: {status['token_path']}")

        if "error" in status:
            typer.echo(f"Error: {status['error']}")

        if not status["client_id_configured"]:
            typer.echo("\nTo set up Outlook / Microsoft 365 credentials:")
            typer.echo("1. Go to https://entra.microsoft.com")
            typer.echo("2. Register an application (or use an existing one)")
            typer.echo("3. Set OUTLOOK_CLIENT_ID in your .env file")
            typer.echo("4. Optionally set OUTLOOK_CLIENT_SECRET and OUTLOOK_TENANT_ID")

        if status["authenticated"]:
            try:
                provider = _get_provider(ctx)
                profile = provider.get_profile()
                typer.echo("\nOutlook Profile")
                typer.echo("-------------------")
                typer.echo(f"Email: {profile.get('email', 'Unknown')}")
                typer.echo(f"Display name: {profile.get('display_name', 'Unknown')}")
            except Exception:
                pass
    else:
        # Gmail auth status
        from iobox.auth import check_auth_status, get_gmail_profile, get_gmail_service

        status = check_auth_status()
        typer.echo(f"Authenticated: {status['authenticated']}")
        typer.echo(f"Credentials file exists: {status['credentials_file_exists']}")
        typer.echo(f"Credentials path: {status['credentials_path']}")
        typer.echo(f"Token file exists: {status['token_file_exists']}")
        typer.echo(f"Token path: {status['token_path']}")

        if status["token_file_exists"] and "expired" in status:
            typer.echo(f"Token expired: {status['expired']}")
            typer.echo(f"Has refresh token: {status['has_refresh_token']}")

        if not status["credentials_file_exists"]:
            typer.echo("\nTo set up Google Cloud OAuth 2.0 credentials:")
            typer.echo("1. Go to https://console.cloud.google.com/")
            typer.echo("2. Create a project or select an existing one")
            typer.echo("3. Navigate to APIs & Services > Credentials")
            typer.echo("4. Click 'Create Credentials' > 'OAuth client ID'")
            typer.echo("5. Choose 'Desktop app' as application type")
            typer.echo(
                "6. Download the JSON file and save it as 'credentials.json' in the project root"
            )

        try:
            service = get_gmail_service()
            profile = get_gmail_profile(service)
            typer.echo("\nGmail Profile")
            typer.echo("-------------------")
            typer.echo(f"Email: {profile.get('emailAddress', 'Unknown')}")
            typer.echo(f"Messages: {profile.get('messagesTotal', 0):,}")
            typer.echo(f"Threads: {profile.get('threadsTotal', 0):,}")
        except Exception:
            pass


@app.command()
def search(
    query: str = typer.Option(..., "--query", "-q", help="Search query using Gmail search syntax"),
    max_results: int = typer.Option(
        10, "--max-results", "-m", help="Maximum number of results to return"
    ),
    days: int = typer.Option(7, "--days", "-d", help="Number of days back to search"),
    start_date: str = typer.Option(
        None,
        "--start-date",
        "-s",
        help="Start date in YYYY/MM/DD format (overrides days parameter if provided)",
    ),
    end_date: str = typer.Option(
        None, "--end-date", "-e", help="End date in YYYY/MM/DD format (requires start-date)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information for each result"
    ),
    debug: bool = typer.Option(False, "--debug", help="Show debug information about API responses"),
    include_spam_trash: bool = typer.Option(
        False, "--include-spam-trash", help="Include messages from SPAM and TRASH"
    ),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """Search for emails matching the specified query."""
    try:
        provider = _get_provider(ctx)

        after, before = _parse_dates(days, start_date, end_date)
        eq = EmailQuery(
            raw_query=query,
            max_results=max_results,
            after=after,
            before=before,
            include_spam_trash=include_spam_trash,
        )

        typer.echo(f"Searching for emails matching: {query}")
        results = provider.search_emails(eq)

        if not results:
            typer.echo("No emails found matching the query.")
            return

        # Display results
        typer.echo(f"\nFound {len(results)} emails:")

        # In debug mode, show a sample of available fields from the first email
        if debug and results:
            typer.echo("\nAPI Response Debug Info (first result):")
            typer.echo("Available fields in email object:")
            for key, value in results[0].items():
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                elif isinstance(value, dict):
                    value = f"{type(value)} with keys: {', '.join(value.keys())}"
                elif isinstance(value, list) and len(value) > 5:
                    value = f"List with {len(value)} items: {value[:5]}..."
                typer.echo(f"  - {key}: {value}")
            typer.echo("")

        for i, email in enumerate(results, 1):
            email_dict = _email_data_to_dict(email)
            subject = email_dict.get("subject", "No subject")
            sender = email_dict.get("from", "Unknown sender")
            date_str = email_dict.get("date", "Unknown date")

            # Format the date more nicely if possible
            try:
                from dateutil import parser

                date_obj = parser.parse(date_str)
                date_str = date_obj.strftime("%d/%m/%Y %H:%M")
            except Exception:
                pass

            labels = email_dict.get("labels", [])
            label_str = ", ".join(labels) if labels else "No labels"

            typer.echo(f"{i}. {subject}")
            typer.echo(f"   ID: {email_dict.get('message_id', 'No ID')}")

            snippet = email_dict.get("snippet", "")
            if snippet:
                import html

                try:
                    snippet = html.unescape(snippet)
                except Exception:
                    pass
                snippet = snippet[:70] + "..." if len(snippet) > 70 else snippet
                typer.echo(f"   Preview: {snippet}")

            typer.echo(f"   From: {sender}")
            typer.echo(f"   Date: {date_str}")

            if verbose:
                typer.echo(f"   Labels: {label_str}")
                typer.echo("")
            else:
                typer.echo("   " + "-" * 40)

    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@app.command()
def save(
    message_id: str = typer.Option(
        None, "--message-id", "-m", help="ID of a specific email to save"
    ),
    thread_id: str = typer.Option(
        None, "--thread-id", help="ID of a thread to save as a single file"
    ),
    query: str = typer.Option(
        None, "--query", "-q", help="Search query for emails to save (for batch mode)"
    ),
    max_results: int = typer.Option(
        10, "--max", help="Maximum number of emails to save in batch mode"
    ),
    days: int = typer.Option(7, "--days", "-d", help="Number of days back to search for emails"),
    start_date: str = typer.Option(
        None,
        "--start-date",
        "-s",
        help="Start date in YYYY/MM/DD format (overrides days parameter if provided)",
    ),
    end_date: str = typer.Option(
        None, "--end-date", "-e", help="End date in YYYY/MM/DD format (requires start-date)"
    ),
    output_dir: str = typer.Option(
        ".", "--output-dir", "-o", help="Directory to save markdown files to"
    ),
    html_preferred: bool = typer.Option(
        True, "--html-preferred", help="Prefer HTML content if available"
    ),
    download_attachments: bool = typer.Option(
        False, "--download-attachments", help="Download email attachments"
    ),
    attachment_types: str = typer.Option(
        None,
        "--attachment-types",
        help="Filter attachments by file extension (comma-separated, e.g., 'pdf,docx,xlsx')",
    ),
    include_spam_trash: bool = typer.Option(
        False, "--include-spam-trash", help="Include messages from SPAM and TRASH"
    ),
    sync: bool = typer.Option(
        False, "--sync", help="Enable incremental sync: only fetch new emails since last run"
    ),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """
    Save emails as Markdown files.

    Supports three modes:
    1. Single mode: Save one specific email (use --message-id)
    2. Thread mode: Save a full thread as a single file (use --thread-id)
    3. Batch mode: Save multiple emails matching a query (use --query)
    """
    try:
        # Check parameter validity
        if message_id is None and thread_id is None and query is None:
            typer.echo("Error: You must specify --message-id (-m), --thread-id, or --query (-q)")
            typer.echo("\nFor help, run: iobox save --help")
            raise typer.Exit(code=1)

        provider = _get_provider(ctx)
        preferred = "text/html" if html_preferred else "text/plain"

        # Create output directory if it doesn't exist
        output_dir = create_output_directory(output_dir)

        # Parse attachment types if provided
        attachment_filters: list[str] = []
        if attachment_types:
            attachment_filters = [ext.strip().lower() for ext in attachment_types.split(",")]

        # Thread mode
        if thread_id is not None:
            messages = provider.get_thread(thread_id)
            # Convert for markdown compatibility
            messages_dicts = [_email_data_to_dict(m) for m in messages]
            markdown_content = convert_thread_to_markdown(messages_dicts)
            subject = messages_dicts[0].get("subject", "thread") if messages_dicts else "thread"
            from iobox.utils import slugify_text

            subject_slug = slugify_text(subject)
            filename = f"{subject_slug}_{thread_id}.md"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            typer.echo(f"Successfully saved thread to {filepath}")
            return

        # Single email mode
        if message_id is not None:
            # Get email content via provider
            email_data = provider.get_email_content(message_id, preferred_content_type=preferred)
            email_dict = _email_data_to_dict(email_data)

            # Convert to markdown
            markdown_content = convert_email_to_markdown(email_dict)

            # Save to file
            filepath = save_email_to_markdown(
                email_data=email_dict, markdown_content=markdown_content, output_dir=output_dir
            )

            typer.echo(f"Successfully saved email to {filepath}")

            # Download attachments if requested
            if download_attachments and email_dict.get("attachments"):
                att_result = download_email_attachments(
                    email_data=email_dict,
                    output_dir=output_dir,
                    attachment_filters=attachment_filters,
                    download_fn=provider.download_attachment,
                )
                typer.echo(f"  Downloaded {att_result['downloaded_count']} attachment(s)")
                for err in att_result["errors"]:
                    typer.echo(f"  Warning: {err}")

        # Batch mode
        else:
            # Incremental sync: try to use history if --sync is set
            sync_state = SyncState(output_dir)
            message_ids_to_fetch: list[str] | None = None

            if sync:
                state_exists = sync_state.load()
                if state_exists and sync_state.last_history_id:
                    hid = sync_state.last_history_id
                    typer.echo(
                        f"Incremental sync: checking for new emails since historyId {hid}..."
                    )
                    new_ids = provider.get_new_messages(sync_state.last_history_id)
                    if new_ids is not None:
                        typer.echo(f"Found {len(new_ids)} new message(s) since last sync.")
                        message_ids_to_fetch = new_ids
                    else:
                        typer.echo("Sync history expired. Falling back to full query.")

            if message_ids_to_fetch is not None:
                # Use pre-fetched IDs from incremental sync
                if not message_ids_to_fetch:
                    typer.echo("No new emails since last sync.")
                    # Still update the history ID
                    current_sync = provider.get_sync_state()
                    sync_state.update(current_sync, [])
                    return
                results_for_batch = [{"message_id": mid} for mid in message_ids_to_fetch]
            else:
                # Full search
                after, before = _parse_dates(days, start_date, end_date)
                eq = EmailQuery(
                    raw_query=query,
                    max_results=max_results,
                    after=after,
                    before=before,
                    include_spam_trash=include_spam_trash,
                )
                typer.echo(f"Searching for emails matching: {query}")
                search_results = provider.search_emails(eq)
                if not search_results:
                    typer.echo("No emails found matching the query.")
                    if sync:
                        current_sync = provider.get_sync_state()
                        sync_state.update(current_sync, [])
                    return
                results_for_batch = [_email_data_to_dict(r) for r in search_results]

            total_emails = len(results_for_batch)
            typer.echo(f"\nFound {total_emails} emails to process.")

            # Check for already processed emails
            all_message_ids = [r["message_id"] for r in results_for_batch]
            duplicates = check_for_duplicates(all_message_ids, output_dir)
            ids_to_process = [mid for mid in all_message_ids if mid not in duplicates]

            for mid in duplicates:
                typer.echo(f"Skipping already processed email: {mid}")

            saved_count = 0
            attachment_count = 0

            # Batch-fetch full content for all non-duplicate emails
            if ids_to_process:
                typer.echo(f"Fetching {len(ids_to_process)} email(s) in batch...")
                email_batch = provider.batch_get_emails(
                    ids_to_process,
                    preferred_content_type=preferred,
                )

                for idx, raw_email_data in enumerate(email_batch, 1):
                    email_dict = _email_data_to_dict(raw_email_data)
                    if "error" in email_dict:
                        typer.echo(
                            f"  Skipping email {email_dict['message_id']}: {email_dict['error']}"
                        )
                        continue

                    subj = email_dict.get("subject", "No Subject")
                    typer.echo(f"Processing email {idx}/{len(ids_to_process)}: {subj}")

                    # Convert to markdown
                    markdown_content = convert_email_to_markdown(email_dict)

                    # Save to file
                    save_email_to_markdown(
                        email_data=email_dict,
                        markdown_content=markdown_content,
                        output_dir=output_dir,
                    )

                    saved_count += 1

                    # Download attachments if requested
                    if download_attachments and email_dict.get("attachments"):
                        result_dict = download_email_attachments(
                            email_data=email_dict,
                            output_dir=output_dir,
                            attachment_filters=attachment_filters,
                            download_fn=provider.download_attachment,
                        )
                        attachment_count += result_dict["downloaded_count"]
                        for err in result_dict["errors"]:
                            typer.echo(f"  Warning: {err}")

            # Update sync state after successful save
            if sync:
                current_sync = provider.get_sync_state()
                sync_state.update(current_sync, ids_to_process)
                typer.echo(f"Sync state updated (historyId: {current_sync})")

            # Summary message
            typer.echo(f"\nCompleted processing {total_emails} emails:")
            typer.echo(f"  - {saved_count} emails saved to markdown")
            typer.echo(f"  - {len(duplicates)} emails skipped (already processed)")
            if download_attachments:
                typer.echo(f"  - {attachment_count} attachments downloaded")

    except Exception as e:
        typer.echo(f"Error saving emails: {e}")
        raise typer.Exit(code=1) from e


@app.command()
def forward(
    message_id: str = typer.Option(
        None, "--message-id", "-m", help="ID of a specific email to forward"
    ),
    query: str = typer.Option(
        None, "--query", "-q", help="Search query for emails to forward (batch mode)"
    ),
    to: str = typer.Option(..., "--to", "-t", help="Recipient email address"),
    max_results: int = typer.Option(
        10, "--max", help="Maximum number of emails to forward in batch mode"
    ),
    days: int = typer.Option(7, "--days", "-d", help="Number of days back to search"),
    start_date: str = typer.Option(
        None, "--start-date", "-s", help="Start date in YYYY/MM/DD format"
    ),
    end_date: str = typer.Option(None, "--end-date", "-e", help="End date in YYYY/MM/DD format"),
    note: str = typer.Option(
        None, "--note", "-n", help="Optional note to prepend to forwarded email"
    ),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """
    Forward emails to a recipient.

    Supports two modes:
    1. Single mode: Forward one email (use --message-id)
    2. Batch mode: Forward emails matching a query (use --query)
    """
    try:
        if message_id is None and query is None:
            typer.echo("Error: You must specify either --message-id (-m) or --query (-q)")
            raise typer.Exit(code=1)

        provider = _get_provider(ctx)

        if message_id is not None:
            typer.echo(f"Forwarding email {message_id} to {to}...")
            result = provider.forward_message(message_id=message_id, to=to, comment=note)
            msg_id = result.get("message_id", "unknown")
            typer.echo(f"Successfully forwarded. New message ID: {msg_id}")
        else:
            after, before = _parse_dates(days, start_date, end_date)
            eq = EmailQuery(
                raw_query=query,
                max_results=max_results,
                after=after,
                before=before,
            )
            typer.echo(f"Searching for emails matching: {query}")
            results = provider.search_emails(eq)

            if not results:
                typer.echo("No emails found matching the query.")
                return

            typer.echo(f"Found {len(results)} emails to forward.")
            forwarded = 0
            for email_summary in results:
                mid = email_summary["message_id"]
                typer.echo(f"Forwarding: {email_summary.get('subject', 'No Subject')}")
                provider.forward_message(message_id=mid, to=to, comment=note)
                forwarded += 1

            typer.echo(f"\nForwarded {forwarded} emails to {to}.")

    except Exception as e:
        typer.echo(f"Error forwarding emails: {e}")
        raise typer.Exit(code=1) from e


@app.command()
def send(
    to: str = typer.Option(..., "--to", "-t", help="Recipient email address"),
    subject: str = typer.Option(..., "--subject", "-s", help="Email subject line"),
    body: str = typer.Option(None, "--body", "-b", help="Email body text (inline)"),
    body_file: str = typer.Option(
        None, "--body-file", "-f", help="Path to file containing email body"
    ),
    cc: str = typer.Option(None, "--cc", help="CC recipients (comma-separated)"),
    bcc: str = typer.Option(None, "--bcc", help="BCC recipients (comma-separated)"),
    html: bool = typer.Option(False, "--html", help="Send body as HTML content"),
    attach: list[str] | None = typer.Option(
        None, "--attach", help="File path to attach (can be specified multiple times)"
    ),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """
    Compose and send an email.

    Provide the body inline with --body or from a file with --body-file.
    """
    try:
        if body is None and body_file is None:
            typer.echo("Error: You must specify either --body (-b) or --body-file (-f)")
            raise typer.Exit(code=1)

        content_type = "plain"
        if body_file is not None:
            file_path = Path(body_file)
            if not file_path.exists():
                typer.echo(f"Error: File not found: {body_file}")
                raise typer.Exit(code=1)
            body = file_path.read_text(encoding="utf-8")
            if file_path.suffix.lower() == ".html":
                content_type = "html"

        if html:
            content_type = "html"

        if attach:
            for file_path in attach:
                if not Path(file_path).exists():
                    typer.echo(f"Error: Attachment file not found: {file_path}")
                    raise typer.Exit(code=1)

        provider = _get_provider(ctx)
        result = provider.send_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            content_type=content_type,
            attachments=attach or None,
        )

        typer.echo(f"Email sent successfully. Message ID: {result.get('message_id', 'unknown')}")

    except Exception as e:
        typer.echo(f"Error sending email: {e}")
        raise typer.Exit(code=1) from e


@app.command(name="draft-create")
def draft_create(
    to: str = typer.Option(..., "--to", "-t", help="Recipient email address"),
    subject: str = typer.Option(..., "--subject", "-s", help="Email subject line"),
    body: str = typer.Option(None, "--body", "-b", help="Email body text (inline)"),
    body_file: str = typer.Option(
        None, "--body-file", "-f", help="Path to file containing email body"
    ),
    cc: str = typer.Option(None, "--cc", help="CC recipients (comma-separated)"),
    bcc: str = typer.Option(None, "--bcc", help="BCC recipients (comma-separated)"),
    html: bool = typer.Option(False, "--html", help="Use HTML content type"),
    attach: list[str] | None = typer.Option(
        None, "--attach", help="File path to attach (can be specified multiple times)"
    ),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """Create an email draft without sending it."""
    try:
        if body is None and body_file is None:
            typer.echo("Error: You must specify either --body (-b) or --body-file (-f)")
            raise typer.Exit(code=1)

        content_type = "plain"
        if body_file is not None:
            file_path = Path(body_file)
            if not file_path.exists():
                typer.echo(f"Error: File not found: {body_file}")
                raise typer.Exit(code=1)
            body = file_path.read_text(encoding="utf-8")
            if file_path.suffix.lower() == ".html":
                content_type = "html"

        if html:
            content_type = "html"

        if attach:
            for file_path in attach:
                if not Path(file_path).exists():
                    typer.echo(f"Error: Attachment file not found: {file_path}")
                    raise typer.Exit(code=1)

        provider = _get_provider(ctx)
        result = provider.create_draft(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            content_type=content_type,
        )

        typer.echo(f"Draft created successfully. Draft ID: {result.get('message_id', 'unknown')}")

    except Exception as e:
        typer.echo(f"Error creating draft: {e}")
        raise typer.Exit(code=1) from e


@app.command(name="draft-list")
def draft_list(
    max_results: int = typer.Option(10, "--max", "-m", help="Maximum number of drafts to list"),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """List email drafts."""
    try:
        provider = _get_provider(ctx)
        drafts = provider.list_drafts(max_results=max_results)

        if not drafts:
            typer.echo("No drafts found.")
            return

        typer.echo(f"Found {len(drafts)} draft(s):")
        for draft in drafts:
            typer.echo(f"\nID: {draft['message_id']}")
            typer.echo(f"  Subject: {draft['subject']}")
            if draft.get("snippet"):
                typer.echo(f"  Preview: {draft['snippet'][:70]}")

    except Exception as e:
        typer.echo(f"Error listing drafts: {e}")
        raise typer.Exit(code=1) from e


@app.command(name="draft-send")
def draft_send(
    draft_id: str = typer.Option(..., "--draft-id", help="ID of the draft to send"),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """Send an existing draft."""
    try:
        provider = _get_provider(ctx)
        result = provider.send_draft(draft_id)
        typer.echo(f"Draft sent successfully. Message ID: {result.get('message_id', 'unknown')}")

    except Exception as e:
        typer.echo(f"Error sending draft: {e}")
        raise typer.Exit(code=1) from e


@app.command(name="draft-delete")
def draft_delete(
    draft_id: str = typer.Option(..., "--draft-id", help="ID of the draft to delete"),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """Permanently delete a draft."""
    try:
        provider = _get_provider(ctx)
        result = provider.delete_draft(draft_id)
        typer.echo(f"Draft deleted successfully. Draft ID: {result.get('message_id', draft_id)}")

    except Exception as e:
        typer.echo(f"Error deleting draft: {e}")
        raise typer.Exit(code=1) from e


@app.command()
def label(
    message_id: str = typer.Option(None, "--message-id", help="Message ID for single message mode"),
    query: str = typer.Option(None, "-q", "--query", help="Search query for batch mode"),
    max_results: int = typer.Option(
        10, "-m", "--max-results", help="Maximum number of messages in batch mode"
    ),
    days: int = typer.Option(7, "-d", "--days", help="Number of days back to search"),
    mark_read: bool = typer.Option(False, "--mark-read", help="Mark as read"),
    mark_unread: bool = typer.Option(False, "--mark-unread", help="Mark as unread"),
    star: bool = typer.Option(False, "--star", help="Star message"),
    unstar: bool = typer.Option(False, "--unstar", help="Unstar message"),
    archive: bool = typer.Option(False, "--archive", help="Archive (remove from INBOX)"),
    add: str = typer.Option(None, "--add", help="Add label by name"),
    remove: str = typer.Option(None, "--remove", help="Remove label by name"),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """
    Add or remove labels on one or more messages.

    Supports single message mode (--message-id) and batch mode (--query).
    """
    try:
        if message_id is None and query is None:
            typer.echo("Error: You must specify --message-id or --query (-q)")
            raise typer.Exit(code=1)

        provider = _get_provider(ctx)

        def _apply_label_ops(mid: str) -> None:
            """Apply all requested label operations to a single message."""
            if mark_read:
                provider.mark_read(mid, read=True)
            if mark_unread:
                provider.mark_read(mid, read=False)
            if star:
                provider.set_star(mid, starred=True)
            if unstar:
                provider.set_star(mid, starred=False)
            if archive:
                provider.archive(mid)
            if add:
                provider.add_tag(mid, add)
            if remove:
                provider.remove_tag(mid, remove)

        if message_id is not None:
            _apply_label_ops(message_id)
            typer.echo(f"Labels updated for message {message_id}")
        else:
            after, _before = _parse_dates(days, None, None)
            eq = EmailQuery(
                raw_query=query,
                max_results=max_results,
                after=after,
            )
            results = provider.search_emails(eq)
            if not results:
                typer.echo("No emails found matching the query.")
                return

            for r in results:
                _apply_label_ops(r["message_id"])

            typer.echo(f"Labels updated for {len(results)} message(s)")

    except Exception as e:
        typer.echo(f"Error updating labels: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def trash(
    message_id: str = typer.Option(None, "--message-id", help="Message ID for single message mode"),
    query: str = typer.Option(None, "-q", "--query", help="Search query for batch mode"),
    untrash: bool = typer.Option(False, "--untrash", help="Restore from trash instead of trashing"),
    days: int = typer.Option(7, "-d", "--days", help="Number of days back to search"),
    max_results: int = typer.Option(
        10, "-m", "--max-results", help="Maximum number of messages in batch mode"
    ),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """
    Move messages to trash or restore them from trash.

    Supports single message mode (--message-id) and batch mode (--query).
    Batch trash requires confirmation before proceeding.
    """
    try:
        if message_id is None and query is None:
            typer.echo("Error: You must specify --message-id or --query (-q)")
            raise typer.Exit(code=1)

        provider = _get_provider(ctx)
        past_tense = "Restored" if untrash else "Trashed"
        verb = "restore" if untrash else "trash"

        if message_id is not None:
            if untrash:
                provider.untrash(message_id)
            else:
                provider.trash(message_id)
            typer.echo(f"{past_tense} message {message_id}")
        else:
            after, _before = _parse_dates(days, None, None)
            eq = EmailQuery(
                raw_query=query,
                max_results=max_results,
                after=after,
            )
            results = provider.search_emails(eq)
            if not results:
                typer.echo("No emails found matching the query.")
                return

            confirmed = typer.confirm(f"Are you sure you want to {verb} {len(results)} message(s)?")
            if not confirmed:
                typer.echo("Aborted.")
                raise typer.Exit()

            for r in results:
                mid = r["message_id"]
                if untrash:
                    provider.untrash(mid)
                else:
                    provider.trash(mid)

            typer.echo(f"{past_tense} {len(results)} message(s)")

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.callback()
def main(
    ctx: typer.Context,
    version_flag: bool = version_callback,
    mode: str = typer.Option(
        None,
        "--mode",
        help="Access mode: readonly, standard (default), or dangerous",
        envvar="IOBOX_MODE",
    ),
    account: str = typer.Option(
        None,
        "--account",
        help="Account profile name for token storage (default: 'default')",
        envvar="IOBOX_ACCOUNT",
    ),
    provider: str = typer.Option(
        "gmail",
        "--provider",
        help="Email provider: gmail or outlook",
        envvar="IOBOX_PROVIDER",
    ),
):
    """
    Iobox - Email to Markdown Converter

    Use commands to interact with your email provider and convert emails to Markdown.
    """
    # Resolve the access mode (CLI flag > env var > default).
    if mode is not None:
        try:
            resolved_mode = AccessMode(mode.lower().strip())
        except ValueError:
            valid = ", ".join(m.value for m in AccessMode)
            typer.echo(f"Error: Invalid mode '{mode}'. Must be one of: {valid}", err=True)
            raise typer.Exit(code=1) from None
    else:
        resolved_mode = get_mode_from_env()

    # Resolve the account name (CLI flag > env var > default).
    resolved_account = account.strip() if account else "default"

    set_active_mode(resolved_mode)
    set_active_account(resolved_account)

    ctx.ensure_object(dict)
    ctx.obj["mode"] = resolved_mode
    ctx.obj["account"] = resolved_account
    ctx.obj["provider_name"] = provider.lower().strip()

    # Instantiate the provider (lazy auth — no browser/prompt in callback).
    try:
        ctx.obj["provider"] = get_provider(ctx.obj["provider_name"])
    except (ValueError, ImportError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None

    # Gate the invoked subcommand against the allowed set for this mode.
    cmd = ctx.invoked_subcommand
    if cmd is not None and cmd not in CLI_COMMANDS_BY_MODE[resolved_mode]:
        typer.echo(
            f"Error: Command '{cmd}' is not allowed in '{resolved_mode.value}' mode. "
            f"Use --mode dangerous to enable it.",
            err=True,
        )
        raise typer.Exit(code=1)


def run():
    app()


if __name__ == "__main__":
    run()
