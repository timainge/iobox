"""
Command-line interface for the iobox application.

This module provides a user-friendly CLI for interacting with iobox functionality.
"""

import os
import sys
from pathlib import Path

import typer

from iobox import __version__
from iobox.auth import check_auth_status, get_gmail_profile, get_gmail_service
from iobox.email_retrieval import (
    batch_get_emails,
    batch_modify_labels,
    get_label_map,
    get_thread_content,
    modify_message_labels,
    resolve_label_name,
    trash_message,
    untrash_message,
)
from iobox.email_search import (
    get_email_content,
    get_new_messages,
    search_emails,
)
from iobox.email_sender import (
    compose_message,
    create_draft,
    delete_draft,
    forward_email,
    list_drafts,
    send_draft,
    send_message,
)
from iobox.file_manager import (
    SyncState,
    check_for_duplicates,
    create_output_directory,
    download_email_attachments,
    save_email_to_markdown,
)
from iobox.markdown import convert_email_to_markdown
from iobox.markdown_converter import convert_thread_to_markdown

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


@app.command()
def version():
    """Display the current version of iobox."""
    typer.echo(f"iobox version {__version__}")


@app.command()
def auth_status():
    """Check the status of Gmail API authentication."""
    status = check_auth_status()

    typer.echo("\nAuthentication Status")
    typer.echo("-------------------")
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
):
    """Search for emails matching the specified query."""
    try:
        # Authenticate with Gmail API
        service = get_gmail_service()
        label_map = get_label_map(service)

        # Search for emails
        typer.echo(f"Searching for emails matching: {query}")
        results = search_emails(
            service,
            query,
            max_results,
            days,
            start_date,
            end_date,
            label_map=label_map,
            include_spam_trash=include_spam_trash,
        )

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
            subject = email.get("subject", "No subject")
            sender = email.get("from", "Unknown sender")
            date = email.get("date", "Unknown date")

            # Format the date more nicely if possible
            try:
                from dateutil import parser

                date_obj = parser.parse(date)
                date_str = date_obj.strftime("%d/%m/%Y %H:%M")
            except Exception:
                date_str = date

            labels = email.get("labels", [])
            label_str = ", ".join(labels) if labels else "No labels"

            typer.echo(f"{i}. {subject}")
            typer.echo(f"   ID: {email.get('message_id', 'No ID')}")

            snippet = email.get("snippet", "")
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

        # Authenticate with Gmail API
        service = get_gmail_service()
        label_map = get_label_map(service)

        # Create output directory if it doesn't exist
        output_dir = create_output_directory(output_dir)

        # Parse attachment types if provided
        attachment_filters = []
        if attachment_types:
            attachment_filters = [ext.strip().lower() for ext in attachment_types.split(",")]

        # Thread mode
        if thread_id is not None:
            messages = get_thread_content(
                service,
                thread_id,
                preferred_content_type="text/html" if html_preferred else "text/plain",
            )
            markdown_content = convert_thread_to_markdown(messages)
            subject = messages[0].get("subject", "thread") if messages else "thread"
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
            # Get email content
            email_data = get_email_content(
                service,
                message_id,
                preferred_content_type="text/html" if html_preferred else "text/plain",
                label_map=label_map,
            )

            # Convert to markdown
            markdown_content = convert_email_to_markdown(email_data)

            # Save to file
            filepath = save_email_to_markdown(
                email_data=email_data, markdown_content=markdown_content, output_dir=output_dir
            )

            typer.echo(f"Successfully saved email to {filepath}")

            # Download attachments if requested
            if download_attachments and email_data.get("attachments"):
                att_result = download_email_attachments(
                    service=service,
                    email_data=email_data,
                    output_dir=output_dir,
                    attachment_filters=attachment_filters,
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
                    new_ids = get_new_messages(service, sync_state.last_history_id)
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
                    profile = service.users().getProfile(userId="me").execute()
                    sync_state.update(profile.get("historyId", sync_state.last_history_id), [])
                    return
                results_for_batch = [{"message_id": mid} for mid in message_ids_to_fetch]
            else:
                # Full search
                typer.echo(f"Searching for emails matching: {query}")
                search_results = search_emails(
                    service,
                    query,
                    max_results,
                    days,
                    start_date,
                    end_date,
                    label_map=label_map,
                    include_spam_trash=include_spam_trash,
                )
                if not search_results:
                    typer.echo("No emails found matching the query.")
                    if sync:
                        profile = service.users().getProfile(userId="me").execute()
                        sync_state.update(profile.get("historyId", ""), [])
                    return
                results_for_batch = search_results

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
                email_batch = batch_get_emails(
                    service,
                    ids_to_process,
                    preferred_content_type="text/html" if html_preferred else "text/plain",
                    label_map=label_map,
                )

                for idx, email_data in enumerate(email_batch, 1):
                    if "error" in email_data:
                        typer.echo(
                            f"  Skipping email {email_data['message_id']}: {email_data['error']}"
                        )
                        continue

                    subj = email_data.get("subject", "No Subject")
                    typer.echo(
                        f"Processing email {idx}/{len(ids_to_process)}: {subj}"
                    )

                    # Convert to markdown
                    markdown_content = convert_email_to_markdown(email_data)

                    # Save to file
                    save_email_to_markdown(
                        email_data=email_data,
                        markdown_content=markdown_content,
                        output_dir=output_dir,
                    )

                    saved_count += 1

                    # Download attachments if requested
                    if download_attachments and email_data.get("attachments"):
                        result_dict = download_email_attachments(
                            service=service,
                            email_data=email_data,
                            output_dir=output_dir,
                            attachment_filters=attachment_filters,
                        )
                        attachment_count += result_dict["downloaded_count"]
                        for err in result_dict["errors"]:
                            typer.echo(f"  Warning: {err}")

            # Update sync state after successful save
            if sync:
                profile = service.users().getProfile(userId="me").execute()
                sync_state.update(profile.get("historyId", ""), ids_to_process)
                typer.echo(f"Sync state updated (historyId: {profile.get('historyId', 'unknown')})")

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

        service = get_gmail_service()

        if message_id is not None:
            typer.echo(f"Forwarding email {message_id} to {to}...")
            result = forward_email(
                service,
                message_id=message_id,
                to=to,
                additional_text=note,
            )
            typer.echo(f"Successfully forwarded. New message ID: {result.get('id', 'unknown')}")
        else:
            typer.echo(f"Searching for emails matching: {query}")
            results = search_emails(service, query, max_results, days, start_date, end_date)

            if not results:
                typer.echo("No emails found matching the query.")
                return

            typer.echo(f"Found {len(results)} emails to forward.")
            forwarded = 0
            for email_summary in results:
                mid = email_summary["message_id"]
                typer.echo(f"Forwarding: {email_summary.get('subject', 'No Subject')}")
                forward_email(service, message_id=mid, to=to, additional_text=note)
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

        service = get_gmail_service()
        message = compose_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            content_type=content_type,
            attachments=attach or None,
        )
        result = send_message(service, message)

        typer.echo(f"Email sent successfully. Message ID: {result.get('id', 'unknown')}")

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

        service = get_gmail_service()
        message = compose_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            content_type=content_type,
            attachments=attach or None,
        )
        result = create_draft(service, message)

        typer.echo(f"Draft created successfully. Draft ID: {result.get('id', 'unknown')}")

    except Exception as e:
        typer.echo(f"Error creating draft: {e}")
        raise typer.Exit(code=1) from e


