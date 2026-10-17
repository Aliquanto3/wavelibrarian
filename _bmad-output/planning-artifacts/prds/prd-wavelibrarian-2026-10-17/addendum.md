# Addendum au PRD WaveLibrarian : éléments pour l'architecture

Choix techniques et contexte qui ne relèvent pas des exigences, à arbitrer dans `bmad-architecture`.

## Orientations techniques issues du cadrage

- **Socle** : code minimal maison autour d'interfaces, avec Optuna pour l'optimiseur (D4). Les frameworks (LlamaIndex, Haystack) entrent seulement comme Architectures comparées.
- **Passerelle de modèles** : un format unique compatible OpenAI via LiteLLM, vers Anthropic, Ollama, Azure AI Foundry, Bedrock, Vertex, vLLM et llama.cpp.
- **Ingestion** : Docling pour le PDF, comparé plus tard à un VLM (niveau 4).
- **Base vectorielle** : pgvector comme dénominateur commun en cloud. En local au MVP, une base embarquée sans serveur (sqlite-vec ou LanceDB) ; à trancher.
- **Traces** : OpenTelemetry, avec un export fichier par défaut ; Langfuse, Phoenix et les autres outils viendront ensuite comme Composants comparés.
- **Énergie** : CodeCarbon en local et EcoLogits pour les API, en reprenant la méthode du banc SLM et du harnais WaveStack (FinOps : prix datés, plafond par séance, décomposition « sans optimisation / coût réel / part du cache »).
- **Infrastructure** : conteneurs et OpenTofu, un module par fournisseur `[Post-MVP]`.
- **Mutualisation (D14)** : partager le harnais d'évaluation et la mesure d'énergie avec le moteur de recherche local et le banc SLM, pas le code applicatif.

## Environnement de la machine de référence (relevé du 2026-10-17)

- GPU NVIDIA RTX 3050, 8 Go.
- Ollama installé, avec des SLM déjà téléchargés : qwen3.5:4b, ministral-3:3b et 8b, gemma4-ud:12b, granite4.2:3b, llama3.2:3b, olmo-3:7b, nemotron-3-nano:4b, minicpm5, lfm2.5 et d'autres. Aucun modèle d'embedding n'est installé.
- llama-server (llama.cpp) disponible.
- Pas de `ANTHROPIC_API_KEY` dans l'environnement : la clé sera dans `.env`, ignoré par git.

## Composition du panel au MVP (FR-37, PRD §7.3)

Familles disponibles sans Foundry : Claude (Haiku 5.5, API), Qwen, Mistral, Gemma, IBM Granite, Llama, OLMo, MiniCPM (local). Pendant le run autonome, le GPU est occupé par un autre banc de SLM : profil CPU, avec de très petits modèles (minicpm5:1b, minicpm5:2b, granite4.2:3b) et `num_gpu: 0` côté Ollama. Le profil GPU (qwen3.5:4b, ministral-3:8b, bge-m3) sera utilisé ensuite. Les juges locaux de 1 à 3 milliards de paramètres seront faibles. C'est attendu : la calibration doit justement le mesurer, et au MVP ils servent surtout à valider la chaîne.

## Contraintes du premier run autonome

- Budget : 5 $ sur l'API Anthropic, arrêt automatique.
- Ordre des Architectures : naïf, hybride, HyDE, CRAG, CAG, RAPTOR, PageIndex, LLM Wiki, agentique, GraphRAG et variantes.
- Enchaînement par story : `agent-cost-kit:dev-story` → `second-avis` → `reviewer` → intégration.
