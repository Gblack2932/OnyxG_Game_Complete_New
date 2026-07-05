from __future__ import annotations

from typing import Tuple

import constants as cfg


def calculate_rank(score: int, block_signal: int, continues_used: int) -> Tuple[str, str]:
    """Calculate player rank from score + signal gain - continue penalties."""
    rank_score = score
    rank_score += block_signal * cfg.RANK_SIGNAL_MULTIPLIER
    rank_score -= continues_used * cfg.RANK_CONTINUE_PENALTY

    if rank_score >= cfg.RANK_SCORE_S:
        return "S", cfg.RANK_TITLES['S']
    if rank_score >= cfg.RANK_SCORE_A:
        return "A", cfg.RANK_TITLES['A']
    if rank_score >= cfg.RANK_SCORE_B:
        return "B", cfg.RANK_TITLES['B']
    if rank_score >= cfg.RANK_SCORE_C:
        return "C", cfg.RANK_TITLES['C']
    return "D", cfg.RANK_TITLES['D']
