"""Rejugement d'une Exécution terminée (`wl rejuger <run_id> <experience.yaml>`, story 9.6).

Une nouvelle Exécution (`rejudged_from: <run_id>` au manifeste) reprend telles quelles, pour les
seules Questions du split courant du Jeu gelé, les Réponses, les traces de génération (spans des
Postes autres que `judging`, mesures comprises), le Profil et l'applicabilité de la source ; seuls
les Critères automatiques et le Panel de l'Expérience fournie sont recalculés, par le chemin de
jugement de `wl run` (`_Runner.juger`). Les Réponses gardent leur `answer_id` (préfixe du
`run_id` source) : leurs lignes sont copiées octet pour octet, et les annotations humaines faites
sur la source s'y rapportent toujours.

Seuls `judges`, `budget` et `max_error_rate` peuvent différer de l'Expérience de la source. Le
Catalogue (`catalog`, `catalog_date`, `models_frozen_at`) peut changer : seuls les Juges sont
rappelés, les coûts de génération copiés sont ceux des spans de la source. Le Corpus, le Scénario
et le Jeu sont comparés par leur contenu, pas par leur chemin. Le Gel du Jeu peut différer par le
seul `split` des Questions (c'est l'usage : rejuger après un re-Gel) ; les Questions sorties du
split courant sont alors écartées et listées (`excluded_questions`).
"""

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wavelibrarian.config.experiment import ResolvedExperiment
from wavelibrarian.core.bilan import causes_execution
from wavelibrarian.core.errors import BudgetExceeded, ConfigError
from wavelibrarian.core.ids import canonical_json, new_run_id, sha16
from wavelibrarian.corpus.declare import declare
from wavelibrarian.evalset import io as jeu_io
from wavelibrarian.evalset.freeze import PARTICIPANTES, empreinte
from wavelibrarian.llm.gateway import Providers
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.execute import (
    FrozenQuestions,
    RunOutcome,
    RunStatus,
    _Runner,  # pyright: ignore[reportPrivateUsage]
    load_questions,
    panels_de,
)
from wavelibrarian.runner.resume import (
    charger_resolue,
    deja_terminee,
    empreintes_entrees,
    verifier_reprise,
)
from wavelibrarian.runner.rundir import (
    RUN_ID,
    attach_run_log,
    create_run_dir,
    detach_run_log,
    reopen_run_dir,
    resolve_parsers,
    set_status,
)

log = logging.getLogger(__name__)

# Seules sections de l'Expérience qui peuvent différer de la source (AC 2 de la story 9.6).
MODIFIABLES = ("judges", "budget", "max_error_rate")
# Le Catalogue peut changer (tarif, nouveau Juge, date de gel des modèles) : les coûts de
# génération copiés sont ceux écrits dans les spans de la source.
_CATALOGUE = ("catalog", "catalog_date", "models_frozen_at")
# Chemins comparés par leur contenu dans `verifier_source` (empreintes `inputs`, Gel du Jeu).
_PAR_CONTENU = ("corpus", "questions", "scenario")
_IGNOREES = MODIFIABLES + _CATALOGUE + _PAR_CONTENU
_ENTREES = {
    "corpus_fingerprint": ("corpus", "le Corpus"),
    "scenario_fingerprint": ("scenario", "le Scénario"),
}
_SOURCES_ADMISES = ("completed", "completed_with_errors")


@dataclass(frozen=True)
class Source:
    run_id: str
    dossier: Path
    manifeste: dict[str, Any]


@dataclass(frozen=True)
class RejugementOutcome:
    outcome: RunOutcome
    rejudged_from: str
    excluded_questions: tuple[str, ...]


def _dossier(wl_home: Path, run_id: str, champ: str) -> Path:
    if not RUN_ID.fullmatch(run_id):  # jamais hors de runs/
        raise ConfigError(champ, f"run_id invalide : {run_id!r} (lettres, chiffres, - et _)")
    return wl_home / "runs" / run_id


def _manifeste(dossier: Path, champ: str) -> dict[str, Any]:
    try:
        return json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(champ, f"Exécution {dossier.name} introuvable ou illisible") from exc


