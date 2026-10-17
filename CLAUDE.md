# WaveLibrarian

Banc de comparaison des architectures de recherche documentaire IA. Cadrage : `docs/cadrage.md`.

## Commandes
- Installer : `uv sync`
- Tests ciblés : `uv run pytest -q --tb=short tests/<fichier>` ; suite complète une fois avant intégration : `uv run pytest -q --tb=short`
- Lint / format : `uv run ruff check .` et `uv run ruff format .`
- Typage : `uv run pyright`
- Contrôle rapide (avant chaque rapport de dev-story) : `py .claude/cost-kit/controle_rapide.py`

## Conventions
- Python ≥ 3.12, gestion par `uv`, code dans `src/wavelibrarian/`, tests dans `tests/`.
- Dépôt public : aucun secret, aucune donnée client, aucun corpus sous licence restrictive dans le dépôt.
- Enchaînement par story : `agent-cost-kit:dev-story` → `second-avis` → `reviewer` → intégration.
