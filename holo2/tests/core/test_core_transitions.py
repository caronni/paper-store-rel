"""F-08: core's own family laws — subjects frozen, the close's stated.

``SubjectSpec`` is the fact work identities stand on (M3): parameters
moving under a standing subject id would silently re-aim every
descriptor and spend that names it, so a differing write refuses.
``CloseRecord`` deliberately declares NO transition — its law (OPEN
replaceable, terminal freezes the session) is the commit wall's own
terminality check, one wall, stated once — and that absence is pinned
here so it stays deliberate.
"""
from __future__ import annotations

import pytest

from holo2.core.records import (RECORD_FAMILIES, CloseRecord, SubjectSpec,
                                subject_key)
from holo2.core.registry import RegistryError


def _family(record_type: type):
    return {family.record_type: family for family in RECORD_FAMILIES}[
        record_type]


def test_a_minted_subject_is_frozen() -> None:
    transition = _family(SubjectSpec).transition
    subject = SubjectSpec("unit:0", "placement", parameters=(("d", "1"),))
    key = subject_key("unit:0")
    transition(key, subject, SubjectSpec("unit:0", "placement",
                                         parameters=(("d", "1"),)))
    with pytest.raises(RegistryError, match="frozen"):
        transition(key, subject, SubjectSpec("unit:0", "placement",
                                             parameters=(("d", "2"),)))
    with pytest.raises(RegistryError, match="frozen"):
        transition(key, subject, SubjectSpec("unit:0", "payload",
                                             parameters=(("d", "1"),)))


def test_the_close_declares_no_transition_on_purpose() -> None:
    assert _family(CloseRecord).transition is None


def test_a_close_record_names_one_payload_consistently() -> None:
    """F-13 residue as a construction law (user ruling 2026-08-13).

    payload_sha256 and the bytes_ref content address hash the SAME
    bytes, so a record where they disagree is a state nothing could
    have minted — refused at construction, which is commit AND load.
    With this, the verify=True read at the operator handoff IS the
    payload-sha check; no runtime comparison machinery exists.
    """
    from holo2.core import BlobRef, CloseRecord, CloseStatus

    sha = "ab" * 32
    CloseRecord(CloseStatus.VERIFIED, payload_sha256=sha,
                bytes_ref=BlobRef(sha, 4))
    with pytest.raises(ValueError, match="one payload two ways"):
        CloseRecord(CloseStatus.VERIFIED, payload_sha256=sha,
                    bytes_ref=BlobRef("cd" * 32, 4))