def differences(source: ResolvedExperiment, demandee: ResolvedExperiment) -> list[str]:
    """Sections de l'Expérience résolue qui diffèrent, hors `MODIFIABLES`, Catalogue et chemins
    comparés par contenu ; une Configuration différente est nommée avec ses champs
    (`configurations.bm25.generator`), une autre section avec ses clés (`costs.pue`)."""
    a, b = source.model_dump(mode="json"), demandee.model_dump(mode="json")
    ecarts: list[str] = []
    for cle in sorted(set(a) | set(b)):
        if cle in _IGNOREES or a.get(cle) == b.get(cle):
            continue
        va, vb = a.get(cle), b.get(cle)
        if isinstance(va, dict) and isinstance(vb, dict):
            ecarts += [f"{cle}.{k}" for k in sorted(set(va) | set(vb)) if va.get(k) != vb.get(k)]
            continue
        if cle != "configurations":
            ecarts.append(cle)
            continue
        avant = len(ecarts)
        ca = {c["id"]: c for c in a.get(cle) or ()}
        cb = {c["id"]: c for c in b.get(cle) or ()}
        for i in sorted(set(ca) - set(cb)):
            ecarts.append(f"configurations.{i} (absente de l'Expérience)")
        for i in sorted(set(cb) - set(ca)):
            ecarts.append(f"configurations.{i} (absente de la source)")
        for i in sorted(set(ca) & set(cb)):
            champs = sorted(k for k in set(ca[i]) | set(cb[i]) if ca[i].get(k) != cb[i].get(k))
            ecarts += [f"configurations.{i}.{k}" for k in champs]
        if len(ecarts) == avant:  # mêmes Configurations, dans un autre ordre
            ecarts.append("configurations (ordre)")
    return ecarts


def _jeu_conforme(experience: ResolvedExperiment, gel_source: object, posees: set[str]) -> bool:
    """Le Jeu courant ne diffère-t-il du Gel `gel_source` que par le `split` des Questions ?

    La source ne garde que l'empreinte de son Gel (contenu et `split` mêlés) : on rend aux
    Questions le `split` qu'elles avaient pour la source (`posees`, celles qu'elle a posées, dans
    `experience.split` ; les autres Questions participantes de ce split, dans l'autre) et on
    recalcule l'empreinte. Avec `max_questions`, les Questions non posées gardent leur `split`."""
    doc = jeu_io.load(Path(experience.questions))
    if doc.freeze is not None and doc.freeze.sha256 == gel_source:
        return True
    autre = "test" if experience.split == "dev" else "dev"
    remises = tuple(
        q.model_copy(update={"split": experience.split})
        if q.id in posees
        else q.model_copy(update={"split": autre})
        if experience.max_questions is None
        and q.split == experience.split
        and q.status in PARTICIPANTES
        else q
        for q in doc.questions
    )
    return empreinte(doc.model_copy(update={"questions": remises})) == gel_source


def verifier_source(experience: ResolvedExperiment, wl_home: Path, source_id: str) -> Source:
    """Contrôles avant tout appel ; `ConfigError` (code 2) sinon. `experience` a ses parsers
    résolus. La source doit être terminée (`completed` ou `completed_with_errors`) et avoir des
    Réponses ; l'Expérience ne peut différer que par `judges`, `budget`, `max_error_rate` et le
    Catalogue ; le Corpus et le Scénario (contenu) doivent être ceux de la source ; le Jeu courant
    ne peut différer du Gel de la source que par le `split`, et chaque Question du split courant
    doit avoir une Réponse dans la source."""
    dossier = _dossier(wl_home, source_id, "rejuger")
    manifeste = _manifeste(dossier, "rejuger")
    statut = manifeste.get("status")
    if statut not in _SOURCES_ADMISES:
        raise ConfigError(
            "rejuger", f"Exécution {source_id} non terminée (statut {statut}) : rien à rejuger"
        )
    resolue = charger_resolue(dossier)
    ecarts = differences(resolue, experience)
    brutes = manifeste.get("inputs")
    stockees: dict[str, Any] = brutes if isinstance(brutes, dict) else {}
    if (resolue.scenario is None) != (experience.scenario is None):
        ecarts.append("scenario")
    for cle, (champ, _) in _ENTREES.items():  # sans empreinte stockée : le chemin
        if cle not in stockees and getattr(resolue, champ) != getattr(experience, champ):
            ecarts.append(champ)
    if ecarts:
        raise ConfigError(
            "rejuger",
            f"l'Expérience diffère de celle de l'Exécution {source_id} : "
            f"{', '.join(sorted(set(ecarts)))} (seuls {', '.join(MODIFIABLES)} peuvent changer)",
        )
    if stockees:
        actuelles = empreintes_entrees(experience, wl_home)
        for cle, (_, quoi) in _ENTREES.items():
            if stockees.get(cle) != actuelles.get(cle):
                raise ConfigError(
                    "rejuger", f"{quoi} n'est plus celui de l'Exécution {source_id} ({cle})"
                )
    posees = {o["question_id"] for _, o in reponses_source(dossier).values()}
    if not posees:
        raise ConfigError("rejuger", f"Exécution {source_id} sans Réponse : rien à rejuger")
    courantes = {q.id for q in load_questions(experience).questions}
    if manquantes := sorted(courantes - posees):
        raise ConfigError(
            "rejuger",
            f"Questions du split {experience.split} courant sans Réponse dans l'Exécution "
            f"{source_id} (wl run les pose) : {', '.join(manquantes)}",
        )
    if not _jeu_conforme(experience, manifeste.get("freeze_sha256"), posees):
        raise ConfigError(
            "rejuger",
            f"le Jeu {experience.questions} diffère du Gel de l'Exécution {source_id} au-delà "
            "du split des Questions (texte, référence, Ancrages…) : ses Réponses ne se "
            "rejugent pas",
        )
    return Source(source_id, dossier, manifeste)


