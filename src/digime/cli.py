import typer

from digime.config import settings

app = typer.Typer(help="DigiMe local personal reply agent.")


@app.command()
def doctor() -> None:
    """Print the active local configuration."""
    typer.echo(f"env: {settings.env}")
    typer.echo(f"draft_only: {settings.draft_only}")
    typer.echo(f"llm_provider: {settings.llm_provider}")
    typer.echo(f"llm_model: {settings.llm_model}")
    typer.echo(f"llm_base_url: {settings.llm_base_url}")


@app.command()
def draft(message: str, platform: str = "slack", profile: str = "work_slack") -> None:
    """Placeholder command for drafting a reply."""
    typer.echo("Drafting is not implemented yet.")
    typer.echo(f"platform: {platform}")
    typer.echo(f"profile: {profile}")
    typer.echo(f"message: {message}")


if __name__ == "__main__":
    app()

