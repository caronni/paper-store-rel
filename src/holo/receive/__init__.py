"""Format-v1 Track-3 read-back implementation.

The package surface is deliberately small. ``run_discovery_receive`` is the
default receiver-wide entry; ``run_receive`` remains the exact-row
E021--E023c harness. The production composition uses explicitly provisional
historical placement constants and warns on every run until the v1 placement
gate is production-frozen. Other exports are the authenticated raster and
pure certification/closure seams useful to embedders. Numerical stage
decisions and implementation kernels remain in their owning modules.
"""

from .fountain_close import CloseResult, close_volume
from .discovery import (
    DiscoveryReceiveRequest,
    DiscoveryReceiveResult,
    run_discovery_receive,
)
from .runtime import (
    ProvisionalReceiverWarning,
    ReceivePipeline,
    ReceiveRequest,
    ReceiveResult,
    ReceiverQualificationStatus,
    run_receive,
)
from .scan import Raster, SourceId, open_capture
from .payload import attempt_k_tile
from .records import CertificateStore
from .types import CaptureInput

__all__ = [
    "CaptureInput",
    "CertificateStore",
    "CloseResult",
    "DiscoveryReceiveRequest",
    "DiscoveryReceiveResult",
    "ProvisionalReceiverWarning",
    "Raster",
    "ReceivePipeline",
    "ReceiveRequest",
    "ReceiveResult",
    "ReceiverQualificationStatus",
    "SourceId",
    "attempt_k_tile",
    "close_volume",
    "open_capture",
    "run_discovery_receive",
    "run_receive",
]
