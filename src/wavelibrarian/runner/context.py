"""`RunContext` concret (contracts.md §2.4, AD-2, AD-8, AD-20, AD-21).

Un seul objet sert le runner et les commandes hors Exécution (`wl questions generer`,
`closed-book`) : il câble la passerelle mesurée, le Tracer, le registre de dépense et le Cache
de réponses depuis un profil et un Catalogue. Seul un contexte d'Exécution prend `run.lock`.
"""

import random
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any

from wavelibrarian import registry
from wavelibrarian.config.catalog import ModelCatalog, load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.config.experiment import Budget, ResolvedExperiment, RetrySettings
from wavelibrarian.config.schemas import ProfileSettings, valider
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import Condition, CostPost, Phase
from wavelibrarian.llm.budget import Ledger
from wavelibrarian.llm.cache import ResponseCache
from wavelibrarian.llm.gateway import Providers
from wavelibrarian.measure.tokenizers import make_tokenizer, tokenizer_for
from wavelibrarian.measure.tracing import Tracer
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.ports.gateway import ModelGateway
from wavelibrarian.ports.measure import Tokenizer
from wavelibrarian.ports.measure import Tracer as PortTracer
from wavelibrarian.runner.lock import RunLock
from wavelibrarian.runner.wiring import build_gateway

_GARDER: Any = object()  # `scope` : « ne pas toucher » (distinct de None pour `question_id`)


class Context:
    """Implémente le Protocol `ports.context.RunContext`.

    `execution=True` : contexte d'Exécution, qui prend `WL_HOME/run.lock` (échec si une autre
    Exécution le détient) et récupère les réservations orphelines du registre de dépense.
    `providers` : adaptateurs injectés (Faux LLM scénarisé des tests) ; sinon ceux du Catalogue.
    """

    def __init__(
        self,
        *,
        profile: ProfileSettings,
        catalog: ModelCatalog,
        wl_home: Path,
        run_id: str,
        seed: int = 0,
        config_id: str = "",
        condition: Condition = "standard",
        tier: int | None = None,
        phase: Phase = "base",
        parser: str = "auto",
        post: CostPost = "query",
        budget: Budget | None = None,
        retries: RetrySettings | None = None,
        providers: Providers | None = None,
        execution: bool = False,
    ) -> None:
        self.run_id = run_id
        self.config_id = config_id
        self.seed = seed
        self.condition: Condition = condition
        self.tier = tier
        self.phase: Phase = phase
        self.parser = parser
        self.catalog = catalog
        self.profile = profile
        self.wl_home = wl_home
        self.run_dir = wl_home / "runs" / run_id
        self._post: CostPost = post
        self._question_id: str | None = None
        self._lock: RunLock | None = None
        self._ledger: Ledger | None = None
        self._cache: ResponseCache | None = None
        if execution:
            self._lock = RunLock(wl_home, run_id)
            self._lock.acquire()
        try:
            self._ledger = Ledger(
                budget if budget is not None else Budget(),
                run_id,
                wl_home,
                recover_orphans=execution,  # seulement sous `run.lock` (AD-11)
            )
            self._cache = ResponseCache(wl_home)
            self.tracer: PortTracer = Tracer(self, self.run_dir / "traces.jsonl")
            self.tokenizer: Tokenizer = make_tokenizer(profile.tokenizer)
            self.gateway: ModelGateway = build_gateway(
                catalog=catalog,
                profile=profile,
                providers=providers,
                ledger=self._ledger,
                cache=self._cache,
                tracer=self.tracer,
                retries=retries,
            )
        except BaseException:
            self.close()
            raise

    @classmethod
    def from_experiment(
        cls,
        experience: ResolvedExperiment,
        *,
        wl_home: Path,
        run_id: str,
        config_id: str | None = None,
        providers: Providers | None = None,
        execution: bool = True,
    ) -> "Context":
        """Contexte d'une Exécution : profil, Catalogue, graine, plafonds et reprises de
        l'Expérience résolue. `config_id` absent : la première Configuration."""
        conf = next(
            (c for c in experience.configurations if config_id in (None, c.id)),
            None,
        )
        if conf is None:
            raise ValueError(f"Configuration inconnue : {config_id!r}")
        return cls(
            profile=experience.profile_settings,
            catalog=load_catalog(Path(experience.catalog) if experience.catalog else None),
            wl_home=wl_home,
            run_id=run_id,
            seed=experience.seed,
            config_id=conf.id,
            parser=conf.parser.name,
            budget=experience.budget,
            retries=experience.retries,
            providers=providers,
            execution=execution,
        )

    @classmethod
    def from_profile(
        cls,
        profile: str,
        *,
        wl_home: Path,
        run_id: str,
        seed: int = 0,
        catalog: ModelCatalog | None = None,
        providers: Providers | None = None,
    ) -> "Context":
        """Contexte d'une commande hors Exécution : un profil seul, sans `run.lock`."""
        return cls(
            profile=load_profile(profile),
            catalog=catalog if catalog is not None else load_catalog(),
            wl_home=wl_home,
            run_id=run_id,
            seed=seed,
            providers=providers,
            execution=False,
        )

    @property
    def post(self) -> CostPost:
        return self._post

    @property
    def question_id(self) -> str | None:
        return self._question_id

    @contextmanager
    def scope(
        self, *, post: CostPost = _GARDER, question_id: str | None = _GARDER
    ) -> Iterator[None]:
        """Fixe le Poste de coût et la Question des spans du bloc ; restaure à la sortie."""
        avant = (self._post, self._question_id)
        if post is not _GARDER:
            self._post = post
        if question_id is not _GARDER:
            self._question_id = question_id
        try:
            yield
        finally:
            self._post, self._question_id = avant

    def build(self, kind: str, spec: ComponentSpec) -> Any:
        """Seule voie de construction d'un Composant : `cls(params, ctx)` après validation."""
        registry.discover()
        cls: Any = registry.get(kind, spec.name)
        params = valider(cls.Params, spec.params, prefixe=f"{kind}.{spec.name}.params")
        return cls(params, self)

    def rng(self, *keys: str) -> random.Random:
        """Aléa contrôlé (AD-20) : `Random(sha16(seed, *keys))`, même graine, même suite."""
        return random.Random(int(sha16(str(self.seed), *keys), 16))

    def tokenizer_for(self, model_id: str) -> Tokenizer:
        return tokenizer_for(model_id, self.catalog, self.tokenizer)

    def close(self) -> None:
        """Ferme registre, cache et verrou ; idempotent."""
        for ressource in (self._ledger, self._cache):
            if ressource is not None:
                ressource.close()
        self._ledger = self._cache = None
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def __enter__(self) -> "Context":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
