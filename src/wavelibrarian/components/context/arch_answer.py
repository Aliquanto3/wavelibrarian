"""Réexport : `build_arch_answer` vit dans `ports.arch_answer` pour servir aussi le défaut de
`ArchitectureBase.answer_with_context` (couches AD-1)."""

from wavelibrarian.ports.arch_answer import MAX_CONTEXT_TOKENS, build_arch_answer

__all__ = ["MAX_CONTEXT_TOKENS", "build_arch_answer"]
