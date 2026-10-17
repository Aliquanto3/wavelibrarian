"""Commande `wl` : point d'entrée du banc."""

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from wavelibrarian import registry
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import (
    BudgetExceeded,
    ConfigError,
    ProviderError,
    ValidationFailed,
    WlError,
)
from wavelibrarian.core.types import ParsedCorpus
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest, nom_parser_resolu, parsers_par_format
from wavelibrarian.corpus.profile import profile as profil_corpus
from wavelibrarian.corpus.scenario import corpus_apres as scenario_corpus_apres
from wavelibrarian.corpus.tiers import tirer_chemins
from wavelibrarian.evalset import check, closed_book, generate, io
from wavelibrarian.llm.preflight import preflight
from wavelibrarian.measure.tokenizers import make_tokenizer
from wavelibrarian.runner import installer as installation
from wavelibrarian.runner.context import Context

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


def _corpus_apres(parsed: ParsedCorpus, scenario: Path, lang: str) -> ParsedCorpus:
    """Corpus après application du Scénario (story 2.6) ; `lang` : langue par défaut du Corpus."""
    if not scenario.is_file():
        raise ConfigError(str(scenario), "fichier de Scénario introuvable")
    return scenario_corpus_apres(parsed, scenario, lang=lang)


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
        declare_corpus = declare(corpus)
        parsed = ingest(declare_corpus)
        apres = _corpus_apres(parsed, scenario, declare_corpus.spec.lang) if scenario else None
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


def _contexte_hors_execution(profil: str, seed: int) -> Context:
    """Contexte d'une commande hors Exécution (traces dans `WL_HOME/hors-execution/<run_id>/`)."""
    run_id = f"questions-{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    wl_home = Path(os.environ.get("WL_HOME") or ".wl")
    return Context.from_profile(profil, wl_home=wl_home, run_id=run_id, seed=seed)


@questions_app.command("generer")
def questions_generer(
    corpus_yaml: Annotated[Path, typer.Argument(help="Fichier `corpus.yaml` du Corpus.")],
    repartition: Annotated[
        str, typer.Option("--repartition", help="Questions par Type : factual=40,multi_hop=20.")
    ],
    modele: Annotated[
        str | None, typer.Option("--modele", help="Modèle de génération (défaut : profil).")
    ] = None,
    questions: Annotated[
        Path | None,
        typer.Option("--questions", help="Fichier de Questions (défaut : à côté de corpus.yaml)."),
    ] = None,
    cible: Annotated[
        int | None,
        typer.Option("--cible", help="`target_count` d'un nouveau fichier (défaut : le total)."),
    ] = None,
    profil: Annotated[str, typer.Option("--profil", help="Profil : cpu, gpu ou test.")] = "cpu",
    graine: Annotated[int, typer.Option("--graine", help="Graine de l'échantillon.")] = 42,
) -> None:
    """Ajoute des Questions `generated` ancrées dans le Corpus, dans la limite du Plafond."""
    fichier = questions or corpus_yaml.parent / "questions.yaml"
    try:
        demande = generate.parse_repartition(repartition)
        if cible is not None and cible < 1:
            raise ConfigError("--cible", "un entier au moins égal à 1 est attendu")
        reglages = load_profile(profil)
        nom_modele = modele or reglages.defaults.question_gen_model
        load_catalog().get(nom_modele)  # modèle inconnu du Catalogue : code 2, avant tout appel
        parsed = ingest(declare(corpus_yaml))
        if fichier.exists():
            existant = io.load(fichier)
        else:
            existant = io.QuestionsFile(
                corpus_id=parsed.corpus_id,
                target_count=sum(demande.values()) if cible is None else cible,
                questions=(),
            )
        if existant.corpus_id != parsed.corpus_id:
            raise ConfigError(
                str(fichier),
                f"le fichier vise le Corpus {existant.corpus_id!r}, pas {parsed.corpus_id!r}",
            )
        if existant.freeze is not None:
            raise ConfigError(
                str(fichier), "jeu gelé : y ajouter des Questions casserait l'empreinte"
            )
    except ConfigError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    try:
        with _contexte_hors_execution(profil, graine) as ctx:
            res = generate.generer(ctx, parsed, existant, demande, nom_modele)
    except BudgetExceeded as erreur:
        typer.echo(f"Plafond atteint : {erreur} ; aucune Question écrite.", err=True)
        raise typer.Exit(3) from erreur
    except ConfigError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    except ProviderError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(4) from erreur
    except WlError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(1) from erreur
    if res.ajoutees:
        io.save(fichier, res.fichier)
    typer.echo(f"Questions ajoutées : {len(res.ajoutees)} ({fichier})")
    for q in res.ajoutees:
        typer.echo(f"  - {q.id} ({q.type}) : {q.text}")
    typer.echo(f"Rejetées à la génération : {len(res.rejetees)}")
    for r in res.rejetees:
        typer.echo(f"  - {r.type} : {r.motif}")
    if res.en_trop:
        typer.echo(f"Écartées en surplus de la répartition : {res.en_trop}")
    for type_, n in res.manquantes.items():
        typer.echo(f"Manquantes pour {type_} : {n}")
    origine = "servi par le Cache de réponses" if res.depuis_cache else "appel au modèle"
    typer.echo(f"Coût : {res.cout.replace('.', ',')} ({origine}), Poste evalset.")


