"""Exécution d'une Expérience (AD-11, contracts.md §2.1 et §5) : le runner de `wl run`.

`cli.py` charge, valide et passe le préflight ; `load_questions` refuse un Jeu non Gelé avant
tout appel ; `run_experiment` enchaîne ensuite, sous `run.lock` et dans un seul `RunContext`
gardé vivant : ingestion, profilage (`corpus_profile.json`), `check()` par Configuration, index
ou cache, puis `answer` par Question. Une erreur sur une Question donne `status: error` et
l'Exécution continue ; `BudgetExceeded` l'arrête avec le manifeste `budget_exceeded`.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from wavelibrarian.config.experiment import ResolvedConfiguration, ResolvedExperiment
from wavelibrarian.core.errors import BudgetExceeded, ConfigError
from wavelibrarian.core.ids import answer_id, canonical_json, new_run_id, sha16
from wavelibrarian.core.types import (
    Answer,
    ArchAnswer,
    CorpusProfile,
    ParsedCorpus,
    Question,
    QuestionInput,
)
from wavelibrarian.corpus.declare import DeclaredCorpus, declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.corpus.profile import profile as profil_corpus
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions, verify_frozen
from wavelibrarian.evalset.io import QuestionsFile
from wavelibrarian.llm.gateway import Providers
from wavelibrarian.ports.architecture import ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.index_cache import IndexCache
from wavelibrarian.runner.rundir import (
    JsonlWriter,
    attach_run_log,
    create_run_dir,
    detach_run_log,
    resolve_parsers,
    set_status,
)

log = logging.getLogger(__name__)

RunStatus = Literal["completed", "budget_exceeded"]


@dataclass(frozen=True)
class FrozenQuestions:
    """Jeu Gelé vérifié et Questions posées (partie demandée, `max_questions` appliqué)."""

    freeze_sha256: str
    questions: tuple[Question, ...]


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    run_dir: Path
    status: RunStatus
    n_answers: int


def load_questions(experience: ResolvedExperiment) -> FrozenQuestions:
    """Charge le Jeu, `verify_frozen` puis `select_questions` (AD-15) ; `ConfigError` (code 2)
    sur un Jeu non Gelé ou modifié après le Gel. Les Questions sont triées par `id`, puis
    limitées aux `max_questions` premières."""
    doc: QuestionsFile = io.load(Path(experience.questions))
    verify_frozen(doc)
    assert doc.freeze is not None  # garanti par verify_frozen
    choisies = sorted(select_questions(doc, experience.split), key=lambda q: q.id)
    if experience.max_questions is not None:
        choisies = choisies[: experience.max_questions]
    return FrozenQuestions(freeze_sha256=doc.freeze.sha256, questions=tuple(choisies))


def _hors_perimetre(experience: ResolvedExperiment) -> None:
    """Refus explicite de ce que le runner ne sait pas encore exécuter, plutôt qu'un résultat
    faux (contexte parfait et Paliers : story 4.6 ; Scénario : story 4.7)."""
    if experience.conditions != ("standard",):
        raise ConfigError("conditions", "seule la Condition `standard` est exécutée (story 4.6)")
    if experience.tier is not None:
        raise ConfigError("tier", "les Paliers de volume ne sont pas encore exécutés (story 4.6)")
    if experience.scenario is not None:
        raise ConfigError("scenario", "la phase après mise à jour n'est pas exécutée (story 4.7)")


def _question_input(q: Question) -> QuestionInput:
    """L'Architecture ne voit que la Question (AD-6) : jamais la référence."""
    return QuestionInput(question_id=q.id, text=q.text, lang=q.lang, history=q.history)


