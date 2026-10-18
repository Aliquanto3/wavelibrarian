"""Calibration des Juges sur des annotations humaines (FR-38, story 5.2).

Chaque Juge du réservoir admissible note chaque Réponse annotée `passes` fois (`pass_id` 0 à
`passes - 1`, les passes au-delà de 0 contournent le Cache de réponses), au Poste `judging`. Les
verdicts vont dans `calibration_verdicts.jsonl` de l'Exécution ; `verdicts.jsonl` n'est pas
touché. `calibration.json` résume kappa juge-humain, instabilité et exclusion par Juge.
"""

import json
import logging
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.experiment import ResolvedConfiguration, ResolvedExperiment
from wavelibrarian.config.panel import closed_book_judge
from wavelibrarian.core.errors import BudgetExceeded, ConfigError
from wavelibrarian.core.types import Answer, Criterion, ParsedCorpus, Question
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.corpus.scenario import corpus_apres
from wavelibrarian.evalset import io
from wavelibrarian.ports.components import JudgeInput
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.execute import load_questions
from wavelibrarian.runner.rundir import read_answers
from wavelibrarian.scoring import calibration as cal
from wavelibrarian.scoring.panel import construire_juges, criteres_juges

log = logging.getLogger(__name__)

FICHIER_VERDICTS = "calibration_verdicts.jsonl"
FICHIER_CALIBRATION = "calibration.json"


@dataclass
class Calibration:
    donnees: dict[str, Any]  # contenu de `calibration.json`
    ignorees: list[str]  # annotations d'`answer_id` absents de l'Exécution
    avertissements: list[str] = field(default_factory=list)
    cout: dict[str, Decimal] = field(default_factory=dict)  # par devise, Poste judging
    n_appels: int = 0

    @property
    def exclus(self) -> dict[str, str]:
        return {
            m: str(f.get("reason"))
            for m, f in self.donnees["judges"].items()
            if f["excluded"] is True
        }


