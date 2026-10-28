"""The work protocol's own minting seam (DESIGN §7/§8, PROVIDERS §8.1).

``ExpansionRequest.mint`` exists because every provider was writing the
same three lines: lift the request's ``arm`` into a :class:`WorkScope`,
name a ``profile``, and stamp ``entry=request.entry`` — a field the
orchestrator overwrites unconditionally with the identical value on the
way back. The pins below are the contract, and all five descriptor sites
in the tree now mint through it (payload, both placement providers, the
toy payload provider, close): the arm travels, the profile is named for
what it is, and the entry stays the orchestrator's to stamp (provenance,
not identity) — which is what ``_provider_kit`` asserted of every
provider's expansion; it was deleted with the measure cleanup, and
history has the driver.

The last two pins are the B1/B14 rulings of 2026-08-12, held as tests so
a re-grown field or a re-widened promise fails instead of drifting.
"""
from __future__ import annotations

import dataclasses

from holo2.core import ResourceKey, WorkScope
from holo2.core.work import (ExpansionRequest, Provider, WorkDescriptor,
                             WorkResult, Worker)

_SUBJECT = ResourceKey("tile", ("0", "12", "40", "K"))


def test_mint_carries_the_requests_arm_and_the_providers_profile() -> None:
    request = ExpansionRequest(entry="payload-scan", selector="C", arm="a2")
    descriptor = request.mint("payload", _SUBJECT, "scan", profile="p7")
    assert descriptor == WorkDescriptor(
        family="payload", subject=_SUBJECT, route="scan",
        scope=WorkScope(arm="a2", profile="p7"))


def test_mint_leaves_the_entry_to_the_orchestrator() -> None:
    """The recipe entry is provenance: a provider cannot write it wrong."""
    request = ExpansionRequest(entry="payload-scan")
    descriptor = request.mint("payload", _SUBJECT, "scan")
    assert descriptor.entry == ""
    assert descriptor.scope == WorkScope()
    # ... and the id, which is what spends and subscriptions key on, is
    # the same whether or not the entry has been stamped yet.
    assert descriptor.work_id == WorkDescriptor(
        family="payload", subject=_SUBJECT, route="scan",
        entry="payload-scan").work_id


def test_two_profiles_of_one_subject_are_two_pieces_of_work() -> None:
    request = ExpansionRequest(entry="e", arm="a1")
    first = request.mint("payload", _SUBJECT, "scan", profile="near")
    second = request.mint("payload", _SUBJECT, "scan", profile="far")
    assert first.work_id != second.work_id


def test_a_result_carries_no_per_fire_prose() -> None:
    """B1 (ruled 2026-08-12): ``note`` is deleted, not deprecated.

    It was written at ~20 sites and read by nothing; the operator's
    decline surface is the outcome vocabulary plus the ledger's counts,
    and a family with something to say to the observer uses ``report``.
    """
    fields = {field.name for field in dataclasses.fields(WorkResult)}
    assert "note" not in fields
    assert fields == {"outcome", "writes", "blobs", "fired", "retire",
                      "report", "exposure"}


def test_the_protocols_stay_runtime_checkable_on_in_tree_evidence() -> None:
    """B14/Q1 (ruled 2026-08-12): genericity is a complexity bound.

    Nothing here is kept for out-of-tree implementors — but both
    ``isinstance`` seams have in-tree readers (the orchestrator's
    worker-or-decline check, the provider contract battery), so the two
    protocols keep their runtime check and this pin says why.
    """
    assert getattr(Worker, "_is_runtime_protocol", False)
    assert getattr(Provider, "_is_runtime_protocol", False)
