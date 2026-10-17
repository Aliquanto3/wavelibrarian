---
story: "1.3"
title: Registre de Composants et commande `wl registre`
status: done
---

# Story 1.3 : Registre de Composants et commande `wl registre`

## Code Map

- `src/wavelibrarian/registry.py` : `register(kind, name)`, `get`, `names`, `list_components(kind=None)` (`ComponentInfo`, `ParamInfo`), `discover()`.
- `src/wavelibrarian/cli.py` : commande `wl registre [--kind K]`.
- `tests/unit/test_registry.py`.

## Design Notes

- Les `kind` valides viennent de `ports.components.KINDS` (liste fermée de `contracts.md` §2) ; un `kind` hors liste lève `ConfigError` à la décoration, à `get` et à `list_components`.
- Le registre est un dictionnaire de module `(kind, name) -> classe`. `register` refuse une classe sans `Params` pydantic en `extra="forbid"` et `frozen=True` (AD-2). Les tests isolent le registre par une fixture qui le sauvegarde et le restaure, et qui retire de `sys.modules` les modules importés par `discover()` pendant le test.
- `list_components` lit `Params.model_fields` : type affiché (`int`, ou la forme `str(annotation)`), défaut en `repr`, « calculé » pour une `default_factory` qui lit les données, ou « obligatoire ». La description est la docstring propre à la classe (`cls.__dict__`), sans héritage.
- `discover()` parcourt `wavelibrarian.components` et `wavelibrarian.architectures` par `pkgutil.walk_packages` ; un drapeau de module rend le second appel sans effet.
- `wl registre --kind inconnu` sort en 2 (validation) avec un message français.
- Aucun Composant réel n'existe encore : hors tests, `wl registre` affiche seulement « Aucun Composant enregistré. » et sort en 0.

## Tâches et critères

- [x] `@register("chunker","toy")`, `get`, `list_components` avec nom, kind, description et Params typés avec défauts : `test_get_et_list_components`.
- [x] `kind` hors liste et doublon `(kind, name)` : `ConfigError` : `test_kind_inconnu_et_doublon`.
- [x] Nom inconnu : `ConfigError` listant `toy` et `toy2` du seul `kind` : `test_nom_inconnu_liste_le_meme_kind`.
- [x] `discover()` récursif par `pkgutil` sous `components` et sous `architectures`, second appel sans effet : `test_discover_recursif_et_idempotent` (paramétré).
- [x] `Params` en `extra="forbid"` et `frozen=True` exigé (AD-2) : `test_params_exige_forbid_et_frozen`.
- [x] `wl registre` et `--kind`, en français, code 0 : `test_cli_registre` ; `kind` invalide : `test_cli_kind_invalide`.

## Auto Run Result

- Statut : prêt pour revue.
- Vérifications : voir le rapport de l'agent (pytest, pyright, contrôle rapide).
- Aucun appel réseau, ni Ollama, ni GPU (`CUDA_VISIBLE_DEVICES=-1`, threads à 4).
- Reports : aucun (la validation du `Params` à l'enregistrement a été ajoutée en revue).

## Revue

Revue Opus du 2026-10-17, sur le commit 2de29d5 et la liste du second avis (Haiku).

| # | Sévérité | Source | Décision | Motif |
|---|---|---|---|---|
| 1 | medium | second avis | corrigé | La fixture ne restaurait pas `sys.modules` : un module importé par `discover()` restait en cache sans son enregistrement, donc absent des tests suivants dès qu'un vrai Composant existera (1.10). La fixture retire désormais ces modules. |
| 2 | medium | second avis | corrigé | AD-2 et `contracts.md` §2 exigent un `Params` en `extra="forbid"` et `frozen=True` ; sans contrôle, un `Params` laxiste accepterait en silence une faute de frappe dans l'Expérience. `register` lève maintenant `ConfigError`. |
| 3 | low | second avis | corrigé | `inspect.getdoc` reprenait la docstring de la classe de base (par exemple `ArchitectureBase`) ; la description vient de la docstring propre à la classe. |
| 4 | low | second avis | corrigé | Une `default_factory` qui lit les données levait `TypeError` dans `list_components` ; elle s'affiche « calculé ». |
| 5 | low | second avis | corrigé | `test_cli_kind_invalide` vérifie aussi le message. |
| 6 | low | second avis | corrigé | Couvert par le correctif 1 : les modules de `tmp_path` sont retirés de `sys.modules`. |
| 7 | low | second avis | corrigé | Le critère cite aussi `wavelibrarian.architectures` : le test de découverte est paramétré sur les deux paquets. |
| 8 | low | second avis | corrigé | Contradiction des Design Notes sur la sortie vide levée : hors tests, la sortie est « Aucun Composant enregistré. », code 0. |
| 12 | low | second avis | rejeté | Un module qui échoue à l'import est un défaut de code, pas de configuration : le convertir en `ConfigError` masquerait la trace utile. |
