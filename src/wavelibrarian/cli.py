"""Commande `wl` : point d'entrée du banc."""

import typer

app = typer.Typer(
    name="wl",
    help="WaveLibrarian : banc de comparaison des architectures de recherche documentaire IA.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def principal() -> None:
    """WaveLibrarian : banc de comparaison des architectures de recherche documentaire IA."""
