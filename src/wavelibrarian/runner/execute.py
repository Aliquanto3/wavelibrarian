"""Exécution d'une Expérience (AD-11, contracts.md §2.1 et §5) : le runner de `wl run`.

`cli.py` charge, valide et passe le préflight ; `load_questions` refuse un Jeu non Gelé avant
tout appel ; `run_experiment` enchaîne ensuite, sous `run.lock` et dans un seul `RunContext`
gardé vivant : ingestion, profilage (`corpus_profile.json`), `check()` par Configuration, index
ou cache, puis `answer` par Question. Une erreur sur une Question donne `status: error` et
l'Exécution continue ; `BudgetExceeded` l'arrête avec le manifeste `budget_exceeded`.
"""

import json
import logging
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
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
    Passage,
    Question,
    QuestionInput,
    Usage,
)
from wavelibrarian.corpus.declare import DeclaredCorpus, declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.corpus.profile import profile as profil_corpus
from wavelibrarian.corpus.tiers import tirer, tirer_chemins
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions, verify_frozen
from wavelibrarian.evalset.io import QuestionsFile
from wavelibrarian.llm.gateway import Providers
from wavelibrarian.measure.energy import make_meter
from wavelibrarian.measure.tracing import temps_propre
from wavelibrarian.ports.architecture import Applicability, ArchitectureBase
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
    counts: dict[str, int]

    @property
    def all_failed(self) -> bool:
        """Aucune Réponse `ok` et au moins une en `error` : l'Exécution n'a rien produit."""
        return self.counts.get("ok", 0) == 0 and self.counts.get("error", 0) > 0


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
    """Refus explicite de ce que le runner ne sait pas encore exécuter (Scénario : story 4.7)."""
    if experience.scenario is not None:
        raise ConfigError("scenario", "la phase après mise à jour n'est pas exécutée (story 4.7)")


def verifier_paliers(
    experience: ResolvedExperiment, questions: FrozenQuestions | None = None
) -> None:
    """`ConfigError` (code 2) si `tier` demande des Paliers que le Corpus ne déclare pas, une
    taille absente de `tiers.sizes`, ou (avec `questions`) des Documents requis que le plus petit
    Palier ne peut pas contenir. Sans réseau ni verrou : appelé avant le préflight."""
    if experience.tier is None:
        return
    corpus = declare(Path(experience.corpus))
    tiers = corpus.spec.tiers
    if tiers is None:
        raise ConfigError("tier", "le Corpus ne déclare pas de clé `tiers` dans corpus.yaml")
    if experience.tier != "all" and experience.tier not in tiers.sizes:
        tailles = ", ".join(str(t) for t in tiers.sizes)
        raise ConfigError(
            "tier", f"la taille {experience.tier} n'est pas déclarée dans tiers.sizes ({tailles})"
        )
    if questions is not None:  # tirage à blanc : requis hors Corpus ou plus nombreux que le Palier
        presents = [d.source_path for d in corpus.documents]
        tirer_chemins(presents, tiers, chemins_requis(questions.questions, presents))


def chemins_requis(
    questions: Sequence[Question], presents: Iterable[str] | None = None
) -> tuple[str, ...]:
    """`required_paths` des Paliers : Documents des Ancrages de référence des Questions posées.

    `presents` : Documents du Corpus. Un Ancrage vers un Document absent (créé par le Scénario,
    story 4.7) n'est pas requis : le Palier ne peut pas le contenir."""
    docs = {a.doc for q in questions for a in q.reference_anchors}
    if presents is not None:
        docs &= set(presents)
    return tuple(sorted(docs))


def passages_de_reference(parse: ParsedCorpus, q: Question) -> list[Passage]:
    """Contexte parfait (AD-6) : un Passage `level 0` par Ancrage de référence, dans l'ordre des
    `reference_anchors` (sans doublon), texte de `ParsedCorpus.anchor_text`. Vide pour une
    Question `unanswerable`."""
    if q.type == "unanswerable":
        return []
    passages: dict[str, Passage] = {}
    for ref in q.reference_anchors:
        anchor_id = parse.resolve(ref.doc, ref.page, ref.headings)
        if anchor_id is None:
            raise ConfigError(
                "reference_anchors", f"Ancrage introuvable pour {q.id} : {ref.doc} p.{ref.page}"
            )
        if anchor_id in passages:
            continue
        doc_id = anchor_id.split("#", 1)[0]
        passages[anchor_id] = Passage(
            passage_id=sha16(doc_id, "perfect_context", anchor_id),
            doc_id=doc_id,
            text=parse.anchor_text(anchor_id),
            anchor_ids=(anchor_id,),
        )
    return list(passages.values())


