"""Encoder for the arch-mould decoder named like this file (dec_<same>.py):
derived from the decoder's text by derive.make_encoder (no drift possible).
Copy this file under another enc_<name>.py to serve dec_<name>.py."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive  # noqa: E402

enc = derive.make_encoder(str(HERE / Path(__file__).name.replace("enc_", "dec_")))