def calibrer(
    experience: ResolvedExperiment,
    annotations_dir: Path,
    run_id: str,
    *,
    wl_home: Path,
    sortie: Path | None = None,
    providers: Any = None,
) -> tuple[Calibration, Path]:
    """Calibre les Juges ; écrit `calibration_verdicts.jsonl` et `calibration.json` (par défaut
    dans le dossier de l'Exécution). `ConfigError` (code 2) : Exécution inconnue, dossier sans
    annotation valide, aucune annotation sur une Réponse de l'Exécution. `BudgetExceeded`
    (code 3) : rien n'est écrit."""
    dossier = wl_home / "runs" / run_id
    if not dossier.is_dir() or not (dossier / "answers.jsonl").is_file():
        raise ConfigError("--run", f"Exécution {run_id} introuvable dans {wl_home / 'runs'}")
    annotations = cal.charger_dossier(annotations_dir)
    reponses = read_answers(dossier)
    rapprochement = cal.rapprocher(annotations, reponses)
    annotations = rapprochement.annotations
    if not annotations.verdicts:
        raise ConfigError(
            str(annotations_dir),
            f"aucune annotation ne porte sur une Réponse de l'Exécution {run_id}",
        )
    questions = {q.id: q for q in load_questions(experience).questions}
    configs = {c.id: c for c in experience.configurations}
    avertissements: list[str] = []
    cibles: dict[str, tuple[Answer, Question, ResolvedConfiguration]] = {}
    for aid in sorted({k[1] for k in annotations.verdicts}):
        a = reponses[aid]
        q, conf = questions.get(a.question_id), configs.get(a.config_id)
        if a.status != "ok" or q is None or conf is None:
            avertissements.append(
                f"Réponse {aid} ignorée : statut {a.status}, Question ou Configuration "
                "absente de l'Expérience"
            )
            continue
        cibles[aid] = (a, q, conf)
    if not cibles:
        raise ConfigError(str(annotations_dir), "aucune Réponse annotée n'est notable (statut ok)")

    j = experience.judges
    pool = tuple(j.pool or experience.profile_settings.defaults.judge_pool)
    passes = j.calibration_passes
    catalogue = load_catalog(Path(experience.catalog) if experience.catalog else None)
    doubles = cal.doublement_annotees(annotations)
    juge_cal = j.calibration_judge
    tous: list[str] = [*pool, *([juge_cal] if juge_cal else [])]
    modeles: tuple[str, ...] = tuple(m for i, m in enumerate(tous) if m not in tous[:i])

    id_cal = f"calibration-{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    corpus = _Corpus(experience, wl_home)
    verdicts_de: dict[str, dict[cal.Passe, bool]] = {m: {} for m in modeles}
    admises: dict[str, set[str]] = {m: set() for m in modeles}
    lignes: list[dict[str, Any]] = []
    appels = 0
    with Context.from_experiment(
        experience, wl_home=wl_home, run_id=id_cal, providers=providers, execution=False
    ) as ctx:
        juges = construire_juges(ctx, modeles)
        try:
            for aid, (a, q, conf) in cibles.items():
                familles = {catalogue.get(m).family for m in conf.answer_producers}
                criteres: list[Criterion] = [
                    c
                    for c in criteres_juges(q)
                    if any(k[1] == aid and k[2] == c for k in annotations.verdicts)
                ]
                if not criteres:
                    continue
                parse = corpus.de(conf, a)
                if parse is None:
                    avertissements.append(
                        f"Réponse {aid} ignorée : Corpus de sa phase indisponible"
                    )
                    continue
                ancres = [
                    i
                    for r in q.reference_anchors
                    if (i := parse.resolve(r.doc, r.page, r.headings)) is not None
                ]
                item = JudgeInput(
                    question=q.text,
                    reference_answer=q.reference_answer,
                    reference_texts=tuple(parse.anchor_text(i) for i in ancres),
                    answer_text=a.text,
                    context_texts=a.context_texts,
                )
                ctx.config_id, ctx.condition, ctx.tier, ctx.phase = (
                    a.config_id,
                    a.condition,
                    a.tier,
                    a.phase,
                )
                for modele in modeles:
                    est_pool = modele in pool and catalogue.get(modele).family not in familles
                    est_cal = modele == juge_cal and aid in doubles
                    if not (est_pool or est_cal):
                        continue
                    if est_pool:
                        admises[modele].add(aid)
                    for passe in range(passes):
                        try:
                            with ctx.scope(post="judging", question_id=q.id):
                                notes = juges[modele].judge(item, criteres, passe)
                            appels += 1
                        except BudgetExceeded:
                            raise
                        except Exception as erreur:  # un Juge en échec n'arrête pas la calibration
                            avertissements.append(
                                f"Juge {modele} en échec sur {aid} (passe {passe}) : {erreur}"
                            )
                            continue
                        for c, (oui, justification) in notes.items():
                            verdicts_de[modele][(aid, c, passe)] = oui
                            lignes.append(
                                {
                                    "answer_id": aid,
                                    "judge_model": modele,
                                    "criterion": c,
                                    "pass_id": passe,
                                    "verdict": oui,
                                    "justification": justification,
                                }
                            )
        finally:
            ctx.condition, ctx.tier, ctx.phase = "standard", None, "base"
        trace = ctx.run_dir / "traces.jsonl"
    donnees = _assembler(
        experience,
        run_id,
        annotations,
        modeles,
        pool,
        juge_cal,
        verdicts_de,
        admises,
        doubles,
        avertissements,
    )
    cout = _cout_judging(trace)
    resultat = Calibration(donnees, rapprochement.ignorees, avertissements, cout, appels)
    jeu = io.load(Path(experience.questions))
    avertissements.extend(
        avertissements_closed_book(experience, resultat.exclus, jeu.questions, catalogue)
    )
    chemin = sortie or dossier / FICHIER_CALIBRATION
    _ecrire(dossier / FICHIER_VERDICTS, "".join(_ligne(x) for x in lignes))
    _ecrire(chemin, json.dumps(donnees, ensure_ascii=False, indent=2) + "\n")
    return resultat, chemin


