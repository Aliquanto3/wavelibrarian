"""Contexte d'exécution (contracts.md §2.4). Implémenté par `runner/context.py`."""

import random
from typing import Any, Protocol

from wavelibrarian.core.types import Condition, CostPost, Phase
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.ports.gateway import ModelGateway
from wavelibrarian.ports.measure import Tokenizer, Tracer


class RunContext(Protocol):
    run_id: str
    config_id: str
    seed: int
    condition: Condition  # fixé par le runner
    tier: int | None
    phase: Phase
    gateway: ModelGateway
    tracer: Tracer
    tokenizer: Tokenizer  # tokenizer de référence du profil
    # `ModelCatalog` et `ProfileSettings` vivent dans `config` (couche supérieure à `ports`) :
    # typés `Any` ici pour respecter le contrat de couches.
    catalog: Any
    profile: Any

    def build(self, kind: str, spec: ComponentSpec) -> Any: ...  # seule voie de construction
    def rng(self, *keys: str) -> random.Random: ...  # Random(sha16(seed, *keys))
    def tokenizer_for(self, model_id: str) -> Tokenizer: ...

    @property
    def post(self) -> CostPost: ...  # fixé par le runner, lecture seule

    @property
    def question_id(self) -> str | None: ...
