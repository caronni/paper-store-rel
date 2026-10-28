"""Declarative, content-identified E022 attempt-budget policy.

The placement policy is data, not a caller-supplied function. Its durable
identity is derived from every result-affecting field, so changing a gate,
error envelope, support margin, or false-accept declaration necessarily
changes the receiver policy recorded by the session.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ...format.descriptor import FormatSpec
from ..words import WordAttemptBudget, stage_a_hypotheses
from .model import (
    AttemptBudget,
    MAX_LOWER_HINTS,
    PlacementBudgets,
    PlacementConfig,
    PlacementGate,
)
from .search import hypothesis_count


_POLICY_SCHEMA = "holo/e022-placement-budget-policy/v1"
_ENVELOPE_SCHEMA = "holo/e022-receiver-wide-domain/v1"


def _probability(label: str, value: float) -> float:
    result = float(value)
    if not 0.0 < result < 1.0 or not math.isfinite(result):
        raise ValueError(f"{label} must be finite and in (0, 1)")
    return result


def _identity(label: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty")
    return value


@dataclass(frozen=True, slots=True)
class PlacementDomainEnvelope:
    """Frozen receiver-wide hypothesis counts shared by every row branch.

    A branch still searches only its own complete row domain.  The larger
    counts here make every branch's admission record account for the union of
    all rows which the discovery receiver promised to trial.
    """

    row_ids: tuple[str, ...]
    cold_hypotheses: int
    local_hypotheses: int
    lower_hypotheses: int
    word_hypotheses: int

    def __post_init__(self) -> None:
        if (not self.row_ids or tuple(sorted(self.row_ids)) != self.row_ids
                or len(set(self.row_ids)) != len(self.row_ids)):
            raise ValueError(
                "receiver-wide row ids must be sorted, unique, and non-empty")
        for label, value in (
            ("cold hypotheses", self.cold_hypotheses),
            ("local hypotheses", self.local_hypotheses),
            ("lower hypotheses", self.lower_hypotheses),
            ("word hypotheses", self.word_hypotheses),
        ):
            if (isinstance(value, (bool, np.bool_))
                    or not isinstance(value, (int, np.integer))
                    or int(value) < 1):
                raise ValueError(f"{label} must be a positive integer")

    @property
    def policy_id(self) -> str:
        """Readable page-domain identity (data, not code — G2 allows it)."""
        return (
            "holo/e022-receiver-wide-domain/kiss-v1/"
            f"rows={','.join(self.row_ids)}"
        )

    @classmethod
    def resolve(
        cls,
        rows: tuple[tuple[FormatSpec, tuple[int, ...]], ...],
        config: PlacementConfig,
    ) -> "PlacementDomainEnvelope":
        if not rows:
            raise ValueError("receiver-wide domain needs at least one row")
        if type(config) is not PlacementConfig:
            raise TypeError(
                "receiver-wide domain needs an exact PlacementConfig")
        ordered = tuple(sorted(rows, key=lambda item: item[0].spec_id))
        row_ids = tuple(row.spec_id for row, _pages in ordered)
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("receiver-wide domain repeats a format row")
        patch_shape = (config.window_cells, config.window_cells)
        cold = 0
        for spec, pages in ordered:
            if (not pages or len(set(pages)) != len(pages)
                    or any(type(page) is not int
                           or not 0 <= page < spec.max_pages
                           for page in pages)):
                raise ValueError(
                    f"{spec.spec_id} has an invalid discovery page domain")
            cold += hypothesis_count(
                patch_shape,
                tuple(spec.layout.cells_yx),
                len(pages),
                allow_overhang=config.allow_overhang,
            )
        local_per_row = (2 * config.neighbor_radius_cells + 1) ** 2
        return cls(
            row_ids,
            cold,
            local_per_row * len(ordered),
            local_per_row * MAX_LOWER_HINTS * len(ordered),
            stage_a_hypotheses(patch_shape) * len(ordered),
        )


@dataclass(frozen=True, slots=True)
class PlacementBudgetPolicy:
    """One immutable, auditable placement-admission contract.

    Search-domain sizes remain derived from the actual format, page domain,
    lower-hint inventory, and frozen E022 geometry. The fields here are the
    coupled statistical choices which cannot be inferred from those facts.
    """

    qualification_id: str
    familywise_false_accept: float
    max_true_error_rate: float
    gate: PlacementGate
    support_margin_sites: int
    word_familywise_false_accept: float
    word_qualification_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "qualification_id",
            _identity("placement qualification id", self.qualification_id),
        )
        object.__setattr__(
            self, "familywise_false_accept",
            _probability(
                "placement familywise false-accept target",
                self.familywise_false_accept,
            ),
        )
        error = float(self.max_true_error_rate)
        if not 0.0 <= error < 0.5 or not math.isfinite(error):
            raise ValueError(
                "placement maximum true-error rate must be finite and in "
                "[0, 0.5)"
            )
        object.__setattr__(self, "max_true_error_rate", error)
        if type(self.gate) is not PlacementGate:
            raise TypeError("placement gate must be an exact PlacementGate")
        if (isinstance(self.support_margin_sites, (bool, np.bool_))
                or not isinstance(
                    self.support_margin_sites, (int, np.integer))
                or int(self.support_margin_sites) < 0):
            raise ValueError(
                "placement support margin must be a nonnegative integer"
            )
        object.__setattr__(
            self, "support_margin_sites", int(self.support_margin_sites))
        object.__setattr__(
            self, "word_familywise_false_accept",
            _probability(
                "word familywise false-accept target",
                self.word_familywise_false_accept,
            ),
        )
        object.__setattr__(
            self, "word_qualification_id",
            _identity("word qualification id", self.word_qualification_id),
        )

    @property
    def policy_id(self) -> str:
        """Hand-bumped semantic identity (ground rule G2).

        Constants are data, not identity: editing a numeric field does not
        invalidate existing state by itself. When the placement POLICY
        semantics change, bump the version literal here by hand — that is
        the whole mechanism, exactly as G2 intended.
        """
        return f"{self.qualification_id}/kiss-v1"

    def resolve(
        self,
        spec: FormatSpec,
        pages: tuple[int, ...],
        n_lower: int,
        config: PlacementConfig,
        *,
        domain_envelope: PlacementDomainEnvelope | None = None,
    ) -> tuple[PlacementBudgets, WordAttemptBudget]:
        """Derive complete-domain budgets without truncating any search."""
        if not isinstance(spec, FormatSpec):
            raise TypeError("placement budget needs a FormatSpec")
        if (not pages or len(set(pages)) != len(pages)
                or any(type(page) is not int
                       or not 0 <= page < spec.max_pages for page in pages)):
            raise ValueError("placement budget needs unique legal pages")
        if type(config) is not PlacementConfig:
            raise TypeError("placement budget needs an exact PlacementConfig")
        if (isinstance(n_lower, (bool, np.bool_))
                or not isinstance(n_lower, (int, np.integer))
                or int(n_lower) < 0):
            raise ValueError("lower-hint count must be a nonnegative integer")
        lower_count = int(n_lower)
        if (domain_envelope is not None
                and type(domain_envelope) is not PlacementDomainEnvelope):
            raise TypeError(
                "placement domain envelope must be immutable declarative data")
        patch_shape = (config.window_cells, config.window_cells)
        cold_h = hypothesis_count(
            patch_shape,
            tuple(spec.layout.cells_yx),
            len(pages),
            allow_overhang=config.allow_overhang,
        )
        local_h = (2 * config.neighbor_radius_cells + 1) ** 2
        word_h = stage_a_hypotheses(patch_shape)

        route_domains = {
            "cold": cold_h,
            "local": local_h,
            "lower": local_h * lower_count,
        }
        if domain_envelope is not None:
            if spec.spec_id not in domain_envelope.row_ids:
                raise ValueError(
                    "placement format is outside the receiver-wide domain")
            actual_domains = (
                ("cold", cold_h, domain_envelope.cold_hypotheses),
                ("local", local_h, domain_envelope.local_hypotheses),
                (
                    "lower",
                    local_h * lower_count,
                    domain_envelope.lower_hypotheses,
                ),
                ("word", word_h, domain_envelope.word_hypotheses),
            )
            for route, actual, admitted in actual_domains:
                if admitted < actual:
                    raise ValueError(
                        f"receiver-wide {route} domain does not cover "
                        "the actual format hypotheses")
            route_domains.update({
                "cold": domain_envelope.cold_hypotheses,
                "local": domain_envelope.local_hypotheses,
                "lower": domain_envelope.lower_hypotheses,
            })

        def attempt(route: str) -> AttemptBudget:
            return AttemptBudget(
                route_domains[route],
                self.familywise_false_accept,
                self.max_true_error_rate,
                (
                    f"{self.qualification_id}/{route}"
                    if domain_envelope is None
                    else f"{self.qualification_id}/{route}/"
                         f"{domain_envelope.policy_id}"
                ),
                gate=self.gate,
                support_margin_sites=self.support_margin_sites,
            )

        budgets = PlacementBudgets(
            attempt("cold"),
            attempt("local"),
            (None if lower_count == 0
             else attempt("lower")),
        )
        word = WordAttemptBudget(
            (
                word_h
                if domain_envelope is None
                else domain_envelope.word_hypotheses
            ),
            self.word_familywise_false_accept,
            (
                self.word_qualification_id
                if domain_envelope is None
                else f"{self.word_qualification_id}/"
                     f"{domain_envelope.policy_id}"
            ),
        )
        return budgets, word


__all__ = ["PlacementBudgetPolicy", "PlacementDomainEnvelope"]
