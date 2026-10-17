---
story: "3.2"
title: Contexte d'exécution concret
status: done
---

# Story 3.2 : Contexte d'exécution concret

## Code Map

- `src/wavelibrarian/runner/context.py` : `Context` (implémente `ports.context.RunContext`), constructeurs `Context.from_experiment(ResolvedExperiment, wl_home, run_id)` (Exécution) et `Context.from_profile(profil, wl_home, run_id)` (commande hors Exécution) ; `scope`, `build`, `rng`, `tokenizer_for`, `close` / context manager.
- `src/wavelibrarian/runner/lock.py` : `RunLock`, verrou du système sur `WL_HOME/run.lock` (`msvcrt` sous Windows, `fcntl.flock` ailleurs) ; le `run_id` du détenteur est lu pour le message.
- Tests : `tests/unit/runner/test_context.py` (profil `test`, Faux LLM). `wiring.py` et `ports/context.py` inchangés.

## Design Notes

- Le contexte câble `Ledger`, `ResponseCache`, `Tracer` (`WL_HOME/runs/<run_id>/traces.jsonl` pour une Exécution, `WL_HOME/hors-execution/<run_id>/traces.jsonl` hors Exécution) et `build_gateway` ; `tokenizer` = tokenizer de référence du profil, `tokenizer_for` = celui de `measure.tokenizers`. `providers` est injectable (Faux LLM scénarisé).
- `execution=True` prend `run.lock` avant d'ouvrir le registre, qui récupère alors ses réservations orphelines (report 1.8) ; sinon (commande hors Exécution) ni verrou ni récupération. En cas d'échec de construction, tout est refermé.
- Verrou du système plutôt que fichier `O_EXCL` : libéré par l'OS si le processus meurt, donc pas de verrou périmé à nettoyer. Un second contexte d'Exécution lève `WlError` « Exécution <run_id> en cours » (code 1 par contracts §5).
- `scope(post=..., question_id=...)` : mot-clé omis = valeur conservée (imbrication), restauration en `finally` ; `post` et `question_id` sont des propriétés sans setter. Aucun Poste initial : la passerelle refuse tout appel hors `scope(post=…)`, avant de payer (revue).
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

## Revue

Revue Opus en une passe, après rebase sur `main` (75db72b). Suite complète 425 verts, pyright 0 erreur, ruff propre, contrôle rapide sans erreur.

- medium, second avis 1, corrigé : `recover_orphans` réglait aussi les réservations ouvertes d'une commande hors Exécution concurrente, dont le `settle` levait ensuite « déjà close » après un appel payé. Le registre marque désormais ces réservations (`hors_execution`, colonne ajoutée par migration) et la récupération les laisse ouvertes, comptées au montant estimé. Test : `test_une_execution_ne_recupere_pas_la_reservation_d_une_commande_en_cours`.
- medium, second avis 2, corrigé : le Poste `query` par défaut comptait un appel oublié dans le coût de la Configuration (AD-8 ; contracts §2.4 ne fixe aucun défaut). Le Poste initial est vide, et la passerelle du contexte lève `WlError` avant l'appel. Le traceur écrivant le span après l'appel, une erreur levée par `ctx.post` seul aurait perdu le span d'un appel payé. Test : `test_appel_hors_scope_refuse_avant_de_payer`.
- medium, second avis 3, corrigé : les traces hors Exécution allaient dans `runs/<run_id>/`, où un `run_id` réutilisé aurait faussé l'égalité spans = dépense d'une Exécution (AD-9). Le contrat ne prévoit rien pour ces commandes : elles écrivent dans `WL_HOME/hors-execution/<run_id>/`. La création du dossier dès la construction (par l'exportateur) est conservée, sans effet nuisible.
- low, second avis 4, corrigé : `run_id` validé (`[A-Za-z0-9][A-Za-z0-9_-]*`), ce qui refuse `..` et les séparateurs. Le format strict `YYYYMMDD-HHMMSS-<6 hex>` n'est pas imposé, car les commandes hors Exécution et les tests utilisent d'autres identifiants. Test paramétré `test_run_id_invalide_refuse`.
- low, second avis 5, reporté (epic 4) : `parser` reste `"auto"` hors Exécution ; le runner le fixe depuis la Configuration.
- low, second avis 6, corrigé : `close` libère le verrou même si la fermeture du registre ou du cache échoue, et `acquire` déverrouille et ferme le fichier si l'écriture du `run_id` échoue. Test : `test_close_libere_le_verrou_meme_si_une_fermeture_echoue`.
- low, second avis 7, corrigé : le test du paramètre inconnu vérifie le chemin `embedder.fake.params.zzz_absent`, et non plus le mot qu'il passait lui-même.
- low, second avis 8, corrigé : test inter-processus du verrou (`test_verrou_detenu_par_un_autre_processus`, un sous-processus). En l'écrivant, on voit qu'un `RunLock` non référencé est libéré par le ramasse-miettes : le runner devra garder le contexte vivant pendant toute l'Exécution, ce qui est le cas avec `with`.
- low, second avis 9, rejeté : `model_construct` dans le test de `from_experiment` évite de reconstruire une Expérience complète. La validation est déjà couverte par les tests de `config/`.
- low, revue, reporté (epic 4) : une commande hors Exécution qui meurt laisse sa réservation ouverte pour toujours, comptée au montant estimé dans le plafond de période. C'est prudent, mais il faudrait un nettoyage explicite (par exemple `wl budget liberer`) si le cas se présente.
