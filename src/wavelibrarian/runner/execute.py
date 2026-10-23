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

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import charger_yaml
from wavelibrarian.config.experiment import ResolvedConfiguration, ResolvedExperiment
from wavelibrarian.config.panel import excluded_judges, form_panel
from wavelibrarian.config.schemas import valider
from wavelibrarian.core.bilan import causes_execution
from wavelibrarian.core.errors import BudgetExceeded, ConfigError
from wavelibrarian.core.ids import answer_id, canonical_json, new_run_id, sha16
from wavelibrarian.core.types import (
    Answer,
    ArchAnswer,
    CorpusProfile,
    ParsedCorpus,
    Passage,
    Phase,
    Question,
    QuestionInput,
    Usage,
)
from wavelibrarian.corpus.declare import DeclaredCorpus, TiersSpec, declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.corpus.profile import profile as profil_corpus
from wavelibrarian.corpus.scenario import Scenario, appliquer_fichier, charger
from wavelibrarian.corpus.tiers import tirer, tirer_chemins
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions, verify_frozen
from wavelibrarian.evalset.io import QuestionsFile
from wavelibrarian.llm.gateway import Providers
from wavelibrarian.measure.energy import make_meter
from wavelibrarian.measure.tracing import temps_propre
from wavelibrarian.ports.architecture import Applicability, ArchitectureBase, CorpusChange
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.index_cache import IndexCache, index_key
from wavelibrarian.runner.resume import (
    cles_tracees,
    deja_terminee,
    empreintes_entrees,
    verifier_reprise,
)
from wavelibrarian.runner.rundir import (
    JsonlWriter,
    attach_run_log,
    create_run_dir,
    detach_run_log,
    read_answers,
    read_panel,
    read_verdicts,
    reopen_run_dir,
    resolve_parsers,
    set_status,
)
from wavelibrarian.scoring.panel import construire_juges, criteres_juges, juger_reponse

log = logging.getLogger(__name__)

RunStatus = Literal["completed", "completed_with_errors", "budget_exceeded"]


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
    unjudged: int = 0  # Critères jugés sans verdict de panel (appel d'un Juge en échec)
    # `completed_with_errors` : `{config_id, cause, count}` par Configuration (`core/bilan.py`)
    causes: tuple[dict[str, Any], ...] = ()

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


def cibles_du_scenario(scenario: str | Path | None, presents: Iterable[str]) -> tuple[str, ...]:
    """Documents du Corpus de base que le Scénario modifie ou supprime. Avec des Paliers, ils
    sont requis dans chaque Palier (`required_paths`) : le Scénario s'applique alors au
    sous-corpus du Palier, et ses ajouts y entrent. Schéma invalide : `ConfigError` (code 2)."""
    if scenario is None:
        return ()
    chemin = Path(scenario)
    operations = valider(Scenario, charger_yaml(chemin), str(chemin)).operations
    return tuple(sorted({op.target for op in operations if op.op != "add"} & set(presents)))


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
        requis = chemins_requis(questions.questions, presents)
        requis = tuple(sorted({*requis, *cibles_du_scenario(experience.scenario, presents)}))
        tirer_chemins(presents, tiers, requis, _tailles_demandees(experience.tier, tiers))


def _tailles_demandees(tier: int | Literal["all"], tiers: TiersSpec) -> tuple[int, ...]:
    """Paliers exécutés : tous ceux de `tiers.sizes` pour `all`, sinon le seul demandé. Le
    tirage est emboîté et un Palier ne dépend pas des autres tailles : `tier: 20` seul n'exige
    pas que les Documents requis tiennent dans le Palier de 5."""
    return tuple(tiers.sizes) if tier == "all" else (tier,)


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


