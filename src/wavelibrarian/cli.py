"""Commande `wl` : point d'entrée du banc."""

from pathlib import Path
from typing import Annotated

import typer

from wavelibrarian import registry
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import ConfigError, ValidationFailed

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


@app.command("run")
def run(
    experience: Annotated[
        Path, typer.Argument(help="Fichier YAML de l'Expérience à valider puis exécuter.")
    ],
) -> None:
    """Valide une Expérience (sans réseau) ; le runner arrive à l'epic 4."""
    try:
        validate_file(experience)
    except ValidationFailed as echec:
        typer.echo(f"Expérience invalide : {len(echec.errors)} erreur(s).", err=True)
        for e in echec.errors:
            typer.echo(f"  - {e.path} : {e.message}", err=True)
        raise typer.Exit(2) from echec
    typer.echo("Validation réussie.")
