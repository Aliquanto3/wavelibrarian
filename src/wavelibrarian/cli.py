"""Commande `wl` : point d'entrée du banc."""

import importlib
from pathlib import Path
from typing import Annotated

import typer

from wavelibrarian import registry
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import ConfigError, ProviderError, ValidationFailed, WlError
from wavelibrarian.core.types import ParsedCorpus
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.evalset import check, io
from wavelibrarian.llm.preflight import preflight
from wavelibrarian.runner import installer as installation

app = typer.Typer(
    name="wl",
    help="WaveLibrarian : banc de comparaison des architectures de recherche documentaire IA.",
    no_args_is_help=True,
    add_completion=False,
)


questions_app = typer.Typer(
    help="Jeu d'évaluation : contrôle des Questions.", no_args_is_help=True, add_completion=False
)
app.add_typer(questions_app, name="questions")


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


def _corpus_apres(parsed: ParsedCorpus, scenario: Path) -> ParsedCorpus:
    """Corpus après application du Scénario (story 2.6 ; `ConfigError` tant qu'elle manque)."""
    if not scenario.is_file():
        raise ConfigError(str(scenario), "fichier de Scénario introuvable")
    try:
        module = importlib.import_module("wavelibrarian.corpus.scenario")
    except ImportError as exc:
        raise ConfigError(
            "--scenario",
            "l'application d'un Scénario n'est pas encore disponible dans cette version",
        ) from exc
    return module.corpus_apres(parsed, scenario)  # type: ignore[no-any-return]


@questions_app.command("controler")
def questions_controler(
    questions: Annotated[Path, typer.Argument(help="Fichier questions.yaml à contrôler.")],
    corpus: Annotated[Path, typer.Option("--corpus", help="Fichier corpus.yaml du Corpus.")],
    scenario: Annotated[
        Path | None,
        typer.Option("--scenario", help="Scénario : résout les Questions `scenario_target`."),
    ] = None,
) -> None:
    """Compte les Questions, signale les Ancrages introuvables (code 2 si Question validée)."""
    try:
        jeu = io.load(questions)
        parsed = ingest(declare(corpus))
        apres = _corpus_apres(parsed, scenario) if scenario else None
    except ConfigError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    if jeu.corpus_id != parsed.corpus_id:
        typer.echo(
            f"Erreur : le fichier de Questions vise le Corpus {jeu.corpus_id!r}, "
            f"pas {parsed.corpus_id!r}.",
            err=True,
        )
        raise typer.Exit(2)
    res = check.controler(jeu, parsed, apres)
    typer.echo("Questions par statut : " + ", ".join(f"{s} {n}" for s, n in res.par_statut.items()))
    par_type = ", ".join(f"{t} {n}" for t, n in res.par_type.items()) or "aucune"
    typer.echo(f"Questions par Type : {par_type}")
    typer.echo(
        f"Utilisables (validated, corrected) : {res.utilisables} sur {res.target_count} visées, "
        f"écart {res.ecart:+d}."
    )
    for s in res.signalements:
        typer.echo(f"  - {s.question_id} : {s.message}" + ("" if s.bloquant else " (signalé)"))
    if res.echec:
        typer.echo("Contrôle échoué.", err=True)
        raise typer.Exit(2)
    typer.echo("Contrôle réussi.")