def panels_de(experience: ResolvedExperiment) -> dict[str, tuple[str, ...]]:
    """Panel admissible de chaque Configuration (AD-14) : les `panel_size` premiers Juges du
    réservoir d'une autre Famille que les `answer_producers`, hors exclus de la calibration
    (`judges.excluded_from`) ; ces Juges exclus ne sont jamais appelés. `ConfigError` (code 2)
    si moins de deux restent."""
    j = experience.judges
    catalogue = load_catalog(Path(experience.catalog) if experience.catalog else None)
    exclus = excluded_judges(Path(j.excluded_from)) if j.excluded_from else frozenset[str]()
    return {
        c.id: form_panel(j.pool or (), j.panel_size or 0, c.answer_producers, catalogue, exclus)
        for c in experience.configurations
    }


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
        tier: int | Literal["all"] | None = None,
        scenario: Path | None = None,
    ) -> None:
        self.ctx = ctx
        self.scenario = scenario
        self._apres: dict[
            tuple[str, int | None], tuple[CorpusChange, ParsedCorpus, CorpusProfile]
        ] = {}
        self.tier: int | Literal["all"] | None = tier
        self.dossier = dossier
        self.corpus = corpus
        self.questions = questions
        self.index_cache = IndexCache(ctx.wl_home)
        self.meter = make_meter(ctx.profile.energy)
        self._parses: dict[str, ParsedCorpus] = {}
        self._profils: dict[str, CorpusProfile] = {}
        self._paliers: dict[str, dict[int, ParsedCorpus]] = {}
        self._profils_paliers: dict[tuple[str, int], CorpusProfile] = {}
        presents = [d.source_path for d in corpus.documents]
        requis = {*chemins_requis(questions, presents), *cibles_du_scenario(scenario, presents)}
        self.requis = tuple(sorted(requis))
        self.inapplicables: dict[str, dict[str, Any]] = {}
        self.counts: dict[str, int] = {"ok": 0, "error": 0, "inapplicable": 0}
        self.par_config: dict[str, dict[str, int]] = {}
        # Reprise : `faits` = answer_id déjà traités (jamais refaits), `en_attente` = answer_id dont
        # la dernière ligne est `budget_exceeded` ou `error` (reposés, story 8.3 ; une clé
        # `budget_exceeded` n'est pas réécrite si le plafond rebloque).
        self.faits: set[str] = set()
        self.en_attente: set[str] = set()
        self.non_jugees_par: dict[
            str, int
        ] = {}  # Critères sans verdict de panel, par Configuration

    @property
    def n_answers(self) -> int:
        return sum(self.counts.values())

    @property
    def non_jugees(self) -> int:
        return sum(self.non_jugees_par.values())

    def compter(self) -> None:
        """Décompte des Réponses effectives (dernière ligne par clé) de `answers.jsonl`, pour le
        manifeste ; `budget_exceeded` n'y figure que s'il en reste."""
        self.counts = {"ok": 0, "error": 0, "inapplicable": 0}
        self.par_config = {}
        for a in read_answers(self.dossier).values():
            self.counts[a.status] = self.counts.get(a.status, 0) + 1
            compte = self.par_config.setdefault(a.config_id, {})
            compte[a.status] = compte.get(a.status, 0) + 1

    def reprendre(self) -> None:
        """Reprise (AD-11) : relit `answers.jsonl` (clés présentes sautées, sauf `budget_exceeded`
        et `error`, reposées : story 8.3),
        `applicability.json`, et repère les Questions interrompues, c'est-à-dire déjà tracées au
        Poste `query` sans Réponse : leurs appels refaits sortent du cache et sont marqués
        `wl.resumed` (ni appel ni latence en double dans le Rapport)."""
        existantes = read_answers(self.dossier)
        self.faits = {
            i for i, a in existantes.items() if a.status not in ("budget_exceeded", "error")
        }
        self.en_attente = set(existantes) - self.faits
        faites = {
            (a.config_id, a.condition, a.tier, a.phase, a.question_id)
            for i, a in existantes.items()
            if i in self.faits
        }
        self.ctx.traceur.reprises = frozenset(cles_tracees(self.dossier) - faites)
        chemin = self.dossier / "applicability.json"
        if chemin.is_file():
            self.inapplicables = json.loads(chemin.read_text(encoding="utf-8"))

    def _ecrire(self, writer: JsonlWriter, answer: Answer) -> None:
        if answer.answer_id in self.faits:  # reprise : une clé présente n'est jamais réécrite
            return
        writer.append(answer.model_dump(mode="json"))
        if answer.status != "budget_exceeded":
            self.faits.add(answer.answer_id)

    def _tailles(self, experience: ResolvedExperiment) -> list[int | None]:
        tiers = self.corpus.spec.tiers
        if experience.tier is None or tiers is None:
            return [None]
        return list(_tailles_demandees(experience.tier, tiers))

    def marquer_budget_exceeded(self, writer: JsonlWriter, experience: ResolvedExperiment) -> None:
        """Plafond atteint : chaque clé de la grille (Configuration, Condition, Palier, phase,
        Question) sans Réponse devient un `Answer` `budget_exceeded`, la Question interrompue
        comprise. Les Réponses déjà écrites restent telles quelles."""
        ctx = self.ctx
        vide = ArchAnswer(text="", abstained=False, retrieval_method="none")
        message = "plafond de dépense atteint avant que la Question soit posée"
        phases: list[Phase] = ["base", "after_update"] if experience.scenario else ["base"]
        try:
            for conf in experience.configurations:
                for phase in phases:
                    ctx.phase = phase
                    for condition in experience.conditions:
                        for taille in self._tailles(experience):
                            ctx.condition, ctx.tier = condition, taille
                            for q in self.questions:
                                a = self._answer(conf, q, vide, "budget_exceeded", message)
                                if a.answer_id not in self.faits | self.en_attente:
                                    self._ecrire(writer, a)
        finally:
            ctx.condition, ctx.tier, ctx.phase = "standard", None, "base"

    # --- jugement (story 4.9) --------------------------------------------------------------

    def _corpus_de_phase(self, conf: ResolvedConfiguration, phase: Phase) -> ParsedCorpus | None:
        """Corpus dont les Ancrages servent à noter une Réponse de la phase (après mise à jour :
        le Corpus du Scénario). `None` si le Scénario ne s'applique plus : les Réponses de la
        phase restent non jugées (jamais notées sur le Corpus de base), comptées et journalisées."""
        parser = conf.parser.name
        if phase == "after_update":
            try:
                return self.apres_mise_a_jour(parser)[1]
            except BudgetExceeded:
                raise
            except Exception as erreur:
                log.warning("Corpus après mise à jour indisponible pour le jugement : %s", erreur)
                return None
        return self.preparer(parser)[0]

    def juger(self, experience: ResolvedExperiment, panels: dict[str, tuple[str, ...]]) -> None:
        """Note chaque Réponse `ok` au Poste `judging` : Critères automatiques, puis Panel
        (`scoring/panel.py`). `error`, `inapplicable` et `budget_exceeded` n'ont ni verdict ni
        appel de Juge. Reprise : `verdicts.jsonl` et `panel.jsonl` sont relus, seules les clés
        absentes sont redemandées. `BudgetExceeded` remonte (verdicts déjà écrits conservés)."""
        ctx = self.ctx
        configs = {c.id: c for c in experience.configurations}
        questions = {q.id: q for q in self.questions}
        par_reponse: dict[str, dict[Any, Any]] = {}
        for cle, v in read_verdicts(self.dossier).items():
            par_reponse.setdefault(cle[0], {})[cle] = v
        deja_panel = set(read_panel(self.dossier))
        juges: dict[tuple[str, ...], Any] = {}
        corpus_de: dict[tuple[str, str], tuple[ParsedCorpus, set[str]] | None] = {}
        self.non_jugees_par = {}
        reponses = read_answers(self.dossier)
        log.info("étape jugement : %d Réponses", len(reponses))
        try:
            with (
                JsonlWriter(self.dossier, "verdicts.jsonl") as verdicts,
                JsonlWriter(self.dossier, "panel.jsonl") as panel,
            ):
                for a in reponses.values():
                    conf, q = configs.get(a.config_id), questions.get(a.question_id)
                    if a.status != "ok" or conf is None or q is None:
                        continue
                    if (conf.id, a.phase) not in corpus_de:
                        parse = self._corpus_de_phase(conf, a.phase)
                        corpus_de[(conf.id, a.phase)] = (
                            None
                            if parse is None
                            else (parse, {i for d in parse.documents for i in d.anchors})
                        )
                    corpus_phase = corpus_de[(conf.id, a.phase)]
                    if corpus_phase is None:
                        self._non_juges(conf.id, len(criteres_juges(q)))
                        continue
                    parse, tout = corpus_phase
                    ancres = [
                        i
                        for r in q.reference_anchors
                        if (i := parse.resolve(r.doc, r.page, r.headings)) is not None
                    ]
                    membres = panels[conf.id]
                    if membres not in juges:
                        juges[membres] = construire_juges(ctx, membres)
                    ctx.config_id, ctx.condition, ctx.tier, ctx.phase = (
                        a.config_id,
                        a.condition,
                        a.tier,
                        a.phase,
                    )
                    with ctx.scope(post="judging", question_id=q.id):
                        n = juger_reponse(
                            a,
                            q,
                            reference_texts=[parse.anchor_text(i) for i in ancres],
                            reference_anchor_ids=ancres,
                            corpus_anchor_ids=tout,
                            juges=juges[membres],
                            passes=experience.judges.passes,
                            deja=par_reponse.get(a.answer_id, {}),
                            deja_panel=deja_panel,
                            verdicts=verdicts,
                            panel=panel,
                        )
                        self._non_juges(conf.id, n)
        finally:
            ctx.condition, ctx.tier, ctx.phase = "standard", None, "base"

    def _non_juges(self, config_id: str, n: int) -> None:
        if n:
            self.non_jugees_par[config_id] = self.non_jugees_par.get(config_id, 0) + n

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
            demande = self.tier if self.tier is not None else taille
            tailles = _tailles_demandees(demande, tiers)
            self._paliers[parser] = tirer(parse, tiers, self.requis, tailles)
        sous = self._paliers[parser][taille]
        if (parser, taille) not in self._profils_paliers:
            self._profils_paliers[(parser, taille)] = profil_corpus(
                sous,
                parser=parser,
                tokenizer=self.ctx.tokenizer,
                volatility=self.corpus.spec.volatility,
            )
        return sous, self._profils_paliers[(parser, taille)]

    def apres_mise_a_jour(
        self, parser: str, taille: int | None = None
    ) -> tuple[CorpusChange, ParsedCorpus, CorpusProfile]:
        """Scénario appliqué au Corpus de base (story 2.6), ou au sous-corpus du Palier `taille`
        (tiré sur le Corpus de base, les Documents visés par le Scénario y sont requis ; les
        ajouts du Scénario y entrent) : changement net, Corpus après mise à jour et son Profil,
        une fois par (parser, Palier). `lang` et `parser` sont ceux du `corpus.yaml` et de la
        Configuration, comme à l'ingestion directe. `ConfigError` si le Scénario ne s'applique
        pas."""
        if (parser, taille) not in self._apres:
            if self.scenario is None:
                raise ConfigError("scenario", "aucun Scénario déclaré")
            parse = self.preparer(parser)[0] if taille is None else self.palier(parser, taille)[0]
            palier = "all" if taille is None else taille
            log.info(
                "étape scénario : %s (parser %s, palier %s)", self.scenario.name, parser, palier
            )
            change, apres = appliquer_fichier(
                parse, self.scenario, lang=self.corpus.spec.lang, parser=parser
            )
            profil = profil_corpus(
                apres,
                parser=parser,
                tokenizer=self.ctx.tokenizer,
                volatility=self.corpus.spec.volatility,
            )
            self._apres[(parser, taille)] = (change, apres, profil)
        return self._apres[(parser, taille)]

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
                tracer.end_phase(
                    kwh,
                    getattr(self.meter, "method", "estimated"),
                    getattr(self.meter, "source", "unknown"),
                )
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
        passages: Sequence[Passage] | None = None,
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
                    reponse = arch.answer_with_context(_question_input(q), passages)
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
        status: Literal["ok", "error", "inapplicable", "budget_exceeded"],
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
        questions: Sequence[Question] | None = None,
    ) -> None:
        vide = ArchAnswer(text="", abstained=False, retrieval_method=methode)
        for q in self.questions if questions is None else questions:
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
        tailles = self._tailles(experience)
        try:
            for condition in experience.conditions:
                for taille in tailles:
                    ctx.condition, ctx.tier = condition, taille
                    if taille is None:
                        sous, profil_t = parse, profil
                    else:
                        try:
                            sous, profil_t = self.palier(conf.parser.name, taille)
                        except BudgetExceeded:
                            raise
                        except Exception as erreur:  # tirage en échec : la cellule en `error`
                            log.exception("Palier %s de %s en échec", taille, conf.id)
                            message = f"{type(erreur).__name__} : {erreur}"
                            self._vides(writer, conf, "none", "error", message)
                            continue
                    self._cellule(writer, conf, condition, taille, parse, sous, profil_t)
            if experience.scenario is not None:
                self._phase_apres_mise_a_jour(writer, conf, experience, tailles)
        finally:
            ctx.condition, ctx.tier, ctx.phase = "standard", None, "base"

    def _phase_apres_mise_a_jour(
        self,
        writer: JsonlWriter,
        conf: ResolvedConfiguration,
        experience: ResolvedExperiment,
        tailles: Sequence[int | None],
    ) -> None:
        """Phase `after_update` d'une Configuration (contracts.md §2.1, étape 5) : Scénario
        appliqué, `update` vers la clé du Corpus après mise à jour, instance neuve + `load`, puis
        toutes les Questions posées reposées (la Fraîcheur lit celles à `scenario_target`, les
        autres mesurent la régression), par Condition et par Palier de la phase `base`."""
        ctx = self.ctx
        parser = conf.parser.name
        ctx.phase = "after_update"
        for condition in experience.conditions:
            for taille in tailles:
                ctx.condition, ctx.tier = condition, taille
                try:
                    if taille is None:
                        base = self.preparer(parser)[0]
                    else:
                        base = self.palier(parser, taille)[0]
                    change, apres, profil = self.apres_mise_a_jour(parser, taille)
                    complet = self.apres_mise_a_jour(parser)[1]
                except BudgetExceeded:
                    raise
                except Exception as erreur:
                    log.exception("Scénario en échec pour %s (palier %s)", conf.id, taille)
                    message = f"{type(erreur).__name__} : {erreur}"
                    self._vides(writer, conf, "none", "error", message)
                    continue
                self._cellule(
                    writer, conf, condition, taille, complet, apres, profil, maj=(change, base)
                )

    def _cellule(
        self,
        writer: JsonlWriter,
        conf: ResolvedConfiguration,
        condition: str,
        taille: int | None,
        parse: ParsedCorpus,
        sous: ParsedCorpus,
        profil: CorpusProfile,
        *,
        questions: Sequence[Question] | None = None,
        maj: tuple[CorpusChange, ParsedCorpus] | None = None,
    ) -> None:
        """Une (Configuration, Condition, Palier). `maj = (changement, corpus de base)` : phase
        `after_update`, l'index est produit par `update` depuis celui de la base, au Poste `update`
        (`questions` : celles reposées, `parse` et `sous` : le Corpus après mise à jour).
        En contexte parfait, l'Architecture ne reçoit
        que les Passages de référence : ni `check()` (le Corpus n'entre pas dans le prompt), ni
        index."""
        ctx = self.ctx
        questions = self.questions if questions is None else questions
        if self.faits:  # reprise : seules les clés absentes (`budget_exceeded`, `error`) refaites
            questions = [
                q
                for q in questions
                if answer_id(ctx.run_id, conf.id, ctx.condition, ctx.tier, ctx.phase, q.id)
                not in self.faits
            ]
            if not questions:
                return
        parfait = condition == "perfect_context"
        spec = ComponentSpec(name=conf.architecture, params=conf.params)

        def fabrique() -> ArchitectureBase:
            return ctx.build("architecture", spec)

        cle_applicabilite = conf.id if taille is None else f"{conf.id}@{taille}"
        if maj is not None:
            cle_applicabilite = f"{cle_applicabilite}@after_update"
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
            self._vides(
                writer, conf, "none", "error", f"{type(erreur).__name__} : {erreur}", questions
            )
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
                **({} if maj is None else {"phase": "after_update"}),
            }
            self.ecrire_applicabilite()  # au fil de l'Exécution : un arrêt brutal ne la perd pas
            self._vides(writer, conf, methode, "inapplicable", raison, questions)
            return
        cle = "-"
        if not parfait:
            try:
                if maj is None:
                    log.info("étape index : %s", cle_applicabilite)
                    with self.energie_de_phase(conf, "index"):
                        arch, cle = self.index_cache.build(ctx, fabrique, sous)
                else:
                    log.info("étape update : %s", cle_applicabilite)
                    ancien = self._index_de_base(conf, fabrique, maj[1])
                    with self.energie_de_phase(conf, "update"):
                        arch, cle = self.index_cache.build(
                            ctx, fabrique, sous, post="update", change=maj[0], old_dir=ancien
                        )
            except BudgetExceeded:
                raise
            except Exception as erreur:
                log.exception("Configuration %s : index en échec", conf.id)
                message = f"{type(erreur).__name__} : {erreur}"
                self._vides(writer, conf, methode, "error", message, questions)
                return
        log.info(
            "étape answer : %s (%s, palier %s, index %s, %d Questions)",
            conf.id,
            condition,
            "all" if taille is None else taille,
            cle,
            len(questions),
        )
        # Réponses écrites après leurs spans retenus : un arrêt dur pendant la phase perd les
        # deux à la fois, et la reprise (AD-11) repose ces Questions depuis les caches.
        reponses: list[Answer] = []

        def ecrire_reponses() -> None:
            for answer in reponses:
                self._ecrire(writer, answer)

        with self.energie_de_phase(conf, "query", apres=ecrire_reponses):
            for q in questions:
                if not parfait:
                    reponses.append(self.poser(conf, q, arch, methode))
                    continue
                try:
                    passages = passages_de_reference(parse, q)
                except ConfigError as erreur:
                    reponses.append(self._sans_contexte_parfait(conf, q, erreur))
                    continue
                reponses.append(self.poser(conf, q, arch, methode, passages))

    def _index_de_base(
        self,
        conf: ResolvedConfiguration,
        fabrique: Callable[[], ArchitectureBase],
        base: ParsedCorpus,
    ) -> Path:
        """Dossier de l'index de la base, point de départ de `update` (jamais modifié). Absent
        (Condition `standard` non exécutée en base, base en échec), il est construit d'abord, en
        phase `base` et au Poste `indexing`."""
        cle = index_key(base.fingerprint, fabrique())
        if not self.index_cache.has(cle):
            ctx = self.ctx
            ctx.phase = "base"
            try:
                with self.energie_de_phase(conf, "index"):
                    self.index_cache.build(ctx, fabrique, base)
            finally:
                ctx.phase = "after_update"
        return self.index_cache.path(cle)

    def _sans_contexte_parfait(
        self, conf: ResolvedConfiguration, q: Question, erreur: ConfigError
    ) -> Answer:
        """Ancrage de référence absent du Corpus de la phase. Pour une Question de Scénario dont
        l'Ancrage n'existe qu'après la mise à jour (`scenario_target.state: after`), c'est une
        non-applicabilité structurelle (`inapplicable`), non une panne ; elle est posée en
        `after_update`. Symétriquement, en `after_update`, l'Ancrage d'un Document supprimé
        (`state: before`) n'existe plus. Toute autre Question : `error`."""
        vide = ArchAnswer(text="", abstained=False, retrieval_method="provided")
        cible = q.scenario_target or {}
        phase, etat = self.ctx.phase, cible.get("state")
        if phase == "base" and etat == "after":
            raison = "Ancrage créé par le Scénario, absent du Corpus de base (phase after_update)"
            return self._answer(conf, q, vide, "inapplicable", raison)
        if phase == "after_update" and etat == "before":
            raison = "Ancrage supprimé par le Scénario, absent du Corpus après mise à jour"
            return self._answer(conf, q, vide, "inapplicable", raison)
        log.warning("Question %s (%s) sans contexte parfait : %s", q.id, conf.id, erreur)
        return self._answer(conf, q, vide, "error", f"{type(erreur).__name__} : {erreur}")


