"""Câblage de la passerelle mesurée depuis un profil (joint `llm` à `measure`)."""

from functools import partial

from wavelibrarian.config.catalog import ModelCatalog
from wavelibrarian.config.experiment import RetrySettings
from wavelibrarian.config.schemas import ProfileSettings
from wavelibrarian.llm.budget import Ledger
from wavelibrarian.llm.cache import ResponseCache
from wavelibrarian.llm.gateway import MeteredGateway, Providers
from wavelibrarian.measure.energy import make_estimator
from wavelibrarian.measure.tokenizers import make_tokenizer, tokenizer_for
from wavelibrarian.ports.measure import Tracer


def build_gateway(
    *,
    catalog: ModelCatalog,
    profile: ProfileSettings,
    providers: Providers,
    ledger: Ledger,
    cache: ResponseCache,
    tracer: Tracer,
    retries: RetrySettings | None = None,
) -> MeteredGateway:
    """Tokenizer de référence du profil, estimateur d'énergie du profil, délai d'appel du profil."""
    reference = make_tokenizer(profile.tokenizer)
    return MeteredGateway(
        catalog=catalog,
        providers=providers,
        ledger=ledger,
        cache=cache,
        tracer=tracer,
        tokenizer_for=partial(tokenizer_for, catalog=catalog, reference=reference),
        estimator=make_estimator(profile.energy),
        retries=retries,
        default_timeout_s=profile.defaults.call_timeout_s,
    )
