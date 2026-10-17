"""Commande `wl` : point d'entrée du banc."""

from typing import Annotated

import typer

from wavelibrarian import registry
from wavelibrarian.core.errors import ConfigError

app = typer.Typer(
    name="wl",
    help="WaveLibrarian : banc de comparaison des architectures de recherche documentaire IA.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def principal() -> None:
    """WaveLibrarian : banc de comparaison des architectures de recherche documentaire IA."""


@app.command("registre")
def registre(
    kind: Annotated[str | None, typer.Option("--kind", help="Limite la liste à ce kind.")] = None,
) -> None:
    """Liste les Composants et Architectures enregistrés, avec leurs paramètres."""
    registry.discover()
    try:
        entrees = registry.list_components(kind)
    except ConfigError as erreur:
        typer.echo(f"Erreur : {erreur.message}", err=True)
        raise typer.Exit(2) from erreur
    if not entrees:
        typer.echo("Aucun Composant enregistré.")
        return
    for e in entrees:
        typer.echo(f"{e.kind} / {e.name} : {e.description or '(sans description)'}")
        if not e.params:
            typer.echo("    Params : aucun")
        for p in e.params:
            typer.echo(f"    - {p.name} ({p.type}), défaut : {p.default}")
