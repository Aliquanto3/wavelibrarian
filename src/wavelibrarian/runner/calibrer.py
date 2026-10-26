"""Calibration des Juges sur des annotations humaines (FR-38, story 5.2).

Chaque Juge du réservoir admissible note chaque Réponse annotée `passes` fois (`pass_id` 0 à
`passes - 1`, les passes au-delà de 0 contournent le Cache de réponses), au Poste `judging`. Les
verdicts vont dans `<sortie>_verdicts.jsonl` (`calibration_verdicts.jsonl` de l'Exécution par
défaut) ; `verdicts.jsonl` n'est pas touché. Chaque appel de Juge est écrit et vidé sur disque
(`flush` + `os.fsync`) dès sa réception : une ligne par (Juge, Réponse, passe), qui porte
l'empreinte de l'Expérience, de l'Exécution, des annotations et des requêtes des Juges, et
l'identifiant de Registre ; `--reprendre` ne rappelle que les triplets absents, dans le même plafond
`per_run` (story 9.1). `calibration.json` résume kappa juge-humain,
instabilité et exclusion par Juge.
"""

import hashlib
import json
import logging
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.experiment import ResolvedConfiguration, ResolvedExperiment
from wavelibrarian.config.panel import closed_book_judge
from wavelibrarian.core.errors import (
    BudgetExceeded,
    ConfigError,
    NonConformantOutput,
    ProviderError,
    WlError,
)
from wavelibrarian.core.types import (
    NA,
    Answer,
    Criterion,
    ParsedCorpus,
    Question,
    VerdictValue,
    verdict_depuis_bool,
)
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
    reprendre: bool = False,
    ecraser: bool = False,
) -> tuple[Calibration, Path]:
    """Calibre les Juges ; écrit `calibration.json` (par défaut dans le dossier de l'Exécution,
    sinon `sortie`) et ses verdicts bruts à côté (`fichier_verdicts`). `ConfigError` (code 2) :
    Exécution inconnue, dossier sans annotation valide, aucune annotation sur une Réponse de
    l'Exécution, dossier de `sortie` impossible à créer, fichier de verdicts déjà présent sans
    `reprendre` ni `ecraser`, ou partiel d'une autre Expérience, Exécution ou annotation.
    `BudgetExceeded` (code 3) et `ProviderError` (code 4) : `calibration.json` n'est pas écrit, les
    verdicts déjà reçus restent dans `fichier_verdicts` ; l'exception porte `verdicts_recus` et
    `fichier_verdicts` (`reprendre=True` rappelle seulement les triplets absents)."""
    if reprendre and ecraser:
        raise ConfigError("--reprendre", "incompatible avec --ecraser")
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
    jeu = io.load(Path(experience.questions))  # avant tout appel payé
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
    chemin = sortie or dossier / FICHIER_CALIBRATION
    chemin_verdicts = fichier_verdicts(chemin)
    try:  # avant tout appel payé : un dossier de sortie impossible ne perd pas la calibration
        chemin.parent.mkdir(parents=True, exist_ok=True)
    except OSError as erreur:
        raise ConfigError(
            "--sortie", f"dossier {chemin.parent} impossible à créer : {erreur}"
        ) from None

    j = experience.judges
    pool = tuple(j.pool or experience.profile_settings.defaults.judge_pool)
    passes = j.calibration_passes
    catalogue = load_catalog(Path(experience.catalog) if experience.catalog else None)
    doubles = cal.doublement_annotees(annotations)
    juge_cal = j.calibration_judge
    tous: list[str] = [*pool, *([juge_cal] if juge_cal else [])]
    modeles: tuple[str, ...] = tuple(m for i, m in enumerate(tous) if m not in tous[:i])

    lu = _lire_verdicts(chemin_verdicts, reprendre, ecraser)  # avant tout appel payé
    # Reprise : même Registre (plafond `per_run`) et mêmes Traces que la tentative interrompue.
    id_cal = lu.id_cal or f"calibration-{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    corpus = _Corpus(experience, wl_home)
    verdicts_de: dict[str, dict[cal.Passe, VerdictValue]] = {m: {} for m in modeles}
    admises: dict[str, set[str]] = {m: set() for m in modeles}
    tentes: set[str] = set()  # Juges appelés au moins une fois
    appels = 0
    with Context.from_experiment(
        experience, wl_home=wl_home, run_id=id_cal, providers=providers, execution=False
    ) as ctx:
        juges = construire_juges(ctx, modeles, cache_later_passes=False)
        # Préparation sans appel : items, Juges concernés et empreinte des requêtes.
        plan: list[tuple[str, Answer, Question, JudgeInput, list[Criterion], list[str]]] = []
        for aid, (a, q, conf) in cibles.items():
            familles = {catalogue.get(m).family for m in conf.answer_producers}
            annotes: list[Criterion] = [
                c
                for c in criteres_juges(q)
                if any(k[1] == aid and k[2] == c for k in annotations.verdicts)
            ]
            if not annotes:
                continue
            # Réponse vide ou abstention : `faithfulness` vaut `na` sans appel (story 9.3).
            criteres: list[Criterion] = [c for c in criteres_juges(q, a) if c in annotes]
            sans_objet = [c for c in annotes if c not in criteres]
            parse = corpus.de(conf, a)
            if parse is None:
                avertissements.append(f"Réponse {aid} ignorée : Corpus de sa phase indisponible")
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
            notants: list[str] = []
            for modele in modeles:
                est_pool = modele in pool and catalogue.get(modele).family not in familles
                est_cal = modele == juge_cal and aid in doubles
                if not (est_pool or est_cal):
                    continue
                notants.append(modele)
                if est_pool:
                    admises[modele].add(aid)
                for c in sans_objet:
                    for passe in range(passes):
                        verdicts_de[modele][(aid, c, passe)] = NA
            if criteres:
                plan.append((aid, a, q, item, criteres, notants))
        requetes = {
            f"{m}|{aid}": _empreinte_requete(juges[m], ctx.catalog, item, criteres)
            for aid, _, _, item, criteres, notants in plan
            for m in notants
        }
        empreinte = _empreinte(experience, run_id, annotations, modeles, requetes)
        faits = _faits(lu, chemin_verdicts, empreinte)
        for (modele, aid, passe), notes in faits.items():
            for c, (oui, _) in notes.items():
                verdicts_de[modele][(aid, c, passe)] = oui
        lu.finaliser(chemin_verdicts)  # `--ecraser` ou ligne tronquée, après toute validation
        ecrivain = _Ecrivain(chemin_verdicts, len(faits))
        try:
            for aid, a, q, item, criteres, notants in plan:
                ctx.config_id, ctx.condition, ctx.tier, ctx.phase = (
                    a.config_id,
                    a.condition,
                    a.tier,
                    a.phase,
                )
                for modele in notants:
                    tentes.add(modele)
                    for passe in range(passes):
                        if (modele, aid, passe) in faits:
                            continue
                        base = {
                            "answer_id": aid,
                            "judge_model": modele,
                            "pass_id": passe,
                            "empreinte": empreinte,
                            "calibration_id": id_cal,
                        }
                        try:
                            with ctx.scope(post="judging", question_id=q.id):
                                notes = juges[modele].judge(item, criteres, passe)
                            appels += 1
                        except NonConformantOutput as erreur:
                            # Sortie non conforme après un nouvel essai : consignée, la calibration
                            # continue. Plafond, fournisseur injoignable (code 4) et bogues sortent.
                            avertissements.append(
                                f"Juge {modele} en échec sur {aid} (passe {passe}) : {erreur}"
                            )
                            ecrivain.ecrire({**base, "missing": True, "error": str(erreur)}, False)
                            continue
                        for c, (oui, _) in notes.items():
                            verdicts_de[modele][(aid, c, passe)] = oui
                        corps = {
                            c: {"verdict": oui, "justification": justification}
                            for c, (oui, justification) in notes.items()
                        }
                        ecrivain.ecrire({**base, "verdicts": corps}, True)
        except (BudgetExceeded, ProviderError, KeyboardInterrupt) as erreur:
            setattr(erreur, "verdicts_recus", ecrivain.n)  # noqa: B010
            setattr(erreur, "fichier_verdicts", chemin_verdicts)  # noqa: B010
            raise
        finally:
            ctx.condition, ctx.tier, ctx.phase = "standard", None, "base"
            ecrivain.fermer()
        trace = ctx.run_dir / "traces.jsonl"
    sans_verdict = sorted(m for m in tentes if not verdicts_de[m])
    if sans_verdict:  # toutes ses passes ont échoué : rien n'est écrit
        raise WlError(
            f"aucun verdict conforme pour le(s) Juge(s) {', '.join(sans_verdict)} : "
            "calibration non écrite"
        )
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
    avertissements.extend(
        avertissements_closed_book(experience, resultat.exclus, jeu.questions, catalogue)
    )
    _ecrire(chemin, json.dumps(donnees, ensure_ascii=False, indent=2) + "\n")
    return resultat, chemin