def _question_input(q: Question) -> QuestionInput:
    """L'Architecture ne voit que la Question (AD-6) : jamais la référence."""
    return QuestionInput(question_id=q.id, text=q.text, lang=q.lang, history=q.history)


def _ecrire_json(chemin: Path, donnees: Any) -> None:
    """Écriture atomique (fichier temporaire puis `replace`), comme `manifest.json`."""
    tmp = chemin.with_name(chemin.name + ".tmp")
    texte = json.dumps(donnees, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(texte, encoding="utf-8", newline="\n")
    tmp.replace(chemin)


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
        self.meter = make_meter(ctx.profile.energy)
        self._parses: dict[str, ParsedCorpus] = {}
        self._profils: dict[str, CorpusProfile] = {}
        self._paliers: dict[str, dict[int, ParsedCorpus]] = {}
        self._profils_paliers: dict[tuple[str, int], CorpusProfile] = {}
        self.requis = chemins_requis(questions, (d.source_path for d in corpus.documents))
        self.inapplicables: dict[str, dict[str, Any]] = {}
        self.counts: dict[str, int] = {"ok": 0, "error": 0, "inapplicable": 0}

    @property
    def n_answers(self) -> int:
        return sum(self.counts.values())

    def _ecrire(self, writer: JsonlWriter, answer: Answer) -> None:
        writer.append(answer.model_dump(mode="json"))
        self.counts[answer.status] += 1

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

    def palier(self, parser: str, taille: int) -> tuple[ParsedCorpus, CorpusProfile]:
        """Sous-corpus du Palier `taille` et son Profil. Tirage de `corpus/tiers.py` avec les
        Documents des Ancrages de référence comme `required_paths` (AD-22) ; le Profil est celui
        du sous-corpus, donc `check()` juge le Palier et non le Corpus entier."""
        parse, _ = self.preparer(parser)
        if parser not in self._paliers:
            tiers = self.corpus.spec.tiers
            if tiers is None:  # déjà refusé par verifier_paliers
                raise ConfigError("tier", "le Corpus ne déclare pas de clé `tiers`")
            self._paliers[parser] = tirer(parse, tiers, self.requis)
        sous = self._paliers[parser][taille]
        if (parser, taille) not in self._profils_paliers:
            self._profils_paliers[(parser, taille)] = profil_corpus(
                sous,
                parser=parser,
                tokenizer=self.ctx.tokenizer,
                volatility=self.corpus.spec.volatility,
            )
        return sous, self._profils_paliers[(parser, taille)]

    def ecrire_profil(self, profil: CorpusProfile) -> None:
        _ecrire_json(self.dossier / "corpus_profile.json", profil.model_dump(mode="json"))

    def ecrire_applicabilite(self) -> None:
        _ecrire_json(self.dossier / "applicability.json", self.inapplicables)

    # --- énergie locale et latence (AD-17) -------------------------------------------------

    @contextmanager
    def energie_de_phase(
        self,
        conf: ResolvedConfiguration,
        phase: str,
        apres: Callable[[], None] | None = None,
    ) -> Iterator[None]:
        """Relève l'énergie locale d'une phase (index ou query) d'une Configuration, puis la
        répartit sur les spans locaux de la phase au prorata de leur latence.

        La phase est toujours refermée, même si le mesureur échoue au départ : une phase restée
        ouverte ferait échouer toutes les Configurations suivantes. `apres` n'est appelé que si
        les spans retenus ont été écrits : une Réponse n'est jamais écrite sans ses spans (AD-9).
        Un échec de fermeture pendant une exception en vol est journalisé sans la remplacer
        (un `BudgetExceeded` reste un `BudgetExceeded`).
        """
        tracer = self.ctx.traceur
        tracer.begin_phase()
        kwh: float | None = None
        en_vol = False
        try:
            self.meter.start(f"{conf.id}:{phase}")
            try:
                yield
            except BaseException:
                en_vol = True
                raise
            finally:
                try:
                    kwh = self.meter.stop()
                except Exception as exc:
                    if not en_vol:
                        raise
                    log.error("mesure d'énergie %s:%s non relevée : %s", conf.id, phase, exc)
        except BaseException:
            en_vol = True
            raise
        finally:
            try:
                tracer.end_phase(kwh, getattr(self.meter, "method", "estimated"))
                if apres is not None:
                    apres()
            except Exception as exc:
                if not en_vol:
                    raise
                log.error("fin de phase %s:%s en échec : %s", conf.id, phase, exc)

    def poser(
        self,
        conf: ResolvedConfiguration,
        q: Question,
        arch: ArchitectureBase,
        methode: Any,
        passages: Callable[[Question], Sequence[Passage]] | None = None,
    ) -> Answer:
        """Pose une Question dans le Poste `query`. Le span `answer` est émis ici, jamais par
        l'Architecture ; sa latence est le temps propre de `answer`, hors spans déjà tracés
        (appels, embeddings). `Answer.latency_s` = somme des spans `query` de la Question.
        `passages` : Condition contexte parfait, `answer_with_context` au lieu de `answer`."""
        tracer = self.ctx.traceur
        reponse: ArchAnswer | None = None
        erreur: Exception | None = None
        with self.ctx.scope(post="query", question_id=q.id):
            debut = time.perf_counter()
            externe, ecoule = tracer.latency_total, tracer.elapsed_total
            try:
                if passages is None:
                    reponse = arch.answer(_question_input(q))
                else:
                    reponse = arch.answer_with_context(_question_input(q), passages(q))
            except BudgetExceeded:
                raise
            except Exception as exc:  # AD-11 : la Question suivante est posée
                erreur = exc
            externe = tracer.latency_total - externe
            propre = temps_propre(time.perf_counter() - debut, tracer.elapsed_total - ecoule)
            tracer.record(
                "answer",
                "local",
                model_id=None,
                provider=None,
                usage=Usage(),
                cost=Decimal(0),
                cost_uncached=Decimal(0),
                currency="",
                latency_s=propre,
                from_cache=False,
                status="ok" if erreur is None else "error",
                extra={"wl.invalid_citations": reponse.invalid_citations if reponse else 0},
            )
        latence = externe + propre
        if reponse is not None:
            return self._answer(conf, q, reponse, "ok", latency_s=latence)
        log.warning("Question %s (%s) en erreur : %s", q.id, conf.id, erreur)
        vide = ArchAnswer(text="", abstained=False, retrieval_method=methode)
        message = f"{type(erreur).__name__} : {erreur}"
        return self._answer(conf, q, vide, "error", message, latency_s=latence)

    # --- Réponses --------------------------------------------------------------------------

    def _answer(
        self,
        conf: ResolvedConfiguration,
        q: Question,
        arch_answer: ArchAnswer,
        status: Literal["ok", "error", "inapplicable"],
        error: str | None = None,
        *,
        latency_s: float = 0.0,
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
                "latency_s": latency_s,
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
            self._ecrire(writer, self._answer(conf, q, vide, status, message))

    def configuration(
        self, writer: JsonlWriter, conf: ResolvedConfiguration, experience: ResolvedExperiment
    ) -> None:
        """Une Configuration : chaque Condition, puis chaque Palier (`tier: all`) ou le Palier
        demandé, avec sa propre ligne d'`answers.jsonl` et son propre index."""
        ctx = self.ctx
        ctx.config_id = conf.id
        ctx.parser = conf.parser.name
        parse, profil = self.preparer(conf.parser.name)
        if experience.tier is None:
            tailles: list[int | None] = [None]
        elif experience.tier == "all":
            tiers = self.corpus.spec.tiers
            tailles = list(tiers.sizes) if tiers is not None else []
        else:
            tailles = [experience.tier]
        try:
            for condition in experience.conditions:
                for taille in tailles:
                    ctx.condition, ctx.tier = condition, taille
                    sous, profil_t = (
                        (parse, profil) if taille is None else self.palier(conf.parser.name, taille)
                    )
                    self._cellule(writer, conf, condition, taille, parse, sous, profil_t)
        finally:
            ctx.condition, ctx.tier = "standard", None

    def _cellule(
        self,
        writer: JsonlWriter,
        conf: ResolvedConfiguration,
        condition: str,
        taille: int | None,
        parse: ParsedCorpus,
        sous: ParsedCorpus,
        profil: CorpusProfile,
    ) -> None:
        """Une (Configuration, Condition, Palier). En contexte parfait, l'Architecture ne reçoit
        que les Passages de référence : ni `check()` (le Corpus n'entre pas dans le prompt), ni
        index."""
        ctx = self.ctx
        parfait = condition == "perfect_context"
        spec = ComponentSpec(name=conf.architecture, params=conf.params)

        def fabrique() -> ArchitectureBase:
            return ctx.build("architecture", spec)

        cle_applicabilite = conf.id if taille is None else f"{conf.id}@{taille}"
        try:
            arch = fabrique()
            verdict = Applicability(applicable=True)
            if not parfait:
                log.info("étape check : %s", cle_applicabilite)
                verdict = arch.check(profil)
        except BudgetExceeded:
            raise
        except Exception as erreur:  # Configuration en échec : ses Questions en `error`
            log.exception("Configuration %s : construction ou check en échec", conf.id)
            self._vides(writer, conf, "none", "error", f"{type(erreur).__name__} : {erreur}")
            return
        methode = "provided" if parfait else arch.capabilities.retrieval_method
        if not verdict.applicable:
            raison = verdict.reason or "inapplicable"
            log.info("Configuration %s inapplicable : %s", cle_applicabilite, raison)
            self.inapplicables[cle_applicabilite] = {
                "architecture": conf.architecture,
                "applicable": False,
                "reason": raison,
                **({} if taille is None else {"tier": taille}),
            }
            self._vides(writer, conf, methode, "inapplicable", raison)
            return
        cle = "-"
        if not parfait:
            try:
                log.info("étape index : %s", cle_applicabilite)
                with self.energie_de_phase(conf, "index"):
                    arch, cle = self.index_cache.build(ctx, fabrique, sous)
            except BudgetExceeded:
                raise
            except Exception as erreur:
                log.exception("Configuration %s : index en échec", conf.id)
                self._vides(writer, conf, methode, "error", f"{type(erreur).__name__} : {erreur}")
                return
        log.info(
            "étape answer : %s (%s, palier %s, index %s, %d Questions)",
            conf.id,
            condition,
            "all" if taille is None else taille,
            cle,
            len(self.questions),
        )
        # Réponses écrites après leurs spans retenus : un arrêt dur pendant la phase perd les
        # deux à la fois, et la reprise (AD-11) repose ces Questions depuis les caches.
        reponses: list[Answer] = []

        def ecrire_reponses() -> None:
            for answer in reponses:
                self._ecrire(writer, answer)

        def passages(q: Question) -> Sequence[Passage]:
            return passages_de_reference(parse, q)

        with self.energie_de_phase(conf, "query", apres=ecrire_reponses):
            for q in self.questions:
                reponses.append(self.poser(conf, q, arch, methode, passages if parfait else None))


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
    verifier_paliers(experience, questions)
    corpus = declare(Path(experience.corpus))
    experience = resolve_parsers(experience, corpus)
    if run_id is None:
        run_id = new_run_id(sha16(canonical_json(experience.model_dump(mode="json"))))
    with Context.from_experiment(
        experience, wl_home=wl_home, run_id=run_id, providers=providers, execution=True
    ) as ctx:
        dossier = create_run_dir(wl_home, run_id, experience, freeze_sha256=questions.freeze_sha256)
        handler: logging.Handler | None = None
        paquet = logging.getLogger("wavelibrarian")
        niveau = paquet.level
        try:
            handler = attach_run_log(dossier)
            if paquet.getEffectiveLevel() > logging.INFO:  # étapes du runner dans run.log
                paquet.setLevel(logging.INFO)
            log.info("Exécution %s : %d Questions posées", run_id, len(questions.questions))
            runner = _Runner(ctx, dossier, corpus, questions.questions)
            _, profil = runner.preparer(experience.configurations[0].parser.name)
            runner.ecrire_profil(profil)
            statut: RunStatus = "completed"
            try:
                with JsonlWriter(dossier, "answers.jsonl") as writer:
                    for conf in experience.configurations:
                        runner.configuration(writer, conf, experience)
            except BudgetExceeded as erreur:  # arrêt propre ; reprise : story 4.8
                log.warning("Plafond atteint : %s", erreur)
                statut = "budget_exceeded"
            finally:
                runner.ecrire_applicabilite()
            set_status(dossier, statut, answers=dict(runner.counts))
            log.info("Exécution %s : %s, Réponses %s", run_id, statut, runner.counts)
        except BaseException:
            log.exception("Exécution %s en échec", run_id)
            set_status(dossier, "failed")
            raise
        finally:
            paquet.setLevel(niveau)
            if handler is not None:
                detach_run_log(handler)
    return RunOutcome(
        run_id=run_id,
        run_dir=dossier,
        status=statut,
        n_answers=runner.n_answers,
        counts=dict(runner.counts),
    )
