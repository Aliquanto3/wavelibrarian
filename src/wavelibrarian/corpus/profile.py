"""Profil d'un Corpus (FR-7) : tailles, structure, densité de liens, langues, volatilité.

Les tokens sont comptés une seule fois, avec le tokenizer de référence du profil ; la conversion
vers un autre modèle passe par `CorpusProfile.tokens_for` (facteur du Catalogue, défaut 1,2).
"""

from collections import Counter
from typing import Literal

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import CorpusProfile, ParsedCorpus
from wavelibrarian.corpus.entities import link_density
from wavelibrarian.ports.measure import Tokenizer


def profile(
    corpus: ParsedCorpus,
    *,
    parser: str,
    tokenizer: Tokenizer,
    volatility: Literal["low", "medium", "high"],
) -> CorpusProfile:
    """Calcule le Profil d'un `ParsedCorpus`.

    `heading_depth_*` : profondeur maximale de `heading_path` de chaque Document (0 sans titre,
    ce Document comptant dans la moyenne). `dominant_lang` : langue du plus grand nombre de
    Documents, à égalité la première par ordre alphabétique.
    """
    docs = corpus.documents
    if not docs:
        raise ConfigError("corpus", "aucun Document ingéré : le Profil serait vide")
    par_doc = [sum(tokenizer.count(b.text) for b in d.blocks) for d in docs]
    n_tokens = sum(par_doc)
    tokens_tables = sum(
        tokenizer.count(b.text) for d in docs for b in d.blocks if b.kind == "table"
    )
    profondeurs = [max((len(a.heading_path) for a in d.anchors.values()), default=0) for d in docs]
    n = len(docs)
    langs = Counter(d.lang for d in docs)
    return CorpusProfile(
        corpus_id=corpus.corpus_id,
        fingerprint=corpus.fingerprint,
        parser=parser,
        tokenizer=tokenizer.name,
        n_documents=n,
        n_tokens=n_tokens,
        mean_tokens_per_document=n_tokens / n,
        heading_depth_max=max(profondeurs),
        heading_depth_mean=sum(profondeurs) / n,
        link_density=link_density(corpus),
        table_share=tokens_tables / n_tokens if n_tokens else 0.0,
        images_per_document=sum(b.kind == "image" for d in docs for b in d.blocks) / n,
        dominant_lang=min(langs, key=lambda k: (-langs[k], k)),
        langs=dict(sorted(langs.items())),
        formats=dict(sorted(Counter(d.format for d in docs).items())),
        volatility=volatility,
    )
