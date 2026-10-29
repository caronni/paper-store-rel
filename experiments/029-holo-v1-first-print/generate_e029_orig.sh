# Historical record of e029: the original heredoc form of generate_e029.py, as run on 2026-08-04 from a
# since-removed worktree of main (printer row hp-m281-ink not yet in the registry, so it is built inline).
# Regenerates the same four artifacts; generate_e029.py is the runnable form.
cd "$REPO"   # 2026-08-04: a worktree of main, since removed
rm -rf scratch/holo-c2-r0700-q07-ink-counting
PYTHONPATH=src env/bin/python - <<'PY'
from pathlib import Path
import hashlib
from holo.devices.registry import PRINTERS, Printer
from holo.devices.profiles import make_spec
from holo.gen.plan import max_payload_bytes
from holo.gen.emit import emit_volume

ink = Printer(
    printer_id='hp-m281-ink',
    name='HP M281 ink-tight (e028 clip experiment)',
    usable_dpi=600,
    media_ids=('a4',),
    payload_safe_margin_mm=4.5,
    margin_footing='e028 2026-08-04 printable clip ~4.15-4.28mm; '
                   '4.5mm request lands next 64-quantum (~4.9mm borders)',
    bw=PRINTERS['hp-m281'].bw,
    color=PRINTERS['hp-m281'].color,
    print_path=PRINTERS['hp-m281'].print_path,
)
PRINTERS['hp-m281-ink'] = ink

spec = make_spec('c2-r0700', 'hp-m281-ink')
q = 0.7
n = max_payload_bytes(spec, q, 1)
payload = bytes(i & 0xFF for i in range(n))
out = Path('scratch/holo-c2-r0700-q07-ink-counting')
vol = emit_volume(spec, payload, q, out, profile=None, printer_id='hp-m281-ink')
(out / 'payload-counting.bin').write_bytes(payload)
print(n, hashlib.sha256(payload).hexdigest(), vol.plan)
PY
