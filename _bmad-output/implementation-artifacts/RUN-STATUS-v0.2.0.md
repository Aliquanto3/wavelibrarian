# RUN-STATUS v0.2.0 - run autonome de l'epic 8

Fichier tenu par l'orchestrateur. Après `/clear`, relire ce fichier puis `sprint-status.yaml` ; une story `in-progress` sans commit d'intégration reprend depuis son fichier de story et son worktree. Contexte de l'epic : `epic-8-context.md`.

## Consignes

- Par story : `agent-cost-kit:dev-story` (Sonnet ; Opus pour 8.3) → `second-avis` → `reviewer` (avec la liste du second avis) → intégration sur `main`. Appels bloquants, une passe de revue, une voie. Suite complète + `py .claude/cost-kit/controle_rapide.py` avant chaque intégration.
- Ollama : rien au-delà de `/api/version`, `/api/ps`, `/api/tags`, ni `ollama`, ni `pytest -m real_local`, ni `wl run` réel, tant qu'Anaël n'a pas écrit « Ollama disponible ». Ensuite : `/api/tags`, profil `cpu`, `num_gpu: 0`, `CUDA_VISIBLE_DEVICES=-1`.
- Non décidable seul : valeur par défaut (`relevance_threshold`, prix/palier du Catalogue, option PageIndex hors AC), dépense > 1 $, modification d'AC → « À arbitrer par Anaël » + notification, puis continuer.
- Sonnet en échec deux fois sur une story → reprise avec Opus.
- Ordre : 8.1, 8.2 (SM-4 real_api, plafond 5 $), 8.3, 8.4 (code ; vérif. réelle en attente), 8.5 (WebFetch prix), 8.6 (charge CPU ≤ 4 threads), 8.7 (Ollama → notifier ; pendant l'attente, code de 8.9) ; après « Ollama disponible » : vérif. 8.4, 8.7, 8.8, paquet 8.9 depuis le run_id de 8.8. 8.10 : ne pas toucher. Fin : notifier avec le chemin du paquet, pousser `main`.

## État

| Champ | Valeur |
| --- | --- |
| Mis à jour | 2026-10-18 16:52 |
| Story en cours | **run arrêté** : tout ce qui est réalisable sans Anaël est fait |
| Stories livrées | 8 / 10 done (8.1 à 8.7, 8.9) ; 8.8 en review (à arbitrer) ; 8.10 attend les annotations |
| Dépense Anthropic | ~0,0103 $ (SM-4 de 8.2) / plafond 5 $ |
| Ollama | **rendu à Anaël** (16:33) ; plus besoin dans ce run |
| Attentes envers Anaël | (1) annoter `corpora/minicorpus/annotations/anael.yaml` (40 Réponses, run 20261018-115941-a2a512) pour 8.10 ; (2) arbitrer 8.8 (7 Critères sans verdict, relevance_threshold, q-044) ; (3) arbitrages non bloquants 8.2, 8.3, 8.6, fix-8-8 |
| À arbitrer par Anaël | **8.2 (non bloquant)** : en profil `test`, la part matérielle de la possession locale (secondes CPU réelles des spans `local` : index, BM25) est classée fictive avec l'énergie factice, pour que `cost_eur_real` = 0 exactement (AC 2 littéral) ; une énergie `measured` reste réelle. Alternative : garder la part matérielle dans le réel et relire l'AC 2 comme « 0 hors possession ». Choix du run : le premier (spec 8-2, section « Revue »). **8.7 : tranché par Anaël, option (c)** (granite4.2:3b en select_model, sans repeat_penalty). Rappel : `repeat_penalty: 1.15` global au profil `cpu` remplit l'AC (8/8 ok, 0 sortie tronquée, 56 verdicts, Juges intacts) mais fait passer la qualité de PageIndex de 1,00 à 0,00 sur q-002 (n = 1 ; contre-essai sans pénalité : même nœud, Réponse « 1297 » au lieu de « More than 2000 », le Generator est dégradé). Choix : (b) garder la pénalité globale ; (c) `select_model: granite4.2:3b` sans pénalité (sélection 18-20 s, 5,1 Go) ; (d) étendre le schéma pour réserver `repeat_penalty` au rôle `select_nodes` ou à un modèle. Spec 8-7, section « Revue ». **8.3 (non bloquant)** : voir spec 8-3, section « À arbitrer par Anaël » (`all_failed` et `--tolerer-erreurs`, Configuration seulement `inapplicable`, reprise d'une Exécution d'avant 8.3). **8.6 (non bloquant)** : méthode `mixed` (ou colonne à part) quand la part RAM d'une phase `measured` est estimée par formule ? **fix-8-8 (non bloquant)** : mesurer l'énergie du Poste `judging` (156 spans `unknown`) ? mesurer le GPU au profil `gpu` ? **8.8 (bloque done)** : 7 Critères sans verdict (Juges tronqués à 500/700 sur q-044 et q-017 ; options a/b/c de la spec 8-8) ; `relevance_threshold` : 0,1 maintenu, balayage non discriminant (Decider minicpm5:1b note 0,0 partout, latence à 0,3/0,5 rejouée du Cache) : refaire avec un autre prompt ou Decider et un Cache isolé par seuil ? ; q-044 (Ancrage absent en base) : phase update ou exclusion, et ses 4 lignes du paquet. |

## Stories livrées

| Story | Début | Fin | Commit d'intégration | Dépense | Notes |
| --- | --- | --- | --- | --- | --- |
| 8.1 | — | 10:45 | d9d285c | 0 $ | Liste blanche SPDX exacte, message nommant la licence ; Mini-corpus CC-BY-4.0 inchangé. Revue : AC 2 couvert (licence restrictive hors dépôt ou ignorée : declare puis ingest), refus d'une licence ignorée mais suivie. 1172 tests verts. |
| 8.4 | — | 11:27 | aef57dd | 0 $ | `think: bool \| None = False` au Catalogue, posé par la passerelle, clé de cache Ollama. Réel : real_local 2/2 ; mini-cpu 7 ok / 1 error, 49 verdicts, 9 min 11 (= référence). Revue : contracts.md aligné, test direct de cache_key. Une reprise d'un run d'avant v0.2.0 est refusée (catalog_fingerprint change) : relancer de zéro. 1177 tests verts. |
| 8.2 | — | 11:39 | e43fdbd | ~0,0103 $ | cost_eur_real sans les spans fake, colonne cost_eur_fake ; SM-4 réel vert (cost_eur_real = Registre converti). Revue : possession des spans local à énergie factice classée fictive (cost_eur_real = 0 exactement en Faux LLM), Faux LLM pur détecté par l'absence de span réel, coût par requête et point mort sur le fictif, mention du fictif exclu en run mixte. 1181 tests verts. Arbitrage non bloquant soumis. |
| 8.5 | — | 12:20 | 6a8f65c | 0 $ | Tests 1.8 (0,90 + 0,90 sous 2,00, soldes vérifiés, mois suivant par horloge injectée ; ancien test à 3,00 supprimé) et 1.4 (3,00 et 0,03 sur le Catalogue livré) ; relevé de prix recopié, aucun écart, Catalogue inchangé. 1181 tests verts. |
| 8.3 | — | 12:41 | 36efec0 | 0 $ | completed_with_errors (aucune ok, Critère sans verdict, taux d'error > max_error_rate 0,2), causes au manifeste avec taux réel, code 1 ou 0 avec --tolerer-erreurs (all_failed compris, AC 2), budget_exceeded/3 prime, bandeau du Rapport, reprise des error et Critères sans verdict. 1195 tests verts. Points non bloquants soumis (spec 8-3). |
| 8.7 | — | 13:12 | 76d6be3 | 0 $ | Option (c), décision d'Anaël : select_model granite4.2:3b pour PageIndex, sans repeat_penalty ; options Ollama dans la clé du Cache. Réel : mini-cpu completed, 8/8 ok, 56 verdicts, 0 sortie tronquée, 560 s. |
| 8.6 | — | 13:58 | fa334b9 | 0 $ | windows_emi suit la charge (repos ~44 W, charge ~107 W, 4 processus, deux répétitions, écart ≈ 1 %) → measured ; wl.energy_source partout, nvml prioritaire, contracts.md §6 aligné ; part RAM estimée par formule signalée au Rapport. 1227 tests verts. Point non bloquant : méthode mixed ? |
| 8.9 | — | 16:52 | 862a16e (code), 3d67958 (paquet) | 0 $ | wl annotations exporter (--ecraser, contexte des Juges, noms contrôlés), section Calibration des Juges au Rapport ; paquet réel : corpora/minicorpus/annotations/anael.yaml, 40 Réponses du run 8.8, 0 double. |

## Reports entre stories

À transmettre au dev-story de la story cible.

- **8.5 (relevé de prix, orchestrateur, 2026-10-18)** : https://platform.claude.com/docs/en/about-claude/pricing (sections « Model pricing », « Batch processing », « Long context pricing »). Haiku 5.5 jusqu'à 100 000 tokens de prompt : entrée 0,10, écriture cache 5 min 0,125, 1 h 0,20, lecture 0,01, sortie 0,50 $/Mtok ; au-delà (« over 100,000 tokens ») : 0,50 / 0,625 / 1 / 0,05 / 2,50, soit ×5 sur tous les postes ; batch 0,05/0,25 → 0,25/1,25 (×5). « A request's prompt length counts all of its input tokens, including cache reads and cache writes. Each request is priced on its own. » → concorde avec `defaults/models.yaml` (`above_prompt_tokens: 100000`, `multiplier: "5"`). Seuil strict (« over ») : `config/catalog.py:52` applique bien `>`. Aucun écart : rien à soumettre à Anaël.

## Journal

- 2026-10-18 : artefacts de planification commités (`ab2181f`) ; `epic-8-context.md` compilé ; démarrage du run.
- 2026-10-18 : relevé de prix de 8.5 fait (voir Reports), concordant.
- 2026-10-18 : Anaël : « Ollama est maintenant disponible pour toi ». `/api/version` 0.40.5 ; `/api/tags` : minicpm5:1b-q4_k_m, granite4.2:3b, qwen3.5:4b, nomic-embed-text présents ; `/api/ps` vide. Plus d'attente Ollama : 8.4 (vérif. réelle), 8.7 et 8.8 s'enchaînent dans l'ordre.
- 2026-10-18 : Anaël autorise la parallélisation si elle est sans risque. Deux voies : A (sans réseau) 8.1 → 8.2 → 8.3 → 8.5 → 8.6 → code 8.9 ; B (Ollama) 8.4 → 8.7. 8.8 attend 8.1 à 8.7 intégrées. Intégration séquentielle sur `main` (rebase, suite complète, contrôle rapide). Pas de mesure de charge 8.6 pendant un run Ollama ; latences de la voie B indicatives si la voie A teste en même temps. Référence de 8.4 : 3e série du 2026-10-18, mini-cpu 7 ok / 1 error, 49 lignes de verdicts, ~9 min 30.
- 2026-10-18 12:41 : Anaël choisit l'option (c) pour 8.7. 8.3 intégrée. Anaël reprend Ollama pour un autre usage : plus aucun appel Ollama jusqu'à un nouveau « Ollama disponible ». Avance sans Ollama : 8.7 (c) côté code, code de 8.9.
- 2026-10-18 12:55 : « Ollama disponible ». Suite : vérif. réelle 8.7 (c) après intégration, mesure 8.6 quand la machine est calme, puis 8.8 et paquet 8.9.
- 2026-10-18 13:01 : code de 8.7 option (c) intégré (76d6be3, 1201 tests verts) ; vérification réelle mini-cpu lancée.
- 2026-10-18 13:12 : vérif. réelle 8.7 (c) faite (run 20261018-110209-a8262d), 8.7 close ; Ollama rendu à Anaël ; 8.6 lancée.
- 2026-10-18 13:18 : code de 8.9 approuvé (34d03df, wl annotations exporter avec --ecraser, contexte des Juges dans le paquet, section Calibration des Juges) ; intégration différée après la mesure de 8.6 (pas de suite complète pendant la mesure). Report : longueur du paquet (~8 000 tokens par Réponse) et tirage non stratifié, à voir avec Anaël sur le paquet réel.
- 2026-10-18 13:22 : à la demande d'Anaël, topic GitHub repassé de status-test à status-dev pendant le lot v0.2.0 ; à remettre à status-test avec la release v0.2.0.
- 2026-10-18 13:24 : « Ollama de nouveau disponible ». 8.8 démarre après la mesure de 8.6 et l'intégration de 8.6 et 8.9.
- 2026-10-18 13:44 : code de 8.9 intégré (862a16e, 1216 tests verts) ; reste le paquet réel depuis le run_id de 8.8.
- 2026-10-18 13:59 : 8.8 lancée : WL_HOME neuf C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0 (hors dépôt), mini-cpu (19 Questions) puis lazy-seuil-cpu ; RAM libre et ollama ps relevés chaque minute dans ram.log. Sorties : mini-cpu.out, lazy-seuil-cpu.out.
- 2026-10-18 14:42 : script des runs 8.8 arrêté par Claude Code (mémoire système critique, ~1,3 Go libres : Juges granite + qwen 9,3 Go à 32k sans GPU). Le processus wl run mini-cpu (run 20261018-115941-a2a512) a survécu : 76 Réponses produites, Juges en cours. Anaël : le laisser finir. lazy-seuil-cpu non lancé ; ne rien relancer sans son accord.
- 2026-10-18 15:42 : run 8.8 mini-cpu terminé : completed_with_errors, 76/76 Réponses ok, 55 Critères sans verdict (bm25 18, rag-naif 17, raptor 17, pageindex 3). Cause : 48 sorties de Juges tronquées au budget components/judges/llm.py:22 (120 × Critères + 60 : 300 ou 420 tokens ; granite 44, qwen 4 ; sorties conformes jusqu'à 414). Défaut 8.6 révélé : wl.energy_source=nvml sur 309 spans alors que le GPU est désactivé (1 seul windows_emi), 156 unknown. Correctif fix-8-8 lancé (sans Ollama), puis wl run --reprendre.
- 2026-10-18 15:46 : Anaël donne son accord pour le balayage lazy-seuil-cpu ; lancé après le correctif fix-8-8 (sinon Juges tronqués), avec arrêt si RAM libre < 3 Go. OLLAMA_MAX_LOADED_MODELS est une variable du serveur : effective seulement si Anaël relance Ollama avec. Ordre : fix → reprise mini-cpu → paquet 8.9 → balayage.
- 2026-10-18 16:13 : fix-8-8 intégré (360ea0f) : budget des Juges 200 × Critères + 100 (borné au Catalogue), GPU non demandé retiré du tracker codecarbon (vérifié en réel : gpu_energy 0, windows_emi). 1232 tests verts. Suite : reprise du run 8.8.
- 2026-10-18 16:33 : reprise mini-cpu terminée (16:31) : 7 Critères sans verdict restants (qwen q-044 rag-naif et raptor, granite q-017 pageindex ; q-044 a un Ancrage de référence non résolu). Paquet 8.9 : corpora/minicorpus/annotations/anael.yaml (40 Réponses, 0 double). Le premier script (arrêté pour mémoire) avait lancé seul lazy-seuil-cpu (run 20261018-131800-492c48, ancien budget des Juges) ; reprise de ce run en 39 s → completed, 57 Réponses. Processus orphelins arrêtés. Ollama rendu à Anaël (ps vide).
- 2026-10-18 16:52 : synthèse 8.8 intégrée (c218821, série verifications-reelles-2026-10-18-v0.2.0.md) : mini-cpu 76/76 ok, qualité 0,26 à 0,37 (IC recouvrants), 7 Critères sans verdict ; balayage non discriminant. 8.9 done. 8.8 en review en attente d'Anaël. 8.10 non touchée. Run arrêté, main poussé.