class _Runner:
    def __init__(
        self,
        ctx: Context,
        dossier: Path,
        corpus: DeclaredCorpus,
        questions: tuple[Question, ...],
    ) -> None:
        self.ctx = ctx
        self.dossier = dossier
        self.corpus = corpus
        self.questions = questions
        self.index_cache = IndexCache(ctx.wl_home)
        self._parses: dict[str, ParsedCorpus] = {}
        self._profils: dict[str, CorpusProfile] = {}
        self.inapplicables: dict[str, dict[str, Any]] = {}
        self.n_answers = 0

    # --- ingestion et profilage ------------------------------------------------------------

    def preparer(self, parser: str) -> tuple[ParsedCorpus, CorpusProfile]:
        """Ingestion et Profil du Corpus pour un parser résolu (une fois par parser)."""
        if parser not in self._parses:
            log.info("étape ingestion : parser %s", parser)
            parse = ingest(self.corpus, parser, wl_home=self.ctx.wl_home)
            log.info("étape profilage : %d Documents", len(parse.documents))
            self._parses[parser] = parse
            self._profils[parser] = profil_corpus(
                parse,
                parser=parser,
                tokenizer=self.ctx.tokenizer,
                volatility=self.corpus.spec.volatility,
            )
        return self._parses[parser], self._profils[parser]

    def ecrire_profil(self, profil: CorpusProfile) -> None:
        (self.dossier / "corpus_profile.json").write_text(
            json.dumps(profil.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def ecrire_applicabilite(self) -> None:
        (self.dossier / "applicability.json").write_text(
            json.dumps(self.inapplicables, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # --- Réponses --------------------------------------------------------------------------

    def _answer(
        self,
        conf: ResolvedConfiguration,
        q: Question,
        arch_answer: ArchAnswer,
        status: Literal["ok", "error", "inapplicable"],
        error: str | None = None,
    ) -> Answer:
        ctx = self.ctx
        return Answer.model_validate(
            {
                **arch_answer.model_dump(),
                "answer_id": answer_id(
                    ctx.run_id, conf.id, ctx.condition, ctx.tier, ctx.phase, q.id
                ),
                "question_id": q.id,
                "config_id": conf.id,
                "condition": ctx.condition,
                "tier": ctx.tier,
                "phase": ctx.phase,
                "status": status,
                "error": error,
            }
        )

    def _vides(
        self,
        writer: JsonlWriter,
        conf: ResolvedConfiguration,
        methode: Any,
        status: Literal["error", "inapplicable"],
        message: str,
    ) -> None:
        vide = ArchAnswer(text="", abstained=False, retrieval_method=methode)
        for q in self.questions:
            writer.append(self._answer(conf, q, vide, status, message).model_dump(mode="json"))
            self.n_answers += 1

    def configuration(self, writer: JsonlWriter, conf: ResolvedConfiguration) -> None:
        ctx = self.ctx
        ctx.config_id = conf.id
        ctx.parser = conf.parser.name
        parse, profil = self.preparer(conf.parser.name)
        spec = ComponentSpec(name=conf.architecture, params=conf.params)

        def fabrique() -> ArchitectureBase:
            return ctx.build("architecture", spec)

        try:
            arch = fabrique()
            log.info("étape check : %s", conf.id)
            verdict = arch.check(profil)
        except BudgetExceeded:
            raise
        except Exception as erreur:  # Configuration en échec : ses Questions en `error`
            log.exception("Configuration %s : construction ou check en échec", conf.id)
            self._vides(writer, conf, "none", "error", f"{type(erreur).__name__} : {erreur}")
            return
        methode = arch.capabilities.retrieval_method
        if not verdict.applicable:
            raison = verdict.reason or "inapplicable"
            log.info("Configuration %s inapplicable : %s", conf.id, raison)
            self.inapplicables[conf.id] = {
                "architecture": conf.architecture,
                "applicable": False,
                "reason": raison,
            }
            self._vides(writer, conf, methode, "inapplicable", raison)
            return
        try:
            log.info("étape index : %s", conf.id)
            arch, cle = self.index_cache.build(ctx, fabrique, parse)
        except BudgetExceeded:
            raise
        except Exception as erreur:
            log.exception("Configuration %s : index en échec", conf.id)
            self._vides(writer, conf, methode, "error", f"{type(erreur).__name__} : {erreur}")
            return
        log.info("étape answer : %s (index %s, %d Questions)", conf.id, cle, len(self.questions))
        for q in self.questions:
            try:
                with ctx.scope(post="query", question_id=q.id):
                    reponse = arch.answer(_question_input(q))
                answer = self._answer(conf, q, reponse, "ok")
            except BudgetExceeded:
                raise
            except Exception as erreur:  # AD-11 : la Question suivante est posée
                log.warning("Question %s (%s) en erreur : %s", q.id, conf.id, erreur)
                vide = ArchAnswer(text="", abstained=False, retrieval_method=methode)
                answer = self._answer(conf, q, vide, "error", f"{type(erreur).__name__} : {erreur}")
            writer.append(answer.model_dump(mode="json"))
            self.n_answers += 1


def run_experiment(
    experience: ResolvedExperiment,
    questions: FrozenQuestions,
    *,
    wl_home: Path,
    run_id: str | None = None,
    providers: Providers | None = None,
) -> RunOutcome:
    """Exécute une Expérience validée dont le Jeu est vérifié (`load_questions`).

    `run.lock` est pris (et les réservations orphelines récupérées) avant d'écrire quoi que ce
    soit ; un second `wl run` échoue donc sans créer de dossier. `providers` : Faux LLM
    scénarisé des tests ; sinon les adaptateurs du Catalogue (`build_providers`, `fake` compris).
    """
    _hors_perimetre(experience)
    corpus = declare(Path(experience.corpus))
    experience = resolve_parsers(experience, corpus)
    if run_id is None:
        run_id = new_run_id(sha16(canonical_json(experience.model_dump(mode="json"))))
    with Context.from_experiment(
        experience, wl_home=wl_home, run_id=run_id, providers=providers, execution=True
    ) as ctx:
        dossier = create_run_dir(wl_home, run_id, experience, freeze_sha256=questions.freeze_sha256)
        handler = attach_run_log(dossier)
        paquet = logging.getLogger("wavelibrarian")
        niveau = paquet.level
        if paquet.getEffectiveLevel() > logging.INFO:  # les étapes du runner vont dans run.log
            paquet.setLevel(logging.INFO)
        try:
            log.info("Exécution %s : %d Questions posées", run_id, len(questions.questions))
            runner = _Runner(ctx, dossier, corpus, questions.questions)
            _, profil = runner.preparer(experience.configurations[0].parser.name)
            runner.ecrire_profil(profil)
            statut: RunStatus = "completed"
            try:
                with JsonlWriter(dossier, "answers.jsonl") as writer:
                    for conf in experience.configurations:
                        runner.configuration(writer, conf)
            except BudgetExceeded as erreur:  # arrêt propre ; reprise : story 4.8
                log.warning("Plafond atteint : %s", erreur)
                statut = "budget_exceeded"
            finally:
                runner.ecrire_applicabilite()
            set_status(dossier, statut)
            log.info("Exécution %s : %s, %d Réponses", run_id, statut, runner.n_answers)
        except BaseException:
            log.exception("Exécution %s en échec", run_id)
            set_status(dossier, "failed")
            raise
        finally:
            paquet.setLevel(niveau)
            detach_run_log(handler)
    return RunOutcome(run_id=run_id, run_dir=dossier, status=statut, n_answers=runner.n_answers)