def _assembler(
    experience: ResolvedExperiment,
    run_id: str,
    annotations: cal.Annotations,
    modeles: tuple[str, ...],
    pool: tuple[str, ...],
    juge_cal: str | None,
    verdicts_de: Mapping[str, Mapping[cal.Passe, bool]],
    admises: Mapping[str, set[str]],
    doubles: set[str],
    avertissements: list[str],
) -> dict[str, Any]:
    seuil = experience.judges.kappa_threshold
    juges: dict[str, Any] = {}
    for m in pool:
        if not admises[m]:
            avertissements.append(f"Juge {m} sans Réponse annotée admissible : non calibré")
            continue
        fiches = cal.fiches_du_juge(verdicts_de[m], annotations, admises[m])
        exclu, raison, signales = cal.decider_exclusion(fiches, seuil)
        avertissements.extend(f"{m} : {s}" for s in signales)
        juges[m] = {
            "excluded": exclu,
            "reason": raison,
            "warnings": signales,
            "criteria": {c: f.en_json() for c, f in fiches.items()},
        }
    donnees: dict[str, Any] = {
        "run_id": run_id,
        "experiment_id": experience.experiment_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "kappa_threshold": seuil,
        "passes": experience.judges.calibration_passes,
        "annotators": annotations.annotateurs,
        "judges": juges,
        "inter_annotator": cal.kappa_inter_annotateurs(annotations),
    }
    if juge_cal is not None:
        fiches = cal.fiches_du_juge(verdicts_de[juge_cal], annotations, doubles)
        donnees["calibration_judge"] = {
            "model": juge_cal,
            "criteria": {c: f.en_json() for c, f in fiches.items()},
        }
    return donnees


def avertissements_closed_book(
    experience: ResolvedExperiment,
    exclus: Mapping[str, str],
    questions: Any,
    catalog: Any,
) -> list[str]:
    """Pour chaque Juge exclu qui a servi au Filtre closed-book du Jeu (réponses libres notées par
    `closed_book_judge`), un avertissement : relancer `wl questions closed-book`."""
    if not exclus or not any(q.answer_form == "free" for q in questions):
        return []
    defauts = experience.profile_settings.defaults
    testes = list(
        dict.fromkeys(
            [*defauts.closed_book_models, *(m for q in questions for m in q.contaminated_by)]
        )
    )
    out: list[str] = []
    for juge in exclus:
        modeles = []
        for t in testes:
            try:
                if closed_book_judge(t, defauts.judge_pool, catalog) == juge:
                    modeles.append(t)
            except ConfigError:
                continue
        if modeles:
            out.append(
                f"Le Juge {juge} a servi au Filtre closed-book (modèles testés : "
                f"{', '.join(modeles)}) : relancer `wl questions closed-book`."
            )
    return out


class _Corpus:
    """Corpus dont les Ancrages donnent les textes de référence, par (parser, phase)."""

    def __init__(self, experience: ResolvedExperiment, wl_home: Path) -> None:
        self._exp = experience
        self._wl_home = wl_home
        self._declare = declare(Path(experience.corpus))
        self._cache: dict[tuple[str, str], ParsedCorpus | None] = {}

    def de(self, conf: ResolvedConfiguration, a: Answer) -> ParsedCorpus | None:
        parser = conf.parser.name
        cle = (parser, a.phase)
        if cle not in self._cache:
            base = ingest(self._declare, parser, wl_home=self._wl_home)
            if a.phase == "after_update":
                try:
                    if self._exp.scenario is None:
                        raise ConfigError("scenario", "aucun Scénario déclaré")
                    base = corpus_apres(
                        base, Path(self._exp.scenario), lang=self._declare.spec.lang, parser=parser
                    )
                except ConfigError as erreur:
                    log.warning("Corpus après mise à jour indisponible : %s", erreur)
                    self._cache[cle] = None
                    return None
            self._cache[cle] = base
        return self._cache[cle]


def _ligne(objet: dict[str, Any]) -> str:
    return json.dumps(objet, ensure_ascii=False, sort_keys=True) + "\n"


def _ecrire(chemin: Path, texte: str) -> None:
    """Écriture atomique (fichier temporaire puis `replace`)."""
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(texte, encoding="utf-8", newline="\n")
    tmp.replace(chemin)


def _cout_judging(trace: Path) -> dict[str, Decimal]:
    """Somme des `wl.cost` des spans du Poste `judging`, par devise."""
    total: dict[str, Decimal] = {}
    if not trace.is_file():
        return total
    for ligne in trace.read_text(encoding="utf-8").splitlines():
        if not ligne.strip():
            continue
        span = json.loads(ligne)
        if span.get("wl.post") != "judging":
            continue
        try:
            montant = Decimal(str(span.get("wl.cost", "0")))
        except InvalidOperation:
            continue
        devise = str(span.get("wl.currency", "EUR"))
        total[devise] = total.get(devise, Decimal(0)) + montant
    return total