@questions_app.command("closed-book")
def questions_closed_book(
    questions: Annotated[Path, typer.Argument(help="Fichier questions.yaml à filtrer.")],
    modeles: Annotated[
        str | None,
        typer.Option("--modeles", help="Modèles interrogés, séparés par des virgules."),
    ] = None,
    profil: Annotated[str, typer.Option("--profil", help="Profil : cpu, gpu ou test.")] = "cpu",
    graine: Annotated[int, typer.Option("--graine", help="Graine de l'Exécution.")] = 42,
) -> None:
    """Remplit `contaminated_by` : modèles qui connaissent déjà la Réponse (Filtre closed-book)."""
    try:
        jeu = io.load(questions)
        reglages = load_profile(profil)
        noms = (
            [m.strip() for m in modeles.split(",")]
            if modeles is not None
            else list(reglages.defaults.closed_book_models)
        )
        closed_book.valider_modeles(noms, load_catalog())  # inconnu au Catalogue : code 2
    except ConfigError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    try:
        with _contexte_hors_execution(profil, graine) as ctx:
            res = closed_book.filtrer(ctx, jeu, noms)
    except BudgetExceeded as erreur:
        typer.echo(f"Plafond atteint : {erreur} ; fichier inchangé.", err=True)
        raise typer.Exit(3) from erreur
    except ConfigError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    except ProviderError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(4) from erreur
    except WlError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(1) from erreur
    if res.fichier != jeu:
        io.save(questions, res.fichier)  # seul `contaminated_by` change : le Gel reste valide
    posees = len({v.question_id for v in res.verdicts})
    typer.echo(f"Modèles interrogés : {', '.join(noms)}")
    typer.echo(f"Questions posées : {posees} ; non posées (unanswerable) : {len(res.exclues)}")
    contaminees = res.contaminees
    typer.echo(f"Questions contaminées : {len(contaminees)}")
    for qid, ms in contaminees.items():
        typer.echo(f"  - {qid} : {', '.join(ms)}")
    typer.echo("Poste de coût : judging.")


def _fr(valeur: float, decimales: int = 2) -> str:
    """Nombre à virgule décimale, pour les résumés en français."""
    return f"{valeur:.{decimales}f}".replace(".", ",")


corpus_app = typer.Typer(help="Déclarer, ingérer et profiler un Corpus.", no_args_is_help=True)
app.add_typer(corpus_app, name="corpus")


