---
story: "3.2"
title: Contexte d'exécution concret
status: review
---

# Story 3.2 : Contexte d'exécution concret

## Code Map

- `src/wavelibrarian/runner/context.py` : `Context` (implémente `ports.context.RunContext`), constructeurs `Context.from_experiment(ResolvedExperiment, wl_home, run_id)` (Exécution) et `Context.from_profile(profil, wl_home, run_id)` (commande hors Exécution) ; `scope`, `build`, `rng`, `tokenizer_for`, `close` / context manager.
- `src/wavelibrarian/runner/lock.py` : `RunLock`, verrou du système sur `WL_HOME/run.lock` (`msvcrt` sous Windows, `fcntl.flock` ailleurs) ; le `run_id` du détenteur est lu pour le message.
- Tests : `tests/unit/runner/test_context.py` (profil `test`, Faux LLM). `wiring.py` et `ports/context.py` inchangés.

## Design Notes

- Le contexte câble `Ledger`, `ResponseCache`, `Tracer` (`WL_HOME/runs/<run_id>/traces.jsonl`) et `build_gateway` ; `tokenizer` = tokenizer de référence du profil, `tokenizer_for` = celui de `measure.tokenizers`. `providers` est injectable (Faux LLM scénarisé).
- `execution=True` prend `run.lock` avant d'ouvrir le registre, qui récupère alors ses réservations orphelines (report 1.8) ; sinon (commande hors Exécution) ni verrou ni récupération. En cas d'échec de construction, tout est refermé.
- Verrou du système plutôt que fichier `O_EXCL` : libéré par l'OS si le processus meurt, donc pas de verrou périmé à nettoyer. Un second contexte d'Exécution lève `WlError` « Exécution <run_id> en cours » (code 1 par contracts §5).
- `scope(post=..., question_id=...)` : mot-clé omis = valeur conservée (imbrication), restauration en `finally` ; `post` et `question_id` sont des propriétés sans setter. Le Poste initial est `query`.
- `build` : `registry.discover()`, `valider(cls.Params, params)` (paramètre inconnu = `ConfigError` au chemin `kind.nom.params.champ`), puis `cls(params, ctx)`.
- `rng(*clés)` = `Random(int(sha16(str(seed), *clés), 16))` (AD-20).
- `condition`, `tier`, `phase`, `config_id`, `parser` sont des attributs simples que le runner (epic 4) modifie.

## Tâches et critères

- [x] Contexte avec profil `test` : attributs exposés, Protocol satisfait (affectation typée `RunContext`, pyright) : `test_expose_les_attributs_et_satisfait_le_protocol`, `test_passerelle_mesuree_avec_le_provider_du_catalogue`, `test_contexte_d_experience_reprend_graine_plafonds_et_parser`.
- [x] `ctx.scope(post="evalset", question_id="q-001")` : span porteur, valeurs restaurées, lecture seule : `test_scope_pose_les_valeurs_dans_le_span_puis_les_restaure`, `test_scope_restaure_meme_sur_exception`, `test_post_et_question_id_en_lecture_seule`.
- [x] `ctx.build("embedder", ComponentSpec(name="fake"))` par `cls(params, ctx)` ; paramètre inconnu = `ConfigError` : `test_build_construit_par_cls_params_ctx`, `test_build_refuse_un_parametre_inconnu`, `test_build_refuse_un_composant_inconnu`.
- [x] `ctx.rng("split", "factual")` : même graine identique, autre graine différente : `test_rng_meme_graine_meme_suite_autre_graine_autre_suite`, `test_rng_depend_des_cles`.
- [x] Second contexte d'Exécution : « Exécution <run_id> en cours » ; hors Exécution sans verrou : `test_second_contexte_d_execution_echoue`.

## Auto Run Result

- Statut : review. 12 tests ciblés verts ; suite complète 406 verts ; pyright 0 erreur ; contrôle rapide sans erreur (avec `PYTHONUTF8=1` sous Windows, voir Reports).
- Reports traités : `tokenizer_for` et `build_gateway` (RunContext) ; prise de `run.lock` puis `Ledger(recover_orphans=True)` (report 1.8) ; injection de `FakeProvider` via `providers`.
- Reports non traités : (0) `controle_rapide.py` plante sous Windows sans `PYTHONUTF8=1` (lecture cp1252 d un fichier UTF-8), hors périmètre ; (1) handler de `run.log` et `limiter_journaux`, dans `llm.providers` (protégé par import-linter) : le runner doit passer par un point d'entrée de `llm` ; (2) isolation du Cache de réponses des runs scénarisés (`script`) : le contexte ouvre le cache sous `WL_HOME` sans option de dossier dédié : le runner devra ajouter un paramètre de cache à part ; (3) répartition de l'énergie locale par phase ; (4) refus à la validation d'un plafond `ollama` hors EUR ; (5) écriture de `manifest.json`, `run.log` et `experiment.resolved.yaml` dans `run_dir` : runner.