@app.command(name="draft-list")
def draft_list(
    max_results: int = typer.Option(10, "--max", "-m", help="Maximum number of drafts to list"),
):
    """List Gmail drafts."""
    try:
        service = get_gmail_service()
        drafts = list_drafts(service, max_results=max_results)

        if not drafts:
            typer.echo("No drafts found.")
            return

        typer.echo(f"Found {len(drafts)} draft(s):")
        for draft in drafts:
            typer.echo(f"\nID: {draft['id']}")
            typer.echo(f"  Subject: {draft['subject']}")
            if draft["snippet"]:
                typer.echo(f"  Preview: {draft['snippet'][:70]}")

    except Exception as e:
        typer.echo(f"Error listing drafts: {e}")
        raise typer.Exit(code=1) from e


@app.command(name="draft-send")
def draft_send(
    draft_id: str = typer.Option(..., "--draft-id", help="ID of the draft to send"),
):
    """Send an existing draft."""
    try:
        service = get_gmail_service()
        result = send_draft(service, draft_id)
        typer.echo(f"Draft sent successfully. Message ID: {result.get('id', 'unknown')}")

    except Exception as e:
        typer.echo(f"Error sending draft: {e}")
        raise typer.Exit(code=1) from e


@app.command(name="draft-delete")
def draft_delete(
    draft_id: str = typer.Option(..., "--draft-id", help="ID of the draft to delete"),
):
    """Permanently delete a draft."""
    try:
        service = get_gmail_service()
        result = delete_draft(service, draft_id)
        typer.echo(f"Draft deleted successfully. Draft ID: {result.get('draft_id', draft_id)}")

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
):
    """
    Add or remove labels on one or more messages.

    Supports single message mode (--message-id) and batch mode (--query).
    """
    try:
        if message_id is None and query is None:
            typer.echo("Error: You must specify --message-id or --query (-q)")
            raise typer.Exit(code=1)

        service = get_gmail_service()

        add_labels: list[str] = []
        remove_labels: list[str] = []

        if mark_read:
            remove_labels.append("UNREAD")
        if mark_unread:
            add_labels.append("UNREAD")
        if star:
            add_labels.append("STARRED")
        if unstar:
            remove_labels.append("STARRED")
        if archive:
            remove_labels.append("INBOX")
        if add:
            add_labels.append(resolve_label_name(service, add))
        if remove:
            remove_labels.append(resolve_label_name(service, remove))

        if message_id is not None:
            modify_message_labels(service, message_id, add_labels or None, remove_labels or None)
            typer.echo(f"Labels updated for message {message_id}")
        else:
            label_map = get_label_map(service)
            results = search_emails(service, query, max_results, days, label_map=label_map)
            if not results:
                typer.echo("No emails found matching the query.")
                return

            msg_ids = [r["message_id"] for r in results]
            if len(msg_ids) >= 2:
                batch_modify_labels(service, msg_ids, add_labels or None, remove_labels or None)
            else:
                modify_message_labels(
                    service, msg_ids[0], add_labels or None, remove_labels or None
                )

            typer.echo(f"Labels updated for {len(msg_ids)} message(s)")

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

        service = get_gmail_service()
        past_tense = "Restored" if untrash else "Trashed"
        verb = "restore" if untrash else "trash"

        if message_id is not None:
            if untrash:
                untrash_message(service, message_id)
            else:
                trash_message(service, message_id)
            typer.echo(f"{past_tense} message {message_id}")
        else:
            label_map = get_label_map(service)
            results = search_emails(service, query, max_results, days, label_map=label_map)
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
                    untrash_message(service, mid)
                else:
                    trash_message(service, mid)

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
):
    """
    Iobox - Gmail to Markdown Converter

    Use commands to interact with Gmail and convert emails to Markdown.
    """
    pass


def run():
    app()


if __name__ == "__main__":
    run()
