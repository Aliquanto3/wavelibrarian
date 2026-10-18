"""Paliers de volume emboîtés et reproductibles (FR-54, AD-20, AD-22)."""

import random
from collections.abc import Iterable

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import ParsedCorpus
from wavelibrarian.corpus.declare import TiersSpec
from wavelibrarian.corpus.ingest import empreinte


def tirer_chemins(
    chemins: Iterable[str],
    tiers: TiersSpec,
    required_paths: Iterable[str] = (),
    tailles: Iterable[int] | None = None,
) -> dict[int, tuple[str, ...]]:
    """`{taille: source_path triés}` : Palier k inclus dans Palier k+1, requis dans chacun.

    Les Documents non requis sont mélangés une fois (graine `tiers.seed`, ordre de départ trié)
    et chaque Palier en prend le préfixe nécessaire : l'emboîtement en découle. Un Palier ne
    dépend donc pas des autres tailles : `tailles` (sous-ensemble de `tiers.sizes`, toutes par
    défaut) restreint le tirage aux Paliers demandés, et les requis doivent tenir dans le plus
    petit d'entre eux.
    """
    tous = sorted(set(chemins))
    requis = sorted(set(required_paths))
    inconnus = [p for p in requis if p not in tous]
    if inconnus:
        raise ConfigError("required_paths", f"Document absent du Corpus : {', '.join(inconnus)}")
    for i, taille in enumerate(tiers.sizes):
        if taille > len(tous):
            raise ConfigError(
                f"tiers.sizes[{i}]", f"{taille} dépasse le nombre de Documents ({len(tous)})"
            )
    voulues = tiers.sizes if tailles is None else tuple(sorted(set(tailles)))
    inconnues = [t for t in voulues if t not in tiers.sizes]
    if inconnues:
        raise ConfigError("tier", f"taille absente de tiers.sizes : {inconnues}")
    if voulues and len(requis) > voulues[0]:
        i = tiers.sizes.index(voulues[0])
        raise ConfigError(
            f"tiers.sizes[{i}]",
            f"le Palier de {voulues[0]} Documents ne peut pas contenir les {len(requis)} "
            "Documents requis (Ancrages de référence des Questions posées) : réduire "
            "`max_questions` ou demander un Palier plus grand",
        )
    ordre = [p for p in tous if p not in set(requis)]
    random.Random(int(sha16(str(tiers.seed), "tiers"), 16)).shuffle(ordre)
    return {t: tuple(sorted([*requis, *ordre[: t - len(requis)]])) for t in voulues}


def sous_corpus(parsed: ParsedCorpus, chemins: Iterable[str]) -> ParsedCorpus:
    """`ParsedCorpus` restreint à ces Documents, avec sa propre `fingerprint`."""
    gardes = set(chemins)
    documents = tuple(d for d in parsed.documents if d.source_path in gardes)
    return parsed.model_copy(update={"documents": documents, "fingerprint": empreinte(documents)})


def tirer(
    parsed: ParsedCorpus,
    tiers: TiersSpec,
    required_paths: Iterable[str] = (),
    tailles: Iterable[int] | None = None,
) -> dict[int, ParsedCorpus]:
    """Sous-corpus par taille de Palier (voir `tirer_chemins`)."""
    chemins = (d.source_path for d in parsed.documents)
    tirage = tirer_chemins(chemins, tiers, required_paths, tailles)
    return {t: sous_corpus(parsed, c) for t, c in tirage.items()}
