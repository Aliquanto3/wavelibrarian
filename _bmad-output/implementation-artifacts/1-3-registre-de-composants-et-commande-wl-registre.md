---
story: "1.3"
title: Registre de Composants et commande `wl registre`
status: review
---

# Story 1.3 : Registre de Composants et commande `wl registre`

## Code Map

- `src/wavelibrarian/registry.py` : `register(kind, name)`, `get`, `names`, `list_components(kind=None)` (`ComponentInfo`, `ParamInfo`), `discover()`.
- `src/wavelibrarian/cli.py` : commande `wl registre [--kind K]`.
- `tests/unit/test_registry.py`.

## Design Notes

- Les `kind` valides viennent de `ports.components.KINDS` (liste fermée de `contracts.md` §2) ; un `kind` hors liste lève `ConfigError` à la décoration, à `get` et à `list_components`.
- Le registre est un dictionnaire de module `(kind, name) -> classe`. Les tests l'isolent par une fixture qui le sauvegarde et le restaure.
- `list_components` lit `Params.model_fields` : type affiché (`int`, ou la forme `str(annotation)`), défaut en `repr`, ou « obligatoire ». La description est `inspect.getdoc`.
- `discover()` parcourt `wavelibrarian.components` et `wavelibrarian.architectures` par `pkgutil.walk_packages` ; un drapeau de module rend le second appel sans effet.
- `wl registre --kind inconnu` sort en 2 (validation) avec un message français ; sortie vide : « Aucun Composant enregistré. », code 0.
- Aucun Composant réel n'existe encore : la sortie de `wl registre` est vide hors tests.

## Tâches et critères

- [x] `@register("chunker","toy")`, `get`, `list_components` avec nom, kind, description et Params typés avec défauts : `test_get_et_list_components`.
- [x] `kind` hors liste et doublon `(kind, name)` : `ConfigError` : `test_kind_inconnu_et_doublon`.
- [x] Nom inconnu : `ConfigError` listant `toy` et `toy2` du seul `kind` : `test_nom_inconnu_liste_le_meme_kind`.
- [x] `discover()` récursif par `pkgutil`, second appel sans effet : `test_discover_recursif_et_idempotent`.
- [x] `wl registre` et `--kind`, en français, code 0 : `test_cli_registre` ; `kind` invalide : `test_cli_kind_invalide`.

## Auto Run Result

- Statut : prêt pour revue.
- Vérifications : voir le rapport de l'agent (pytest, pyright, contrôle rapide).
- Aucun appel réseau, ni Ollama, ni GPU (`CUDA_VISIBLE_DEVICES=-1`, threads à 4).
- Reports : validation du `Params` (`extra="forbid"`, `frozen=True`) à l'enregistrement non exigée par les critères ; à traiter avec les tests de conformité (stories 6 et 7) si utile.