def run_experiment(
    experience: ResolvedExperiment,
    questions: FrozenQuestions,
    *,
    wl_home: Path,
    run_id: str | None = None,
    providers: Providers | None = None,
    reprendre: str | None = None,
) -> RunOutcome:
    """Exécute une Expérience validée dont le Jeu est vérifié (`load_questions`).

    `run.lock` est pris (et les réservations orphelines récupérées) avant d'écrire quoi que ce
    soit ; un second `wl run` échoue donc sans créer de dossier. `providers` : Faux LLM
    scénarisé des tests ; sinon les adaptateurs du Catalogue (`build_providers`, `fake` compris).
    `reprendre` : `run_id` d'une Exécution à reprendre (story 4.8) ; `ConfigError` (code 2) si
    elle est introuvable, terminée, ou si l'Expérience ou le Gel diffèrent (plafonds exceptés).
    """
    verifier_paliers(experience, questions)
    corpus = declare(Path(experience.corpus))
    experience = resolve_parsers(experience, corpus)
    panels = panels_de(experience)  # Panel inadmissible : refus (code 2) avant tout appel
    scenario = Path(experience.scenario) if experience.scenario else None
    if scenario is not None:  # Scénario invalide : refus (code 2) avant le dossier d'Exécution
        charger(scenario, ingest(corpus, experience.configurations[0].parser.name, wl_home=wl_home))
    entrees: dict[str, str] | None = None
    if reprendre is not None:
        verifier_reprise(experience, wl_home, reprendre, questions.freeze_sha256)
        if deja_terminee(wl_home, reprendre):
            raise ConfigError(
                "reprendre", f"Exécution {reprendre} déjà terminée : rien à reprendre"
            )
        run_id = reprendre
    else:  # contenu du Corpus, du Scénario et du Catalogue, comparé à une reprise
        entrees = empreintes_entrees(experience, wl_home)
    if run_id is None:
        run_id = new_run_id(sha16(canonical_json(experience.model_dump(mode="json"))))
    # Le verrou est pris d'abord, puis les réservations orphelines sont réglées à leur estimation
    # (`Ledger(recover_orphans=True)`) : une reprise après arrêt brutal repart d'un registre sain.
    with Context.from_experiment(
        experience, wl_home=wl_home, run_id=run_id, providers=providers, execution=True
    ) as ctx:
        if reprendre is None:
            dossier = create_run_dir(
                wl_home, run_id, experience, freeze_sha256=questions.freeze_sha256, inputs=entrees
            )
        else:
            dossier = wl_home / "runs" / run_id
            reopen_run_dir(dossier, experience.budget, experience.max_error_rate)
        handler: logging.Handler | None = None
        paquet = logging.getLogger("wavelibrarian")
        niveau = paquet.level
        try:
            handler = attach_run_log(dossier)
            if paquet.getEffectiveLevel() > logging.INFO:  # étapes du runner dans run.log
                paquet.setLevel(logging.INFO)
            log.info("Exécution %s : %d Questions posées", run_id, len(questions.questions))
            runner = _Runner(ctx, dossier, corpus, questions.questions, experience.tier, scenario)
            if reprendre is not None:
                runner.reprendre()
                log.info("Exécution %s reprise : %d clés déjà traitées", run_id, len(runner.faits))
            _, profil = runner.preparer(experience.configurations[0].parser.name)
            runner.ecrire_profil(profil)
            statut: RunStatus = "completed"
            try:
                with JsonlWriter(dossier, "answers.jsonl") as writer:
                    try:
                        for conf in experience.configurations:
                            runner.configuration(writer, conf, experience)
                    except BudgetExceeded as erreur:  # arrêt propre ; reprise : --reprendre
                        log.warning("Plafond atteint : %s", erreur)
                        statut = "budget_exceeded"
                        runner.marquer_budget_exceeded(writer, experience)
            finally:
                runner.ecrire_applicabilite()
            if statut == "completed":  # jugement après toutes les Réponses (AD-11)
                try:
                    runner.juger(experience, panels)
                except BudgetExceeded as erreur:  # arrêt propre ; reprise : --reprendre
                    log.warning("Plafond atteint pendant le jugement : %s", erreur)
                    statut = "budget_exceeded"
            runner.compter()
            causes: list[dict[str, Any]] = []
            if statut == "completed":  # le plafond prime (code 3) ; sinon P9, story 8.3
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
            log.info("Exécution %s : %s, Réponses %s", run_id, statut, runner.counts)
            if runner.non_jugees:
                log.warning(
                    "%d Critère(s) jugé(s) sans verdict de panel ; reprise : --reprendre",
                    runner.non_jugees,
                )
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
        unjudged=runner.non_jugees,
        causes=tuple(causes),
    )
