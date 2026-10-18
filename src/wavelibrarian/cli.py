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
from wavelibrarian.evalset import check, closed_book, freeze, generate, io
from wavelibrarian.llm.preflight import preflight
from wavelibrarian.measure.tokenizers import make_tokenizer
from wavelibrarian.report.export import exporter_front as exporter_front_vers
from wavelibrarian.report.generer import generer_rapport
from wavelibrarian.runner import installer as installation
from wavelibrarian.runner.calibrer import calibrer as calibration
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.execute import load_questions, run_experiment, verifier_paliers
from wavelibrarian.runner.resume import deja_terminee, verifier_reprise
from wavelibrarian.runner.rundir import RUN_ID

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
    reprendre: Annotated[
        str | None,
        typer.Option(
            "--reprendre",
            help="run_id d'une Exécution arrêtée à reprendre : seules les clés absentes sont "
            "refaites (plafonds relevables ; toute autre différence d'Expérience est refusée).",
        ),
    ] = None,
) -> None:
    """Valide une Expérience, vérifie ses dépendances (préflight), puis l'exécute.

    Codes de sortie : 0 succès, 1 erreur (dont une autre Exécution en cours), 2 configuration
    invalide (Jeu non Gelé ou modifié compris, reprise d'une Expérience différente), 3 plafond
    atteint, 4 préflight échoué.
    """
    try:
        resultat = validate_file(experience)
    except ValidationFailed as echec:
        typer.echo(f"Expérience invalide : {len(echec.errors)} erreur(s).", err=True)
        for e in echec.errors:
            typer.echo(f"  - {e.path} : {e.message}", err=True)
        raise typer.Exit(2) from echec
    typer.echo("Validation réussie.")
    wl_home = Path(os.environ.get("WL_HOME") or ".wl")
    termine = False
    try:  # Gel vérifié à la validation, avant le préflight et tout appel (AD-11, AD-15)
        questions = load_questions(resultat.resolved)
        verifier_paliers(resultat.resolved, questions)  # Palier non déclaré : code 2
        if reprendre is not None:  # Expérience ou Gel différents de l'Exécution : code 2
            verifier_reprise(resultat.resolved, wl_home, reprendre, questions.freeze_sha256)
            termine = deja_terminee(wl_home, reprendre)
    except ConfigError as erreur:
        typer.echo(f"Configuration invalide : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    if reprendre is not None and termine:  # reprise idempotente d'un run de nuit
        typer.echo(f"Exécution {reprendre} déjà terminée : rien à reprendre.")
        raise typer.Exit(0)
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
    try:
        issue = run_experiment(resultat.resolved, questions, wl_home=wl_home, reprendre=reprendre)
    except ConfigError as erreur:
        typer.echo(f"Configuration invalide : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    except WlError as erreur:  # dont « Exécution <run_id> en cours » (run.lock)
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(1) from erreur
    typer.echo(
        f"Exécution {issue.run_id} : {issue.status}, {issue.n_answers} Réponse(s) "
        f"dans {issue.run_dir}"
    )
    # Le Rapport se génère aussi sur les résultats partiels d'un arrêt au plafond (AD-1 : c'est
    # la CLI qui enchaîne le runner puis `report/`, le runner n'importe jamais `report`).
    rapport_ok = _ecrire_rapport(issue.run_dir, wl_home)
    if issue.status == "budget_exceeded":
        typer.echo("Plafond de dépense atteint : Exécution arrêtée.", err=True)
        raise typer.Exit(3)
    if issue.unjudged:
        typer.echo(
            f"{issue.unjudged} Critère(s) sans verdict de panel (Juge en échec) : "
            "relancer avec --reprendre.",
            err=True,
        )
    if issue.all_failed:
        typer.echo("Aucune Réponse valide : toutes les Questions sont en erreur.", err=True)
        raise typer.Exit(1)
    if not rapport_ok:
        raise typer.Exit(1)


def _ecrire_rapport(run_dir: Path, wl_home: Path) -> bool:
    """Génère `report/` ; un échec du Rapport est annoncé sans masquer l'issue de l'Exécution."""
    try:
        sortie = generer_rapport(run_dir, wl_home=wl_home)
    except Exception as erreur:  # jamais masquer le code de sortie de l'Exécution (3 au plafond)
        typer.echo(f"Rapport non généré : {type(erreur).__name__}: {erreur}", err=True)
        return False
    typer.echo(f"Rapport écrit dans {sortie}")
    return True


@app.command("rapport")
def rapport(
    run_id: Annotated[str, typer.Argument(help="Identifiant de l'Exécution (dossier de runs/).")],
    exporter_front: Annotated[
        str | None,
        typer.Option(
            "--exporter-front",
            help="Front de `pareto.csv` à exporter (`qualite-cout` : le front du Rapport).",
        ),
    ] = None,
    vers: Annotated[
        Path | None, typer.Option("--vers", help="Fichier écrit par --exporter-front.")
    ] = None,
) -> None:
    """Régénère le Rapport (`report/`) d'une Exécution, depuis ses seuls fichiers.

    Avec `--exporter-front <front> --vers <fichier>`, écrit aussi la liste `configurations:` des
    Configurations non dominées de ce front, réutilisable dans une nouvelle Expérience (FR-41).

    Codes de sortie : 0 succès, 1 erreur, 2 Exécution introuvable, Expérience illisible, front
    inconnu ou options `--exporter-front` et `--vers` non données ensemble.
    """
    if (exporter_front is None) != (vers is None):
        typer.echo("--exporter-front et --vers vont ensemble.", err=True)
        raise typer.Exit(2)
    wl_home = Path(os.environ.get("WL_HOME") or ".wl")
    dossier = wl_home / "runs" / run_id
    if not RUN_ID.fullmatch(run_id) or not dossier.is_dir():
        typer.echo(f"Exécution {run_id} introuvable dans {wl_home / 'runs'}.", err=True)
        raise typer.Exit(2)
    try:
        sortie = generer_rapport(dossier, wl_home=wl_home)
        typer.echo(f"Rapport écrit dans {sortie}")
        if exporter_front is not None and vers is not None:
            ids = exporter_front_vers(dossier, exporter_front, vers)
            typer.echo(f"Front {exporter_front} ({len(ids)} Configuration(s)) écrit dans {vers}")
    except ConfigError as erreur:
        typer.echo(f"Configuration invalide : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    except (WlError, OSError, ValueError) as erreur:
        typer.echo(f"Rapport non généré : {erreur}", err=True)
        raise typer.Exit(1) from erreur


@app.command("calibrer")
def calibrer(
    experience: Annotated[Path, typer.Argument(help="Fichier YAML de l'Expérience (Juges).")],
    annotations: Annotated[
        Path, typer.Option("--annotations", help="Dossier d'annotations (un YAML par annotateur).")
    ],
    run: Annotated[str, typer.Option("--run", help="Identifiant de l'Exécution annotée.")],
    sortie: Annotated[
        Path | None,
        typer.Option(
            "--sortie", help="Chemin de calibration.json (défaut : dossier de l'Exécution)."
        ),
    ] = None,
) -> None:
    """Calibre les Juges du réservoir sur des annotations humaines et écrit `calibration.json`.

    Chaque Juge note chaque Réponse annotée `judges.calibration_passes` fois (Poste judging).
    Un Juge dont le kappa est sous `judges.kappa_threshold` est exclu : renseigner
    `judges.excluded_from` dans l'Expérience suivante. Codes de sortie : 0 succès, 1 erreur,
    2 configuration invalide (Exécution inconnue, aucune annotation valide), 3 plafond atteint,
    4 préflight échoué.
    """
    wl_home = Path(os.environ.get("WL_HOME") or ".wl")
    try:
        resultat = validate_file(experience)
    except ValidationFailed as echec:
        typer.echo(f"Expérience invalide : {len(echec.errors)} erreur(s).", err=True)
        for e in echec.errors:
            typer.echo(f"  - {e.path} : {e.message}", err=True)
        raise typer.Exit(2) from echec
    exp = resultat.resolved
    modeles = set(exp.judges.pool or ())
    if exp.judges.calibration_judge is not None:
        modeles.add(exp.judges.calibration_judge)
    if not (wl_home / "runs" / run / "answers.jsonl").is_file():  # code 2 avant le préflight
        typer.echo(f"Exécution {run} introuvable dans {wl_home / 'runs'}.", err=True)
        raise typer.Exit(2)
    verdict = preflight(modeles, resultat.catalog, exp.profile_settings)
    if not verdict.ok:
        typer.echo(
            f"Préflight échoué : {len(verdict.errors)} dépendance(s) manquante(s).", err=True
        )
        for e in verdict.errors:
            typer.echo(f"  - {e}", err=True)
        raise typer.Exit(4)
    try:
        res, chemin = calibration(exp, annotations, run, wl_home=wl_home, sortie=sortie)
    except BudgetExceeded as erreur:
        typer.echo(f"Plafond atteint : {erreur} ; calibration non écrite.", err=True)
        raise typer.Exit(3) from erreur
    except ConfigError as erreur:
        typer.echo(f"Configuration invalide : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    except ProviderError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(4) from erreur
    except WlError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(1) from erreur
    d = res.donnees
    typer.echo(
        f"Calibration de l'Exécution {run} : {len(d['judges'])} Juge(s), "
        f"{res.n_appels} appel(s), {d['passes']} passe(s), "
        f"seuil de kappa {_fr(d['kappa_threshold'])}."
    )
    for modele, fiche in d["judges"].items():
        for critere, f in fiche["criteria"].items():
            kappa = "indéfini" if f["kappa"] is None else _fr(f["kappa"])
            instab = "indéfinie" if f["instability"] is None else _fr(f["instability"])
            typer.echo(
                f"  - {modele} / {critere} : kappa {kappa}, instabilité {instab}, "
                f"{f['n_items']} item(s)"
            )
    for paire in d["inter_annotator"]:
        for critere, f in paire["criteria"].items():
            kappa = "indéfini" if f["kappa"] is None else _fr(f["kappa"])
            typer.echo(
                f"  - annotateurs {' et '.join(paire['annotators'])} / {critere} : "
                f"kappa {kappa}, {f['n_items']} Réponse(s)"
            )
    if "calibration_judge" in d:
        cj = d["calibration_judge"]
        for critere, f in cj["criteria"].items():
            kappa = "indéfini" if f["kappa"] is None else _fr(f["kappa"])
            typer.echo(f"  - juge de calibration {cj['model']} / {critere} : kappa {kappa}")
    for modele, raison in res.exclus.items():
        typer.echo(f"Juge exclu : {modele} ({raison}).")
    if not res.exclus:
        typer.echo("Aucun Juge exclu.")
    for a in res.avertissements:
        typer.echo(f"Avertissement : {a}", err=True)
    if res.ignorees:
        typer.echo(f"Annotations ignorées (Réponse absente de l'Exécution) : {len(res.ignorees)}")
    cout = ", ".join(f"{str(m.normalize()).replace('.', ',')} {dev}" for dev, m in res.cout.items())
    typer.echo(f"Coût des Juges (Poste judging) : {cout or '0'}.")
    typer.echo(f"Calibration écrite : {chemin}")


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


@questions_app.command("geler")
def questions_geler(
    questions: Annotated[Path, typer.Argument(help="Fichier questions.yaml à geler.")],
    dev_ratio: Annotated[
        float, typer.Option("--dev-ratio", help="Part de Questions dev dans chaque Type.")
    ] = freeze.DEV_RATIO_DEFAUT,
    graine: Annotated[int, typer.Option("--graine", help="Graine de la répartition.")] = 42,
    forcer: Annotated[
        bool, typer.Option("--forcer", help="Accepter qu'un re-Gel change la partie de Questions.")
    ] = False,
) -> None:
    """Répartit les Questions en dev / test (stratifié par Type) et écrit l'empreinte du Gel."""
    try:
        jeu = io.load_agrege(questions)
        gele = freeze.geler(jeu, dev_ratio, graine, forcer=forcer)
    except ValidationFailed as erreur:
        for e in erreur.errors:
            typer.echo(f"Erreur : {e}", err=True)
        typer.echo(f"{len(erreur.errors)} erreur(s) ; fichier inchangé.", err=True)
        raise typer.Exit(2) from erreur
    except ConfigError as erreur:
        typer.echo(f"Erreur : {erreur}", err=True)
        raise typer.Exit(2) from erreur
    io.save(questions, gele)
    par: dict[str, dict[str, int]] = {}
    for q in gele.questions:
        if q.split is not None:
            parts = par.setdefault(q.type, {"dev": 0, "test": 0})
            parts[q.split] += 1
    typer.echo(f"Jeu gelé : {questions} (graine {graine}, dev {_fr(dev_ratio)}).")
    for type_, parts in par.items():
        typer.echo(f"  - {type_} : dev {parts['dev']}, test {parts['test']}")
    typer.echo(f"Hors répartition (rejected) : {sum(1 for q in gele.questions if q.split is None)}")
    if gele.freeze is not None:
        typer.echo(f"Empreinte : {gele.freeze.sha256}")


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