def verifier_reprise_rejugement(
    experience: ResolvedExperiment, wl_home: Path, source_id: str, reprendre: str, freeze: str
) -> None:
    """Reprise d'un rejugement : contrôles de `wl run --reprendre` (Expérience à plafonds égaux,
    Juges compris, Gel courant, entrées), et le rejugement doit venir de `source_id`."""
    verifier_reprise(experience, wl_home, reprendre, freeze)
    origine = _manifeste(_dossier(wl_home, reprendre, "reprendre"), "reprendre").get(
        "rejudged_from"
    )
    if origine != source_id:
        raise ConfigError(
            "reprendre", f"l'Exécution {reprendre} n'est pas un rejugement de {source_id}"
        )


def _lignes(chemin: Path) -> list[tuple[str, dict[str, Any]]]:
    """Lignes brutes et objets d'un JSONL ; une ligne illisible (dernière ligne tronquée d'un
    arrêt brutal) est ignorée, comme `lire_jsonl`."""
    if not chemin.is_file():
        return []
    sortie: list[tuple[str, dict[str, Any]]] = []
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        try:
            objet = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(objet, dict):
            sortie.append((ligne, objet))
    return sortie


def reponses_source(dossier: Path) -> dict[str, tuple[str, dict[str, Any]]]:
    """Dernière ligne brute de chaque `answer_id` d'`answers.jsonl` (elle fait foi)."""
    effectives: dict[str, tuple[str, dict[str, Any]]] = {}
    for ligne, objet in _lignes(dossier / "answers.jsonl"):
        effectives[objet["answer_id"]] = (ligne, objet)
    return effectives


def questions_ecartees(dossier: Path, courantes: set[str]) -> tuple[str, ...]:
    """Questions de la source absentes du split courant (ex. q-044 après le Gel b2)."""
    return tuple(
        sorted({o["question_id"] for _, o in reponses_source(dossier).values()} - courantes)
    )


def _ecrire_lignes(chemin: Path, lignes: list[str]) -> None:
    with chemin.open("a", encoding="utf-8", newline="\n") as f:
        for ligne in lignes:
            f.write(ligne + "\n")


def copier_generation(source: Path, cible: Path, courantes: set[str]) -> None:
    """Copie de la source, pour les Questions `courantes` : Réponses effectives (lignes brutes,
    hors `budget_exceeded`), spans des Postes autres que `judging` (ceux sans Question, comme
    l'indexation, compris), `corpus_profile.json` et `applicability.json`."""
    reponses = [
        ligne
        for ligne, o in reponses_source(source).values()
        if o["question_id"] in courantes and o.get("status") != "budget_exceeded"
    ]
    _ecrire_lignes(cible / "answers.jsonl", reponses)
    spans = [
        ligne
        for ligne, s in _lignes(source / "traces.jsonl")
        if s.get("wl.post") != "judging"
        and (not s.get("wl.question_id") or s["wl.question_id"] in courantes)
    ]
    _ecrire_lignes(cible / "traces.jsonl", spans)
    for nom in ("corpus_profile.json", "applicability.json"):
        if (source / nom).is_file():
            shutil.copyfile(source / nom, cible / nom)


