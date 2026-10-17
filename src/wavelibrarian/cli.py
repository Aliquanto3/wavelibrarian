"""Commande `wl` : point d'entrée du banc."""

from pathlib import Path
from typing import Annotated

import typer

from wavelibrarian import registry
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import ConfigError, ProviderError, ValidationFailed, WlError
from wavelibrarian.llm.preflight import preflight
from wavelibrarian.runner import installer as installation

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
    """Valide une Expérience, vérifie ses dépendances (préflight) ; le runner arrive à l'epic 4."""
    try:
        resultat = validate_file(experience)
    except ValidationFailed as echec:
        typer.echo(f"Expérience invalide : {len(echec.errors)} erreur(s).", err=True)
        for e in echec.errors:
            typer.echo(f"  - {e.path} : {e.message}", err=True)
        raise typer.Exit(2) from echec
    typer.echo("Validation réussie.")
    modeles = {m for c in resultat.resolved.configurations for m in c.models}
    modeles |= set(resultat.resolved.judges.pool or ())
    if resultat.resolved.judges.calibration_judge is not None:
        modeles.add(resultat.resolved.judges.calibration_judge)
    verdict = preflight(modeles, resultat.catalog, resultat.resolved.profile_settings)
    if not verdict.ok:
        typer.echo(
            f"Préflight échoué : {len(verdict.errors)} dépendance(s) manquante(s).", err=True
        )
        for e in verdict.errors:
            typer.echo(f"  - {e}", err=True)
        raise typer.Exit(4)
    typer.echo("Préflight réussi.")


@app.command("installer")
def installer(
    profil: Annotated[
        str, typer.Option("--profil", help="Profil à préparer : cpu ou gpu.")
    ] = "cpu",
) -> None:
    """Télécharge l'embedder et l'encodage tiktoken, puis vérifie `ollama list`."""
    try:
        res = installation.installer(profil)
    except ProviderError as erreur:  # Ollama injoignable : code 4 du contrat (contracts.md §8)
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(4) from erreur
    except WlError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(1) from erreur
    typer.echo(f"Encodage tiktoken {res.encodage} prêt.")
    typer.echo(f"Embedder {res.embedder} prêt.")
    if not res.ollama_manquants:
        typer.echo("Modèles Ollama du profil : tous présents.")
        return
    typer.echo("Modèles Ollama manquants (à tirer à la main) :", err=True)
    for m in res.ollama_manquants:
        typer.echo(f"  - ollama pull {m}", err=True)
    raise typer.Exit(4)