def fichier_verdicts(calibration: Path) -> Path:
    """Verdicts bruts à côté de `calibration` : `<nom>_verdicts.jsonl` (`calibration.json` donne
    `calibration_verdicts.jsonl`). Deux calibrations de la même Exécution avec des `--sortie`
    distinctes (Juges Ollama et Claude en parallèle, story 8.11) ne s'écrasent pas."""
    return calibration.with_name(f"{calibration.stem}_verdicts.jsonl")


def _assembler(
    experience: ResolvedExperiment,
    run_id: str,
    annotations: cal.Annotations,
    modeles: tuple[str, ...],
    pool: tuple[str, ...],
    juge_cal: str | None,
    verdicts_de: Mapping[str, Mapping[cal.Passe, VerdictValue]],
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


Triplet = tuple[str, str, int]  # (Juge, answer_id, pass_id)


def _empreinte_requete(
    juge: Any, catalogue: Any, item: JudgeInput, criteres: list[Criterion]
) -> str:
    """Empreinte de la requête d'un Juge (passe 0) : prompt système, message, budget de sortie,
    schéma et entrée de Catalogue du modèle (que la passerelle applique à la requête)."""
    requete, schema = juge.requete(item, criteres, 0)
    corps = {
        "requete": requete.model_dump(mode="json"),
        "schema": schema.model_json_schema(),
        "catalogue": catalogue.get(requete.model_id).model_dump(mode="json"),
    }
    texte = json.dumps(corps, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _empreinte(
    experience: ResolvedExperiment,
    run_id: str,
    annotations: cal.Annotations,
    modeles: tuple[str, ...],
    requetes: Mapping[str, str],
) -> str:
    """Empreinte de ce qui rend deux fichiers de verdicts combinables : Expérience, Exécution,
    Juges, nombre de passes, annotations (clé, verdict) et requêtes des Juges (`requetes` :
    empreinte par Juge et Réponse ; un prompt, une Réponse ou un Catalogue modifié la change).
    Portée par chaque ligne."""
    cles = sorted([*k, v] for k, v in annotations.verdicts.items())
    corps = {
        "experiment_id": experience.experiment_id,
        "run_id": run_id,
        "judges": list(modeles),
        "passes": experience.judges.calibration_passes,
        "annotations": cles,
        "requests": dict(sorted(requetes.items())),
    }
    texte = json.dumps(corps, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


@dataclass
class _Lu:
    """Fichier de verdicts relu avant les appels. `garder` : octets à conserver (`None` : tout) ;
    `supprimer` : `--ecraser` sur un fichier existant."""

    lignes: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    id_cal: str | None = None
    garder: int | None = None
    supprimer: bool = False

    def finaliser(self, chemin: Path) -> None:
        """Juste avant le premier appel : supprime (`--ecraser`) ou retire la ligne tronquée
        (écriture temporaire puis remplacement atomique)."""
        if self.supprimer:
            chemin.unlink(missing_ok=True)
        elif self.garder is not None:
            temporaire = chemin.with_name(chemin.name + ".tmp")
            temporaire.write_bytes(chemin.read_bytes()[: self.garder])
            os.replace(temporaire, chemin)


def _lire_verdicts(chemin: Path, reprendre: bool, ecraser: bool) -> _Lu:
    """Refuse un fichier existant sans `reprendre` ni `ecraser` ; `reprendre` relit les lignes
    complètes (terminées par un saut de ligne ; la dernière, sans saut, vient d'un arrêt brutal et
    sera retirée). Une ligne complète illisible, d'un ancien format ou d'une autre calibration est
    refusée (code 2), jamais supprimée."""
    if not chemin.exists():
        return _Lu()
    if ecraser:
        return _Lu(supprimer=True)
    if not reprendre:
        raise ConfigError(
            "--reprendre",
            f"{chemin} existe déjà : relancer avec --reprendre (verdicts conservés) ou "
            "--ecraser (recommencer)",
        )
    brut = chemin.read_bytes()
    complet = brut.rfind(b"\n") + 1
    lu = _Lu(garder=complet if complet < len(brut) else None)
    for i, ligne in enumerate(brut[:complet].decode("utf-8").split("\n")[:-1], start=1):
        ident = ""
        try:
            x = json.loads(ligne)
            ancien = isinstance(x, dict) and "criterion" in x and "empreinte" not in x
            if not ancien:
                _ = (str(x["judge_model"]), str(x["answer_id"]), int(x["pass_id"]))
                ident, _ = str(x["calibration_id"]), str(x["empreinte"])
                if not x.get("missing"):
                    _ = [_verdict_lu(v["verdict"]) for v in x["verdicts"].values()]
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ConfigError("--reprendre", f"{chemin} ligne {i} illisible") from None
        if ancien:
            raise ConfigError(
                "--reprendre",
                f"{chemin} est à l'ancien format (une ligne par Critère, avant la story 9.1) : "
                "le renommer pour le garder, ou --ecraser pour recommencer",
            )
        if lu.id_cal not in (None, ident):
            raise ConfigError("--reprendre", f"{chemin} mêle deux calibrations (ligne {i})")
        lu.id_cal = ident
        lu.lignes.append((i, x))
    return lu


def _verdict_lu(valeur: Any) -> VerdictValue:
    """Verdict d'une ligne relue : `yes`, `no`, `na`, ou booléen d'un fichier de la 9.1."""
    v = verdict_depuis_bool(valeur)
    if v not in cal.VERDICTS:
        raise ValueError(f"verdict inconnu {valeur!r}")
    return cast(VerdictValue, v)


def _faits(
    lu: _Lu, chemin: Path, empreinte: str
) -> dict[Triplet, dict[str, tuple[VerdictValue, str]]]:
    """Triplets déjà notés du fichier relu, après contrôle de l'empreinte de chaque ligne ; un
    triplet `missing` est rappelé."""
    faits: dict[Triplet, dict[str, tuple[VerdictValue, str]]] = {}
    for i, x in lu.lignes:
        if x["empreinte"] != empreinte:
            raise ConfigError(
                "--reprendre",
                f"{chemin} ligne {i} vient d'une autre Expérience, Exécution, annotation ou "
                "requête de Juge (empreinte différente) : --ecraser pour recommencer",
            )
        cle = (x["judge_model"], x["answer_id"], int(x["pass_id"]))
        if x.get("missing"):
            faits.pop(cle, None)
        else:
            faits[cle] = {
                c: (_verdict_lu(v["verdict"]), str(v.get("justification", "")))
                for c, v in x["verdicts"].items()
            }
    return faits


class _Ecrivain:
    """Ajoute une ligne JSON par appel de Juge, vidée sur disque (`flush` + `os.fsync`) aussitôt.
    `n` : verdicts reçus présents dans le fichier (hors verdicts manquants)."""

    def __init__(self, chemin: Path, deja: int) -> None:
        self._chemin = chemin
        self._f: Any = None
        self.n = deja

    def ecrire(self, objet: dict[str, Any], recu: bool) -> None:
        if self._f is None:
            self._f = self._chemin.open("a", encoding="utf-8", newline="\n")
        self._f.write(json.dumps(objet, ensure_ascii=False, sort_keys=True) + "\n")
        self._f.flush()
        os.fsync(self._f.fileno())
        self.n += int(recu)

    def fermer(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None


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
