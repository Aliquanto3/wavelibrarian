---
story: "1.1"
title: Squelette du projet et garde-fous sans réseau
status: review
---

# Story 1.1 : Squelette du projet et garde-fous sans réseau

## Code Map

- `pyproject.toml` : dépendances épinglées, extras `local`/`energy`/`docling`, groupe dev, script `wl`, config pytest, ruff, pyright et contrats import-linter.
- `uv.lock` : verrou commité (aucun extra installé par `uv sync`).
- `.gitignore` : ajoute `.wl/` et `results/` (`.env` déjà présent).
- `.claude/cost-kit/controle_rapide.py` : ajoute `pyright` et `lint-imports` aux `COMMANDES`.
- `src/wavelibrarian/{core,ports,config,llm,llm/providers,measure,stats,corpus,scoring,evalset,components,architectures,runner,report}/__init__.py` : paquets vides du germe structurel.
- `src/wavelibrarian/registry.py` : module vide (story 1.3).
- `src/wavelibrarian/cli.py` : application typer `wl`, aide en français.
- `src/wavelibrarian/core/errors.py` : hiérarchie d'exceptions sous `WlError`.
- `src/wavelibrarian/core/ids.py` : `canonical_json`, `sha16`, `slug`, `new_run_id`.
- `tests/conftest.py` : fixture `wl_home`.
- `tests/unit/test_garde_fous.py` : socket bloqué, marqueurs, CLI, `.gitignore`, `lint-imports`.
- `tests/unit/core/test_errors.py`, `tests/unit/core/test_ids.py` : tests unitaires du noyau.
- `tests/test_import.py` : supprimé (remplacé par les tests ci-dessus).

## Design Notes

- Le contrat `layers` reprend l'ordre d'AD-1 ; les quatre contrats `forbidden` ont `unmatched_ignore_imports_alerting = "none"` car les modules autorisés (providers, embedders, measure) n'existent pas encore. Les exceptions deviennent actives dès leur création.
- `include_external_packages = true` est requis pour que les contrats `forbidden` voient `anthropic`, `httpx`, etc.
- Le contrat des providers n'autorise que `llm.gateway` et `llm.preflight` ; `llm/providers` reste importable de ces deux modules seulement.
- `ruff` exclut `.claude`, `_bmad` et `_bmad-output` (outillage, pas du code du banc).
- `new_run_id(experiment_hash)` : suffixe de 6 hex dérivé de `sha16(hash, horodatage ISO)`.
- `ProviderError(message, retryable=False)` ; `ConfigError(path, message)` expose `.path` et `.message`.
- Test réseau : `pytest-socket` lève `SocketBlockedError` dès la résolution (`getaddrinfo`), identique sous Windows et Linux ; avertissement bénin affiché.
- `-m 'not real_api and not real_local'` est dans `addopts` : un test `real_*` est désélectionné sans option.

## Tâches et critères

- [x] `pyproject.toml` : pile épinglée, extras, groupe dev, index PyTorch `explicit = true` associé à `torch` seul ; `uv sync` sans extra ; `uv.lock` commité. Couvert par `uv sync` + `uv run pytest -q` (suite verte) ; vérification manuelle du verrou.
- [x] Contrat `layers` et paquets du germe : `tests/unit/test_garde_fous.py::test_lint_imports_passe`.
- [x] Contrats `forbidden` (SDK, mesure, providers) et `lint-imports` dans le contrôle rapide : même test ; rupture vérifiée à la main (import `httpx` dans `core`, import de `cli` dans `ports`).
- [x] `addopts`, marqueurs : `test_socket_tcp_bloque`, `test_real_api_deselectionne` et `test_real_local_deselectionne` (désélectionnés, `2 deselected`).
- [x] `core/errors.py` : `tests/unit/core/test_errors.py`.
- [x] `core/ids.py` : `tests/unit/core/test_ids.py` (`canonical_json`, `sha16`, `slug`, `new_run_id`).
- [x] `wl --help` en français, sortie 0 : `test_aide_cli_en_francais`.
- [x] `.gitignore` : `test_gitignore` ; fixture `wl_home` : `test_wl_home`.

## Auto Run Result

- Statut : prêt pour revue.
- Écart : `typer` est déclaré `>=0.19,<1` et non `>=0.27,<0.28` car l'extra `docling` (docling 2.140) exige `typer<0.27` et rend la résolution impossible. Le verrou retient `typer 0.26.8`. À arbitrer à la revue (retirer la contrainte de l'extra docling, ou rehausser plus tard).
- Aucun appel réseau, aucun extra installé, `CUDA_VISIBLE_DEVICES=-1` et threads à 4.