@corpus_app.command("profiler")
def corpus_profiler(
    corpus_yaml: Annotated[Path, typer.Argument(help="Fichier `corpus.yaml` du Corpus.")],
    parser: Annotated[
        str, typer.Option("--parser", help="Parser à utiliser, ou `auto` (un par format).")
    ] = "auto",
    profil: Annotated[
        str, typer.Option("--profil", help="Profil d'exécution (tokenizer) : cpu, gpu ou test.")
    ] = "cpu",
    sortie: Annotated[
        Path, typer.Option("--sortie", help="Dossier où écrire `corpus_profile.json`.")
    ] = Path("."),
) -> None:
    """Ingère le Corpus et écrit son Profil (`corpus_profile.json`) avec un résumé."""
    try:
        declare_corpus = declare(corpus_yaml)
        reglages = load_profile(profil)
        nom = nom_parser_resolu(parsers_par_format(declare_corpus.formats, parser))
        parse = ingest(declare_corpus, parser)
        p = profil_corpus(
            parse,
            parser=nom,
            tokenizer=make_tokenizer(reglages.tokenizer),
            volatility=declare_corpus.spec.volatility,
        )
    except ConfigError as erreur:
        typer.echo(f"Configuration invalide : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    except WlError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(1) from erreur
    fichier = sortie / "corpus_profile.json"
    try:
        sortie.mkdir(parents=True, exist_ok=True)
        fichier.write_text(
            json.dumps(p.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as erreur:
        typer.echo(f"Erreur : écriture de {fichier} impossible ({erreur.strerror})", err=True)
        raise typer.Exit(1) from erreur
    formats = ", ".join(f"{k} : {v}" for k, v in p.formats.items())
    langues = ", ".join(f"{k} : {v}" for k, v in p.langs.items())
    typer.echo(f"Profil du Corpus « {p.corpus_id} » (empreinte {p.fingerprint}) écrit : {fichier}")
    typer.echo(f"  Documents : {p.n_documents} ({formats})")
    typer.echo(
        f"  Tokens : {p.n_tokens} (tokenizer {p.tokenizer}), "
        f"{_fr(p.mean_tokens_per_document, 1)} par Document"
    )
    typer.echo(
        f"  Profondeur de titres : max {p.heading_depth_max}, moyenne {_fr(p.heading_depth_mean)}"
    )
    typer.echo(
        f"  Densité de liens : {_fr(p.link_density)} ; part tabulaire : {_fr(p.table_share)}"
    )
    typer.echo(f"  Images par Document : {_fr(p.images_per_document)}")
    typer.echo(f"  Langue dominante : {p.dominant_lang} ({langues}) ; volatilité : {p.volatility}")


@corpus_app.command("paliers")
def corpus_paliers(
    corpus_yaml: Annotated[Path, typer.Argument(help="Fichier `corpus.yaml` du Corpus.")],
    parser: Annotated[
        str, typer.Option("--parser", help="Parser à utiliser, ou `auto` (un par format).")
    ] = "auto",
) -> None:
    """Ingère le Corpus et affiche ses Paliers de volume (clé `tiers`), avec leurs Documents.

    Le tirage porte sur les Documents ingérés, comme celui du runner : un Document illisible,
    écarté par l'ingestion, n'entre dans aucun Palier. Sans `required_paths` (fournis par le
    runner à partir des Questions).
    """
    try:
        declare_corpus = declare(corpus_yaml)
        tiers = declare_corpus.spec.tiers
        if tiers is None:
            typer.echo(f"Le Corpus « {declare_corpus.corpus_id} » ne déclare pas de clé `tiers`.")
            return
        parse = ingest(declare_corpus, parser)
        tirage = tirer_chemins((d.source_path for d in parse.documents), tiers)
    except ConfigError as erreur:
        typer.echo(f"Configuration invalide : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    except WlError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(1) from erreur
    typer.echo(f"Paliers du Corpus « {declare_corpus.corpus_id} » (graine {tiers.seed}) :")
    for taille, chemins in tirage.items():
        typer.echo(f"Palier {taille} ({len(chemins)} Documents) :")
        for chemin in chemins:
            typer.echo(f"  {chemin}")
