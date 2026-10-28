"""Operational but unqualified format-v1 placement defaults.

These values are the exact historical E021--E023c stand-ins previously used
only by synthetic qualification.  Making them operational does not turn them
into production evidence: the runtime marks the resulting pipeline
provisional and warns on every run until the outstanding physical/null and
complete-domain yield duties are frozen.
"""
from __future__ import annotations

from .model import V1_WHOLEWORD_RIVAL_GATE
from .policy import PlacementBudgetPolicy


_PROVISIONAL_ALPHA = 1e-3
_PROVISIONAL_CHANNEL_BER_ENVELOPE = 0.08


PROVISIONAL_V1_PLACEMENT_POLICY = PlacementBudgetPolicy(
    qualification_id=(
        "candidate/holo-v1-e026+e022/requires-physical-null"),
    familywise_false_accept=_PROVISIONAL_ALPHA,
    max_true_error_rate=_PROVISIONAL_CHANNEL_BER_ENVELOPE,
    gate=V1_WHOLEWORD_RIVAL_GATE,
    support_margin_sites=0,
    word_familywise_false_accept=_PROVISIONAL_ALPHA,
    word_qualification_id=(
        "holo-v1/e022-single-word-multi-slot-union-bound"),
)

V1_PRODUCTION_QUALIFICATION_NOTES = (
    "the v1 physical/null false-accept gate, channel-BER envelope, and "
    "support safety margin still require frozen qualification",
    "the 0.176 complete-domain rival refusal was diagnosed as a "
    "parity-concentrated cross-page alias and the v0.30 whole-word rival "
    "gate restores the d=27 floor (synthetically verified); real-capture "
    "full-domain yield and resource profile remain unqualified",
)


__all__ = [
    "PROVISIONAL_V1_PLACEMENT_POLICY",
    "V1_PRODUCTION_QUALIFICATION_NOTES",
]