def rejuger(
    experience: ResolvedExperiment,
    questions: FrozenQuestions,
    *,
    wl_home: Path,
    source: str,
    run_id: str | None = None,
    providers: Providers | None = None,
    reprendre: str | None = None,
) -> RejugementOutcome:
    """Rejuge l'Exécution `source` avec le Panel de `experience` (Jeu vérifié par
    `load_questions`). Plafond, `completed_with_errors` et `reprendre` (run_id d'un rejugement
    interrompu : seuls les Critères sans verdict sont redemandés) comme `run_experiment`."""
    corpus = declare(Path(experience.corpus))
    experience = resolve_parsers(experience, corpus)
    panels = panels_de(experience)  # Panel inadmissible : refus (code 2) avant tout appel
    src = verifier_source(experience, wl_home, source)
    courantes = {q.id for q in questions.questions}
    ecartees = questions_ecartees(src.dossier, courantes)
    if reprendre is not None:
        verifier_reprise_rejugement(experience, wl_home, source, reprendre, questions.freeze_sha256)
        if deja_terminee(wl_home, reprendre):
            raise ConfigError(
                "reprendre", f"Exécution {reprendre} déjà terminée : rien à reprendre"
            )
        run_id = reprendre
    if run_id is None:
        graine = {"rejudged_from": source, **experience.model_dump(mode="json")}
        run_id = new_run_id(sha16(canonical_json(graine)))
    scenario = Path(experience.scenario) if experience.scenario else None
    with Context.from_experiment(
        experience, wl_home=wl_home, run_id=run_id, providers=providers, execution=True
    ) as ctx:
        if reprendre is None:
            dossier = create_run_dir(
                wl_home,
                run_id,
                experience,
                freeze_sha256=questions.freeze_sha256,
                inputs=empreintes_entrees(experience, wl_home),
                extra={
                    "rejudged_from": source,
                    "source_freeze_sha256": src.manifeste.get("freeze_sha256"),
                    "excluded_questions": list(ecartees),
                },
            )
            copier_generation(src.dossier, dossier, courantes)
        else:
            dossier = wl_home / "runs" / run_id
            reopen_run_dir(dossier, experience.budget, experience.max_error_rate)
        handler: logging.Handler | None = None
        paquet = logging.getLogger("wavelibrarian")
        niveau = paquet.level
        try:
            handler = attach_run_log(dossier)
            if paquet.getEffectiveLevel() > logging.INFO:
                paquet.setLevel(logging.INFO)
            log.info(
                "Rejugement %s de %s : %d Questions, %d écartée(s) hors split %s",
                run_id,
                source,
                len(courantes),
                len(ecartees),
                experience.split,
            )
            runner = _Runner(ctx, dossier, corpus, questions.questions, experience.tier, scenario)
            statut: RunStatus = "completed"
            try:
                runner.juger(experience, panels)
            except BudgetExceeded as erreur:  # arrêt propre ; reprise : --reprendre
                log.warning("Plafond atteint pendant le rejugement : %s", erreur)
                statut = "budget_exceeded"
            runner.compter()
            causes: list[dict[str, Any]] = []
            if statut == "completed":
                causes = causes_execution(
                    runner.par_config,
                    runner.non_jugees_par,
                    experience.max_error_rate,
                    [c.id for c in experience.configurations],
                )
                if causes:
                    statut = "completed_with_errors"
            set_status(
                dossier,
                statut,
                answers=dict(runner.counts),
                unjudged=runner.non_jugees,
                causes=causes,
            )
            log.info("Rejugement %s : %s, Réponses %s", run_id, statut, runner.counts)
        except BaseException:
            log.exception("Rejugement %s en échec", run_id)
            set_status(dossier, "failed")
            raise
        finally:
            paquet.setLevel(niveau)
            if handler is not None:
                detach_run_log(handler)
    issue = RunOutcome(
        run_id=run_id,
        run_dir=dossier,
        status=statut,
        n_answers=runner.n_answers,
        counts=dict(runner.counts),
        unjudged=runner.non_jugees,
        causes=tuple(causes),
    )
    return RejugementOutcome(issue, source, ecartees)
