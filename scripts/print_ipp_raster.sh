#!/usr/bin/env bash
# Print a prepared RASTER job (image/urf or image/pwg-raster) over IPP, bypassing
# CUPS, with scaling OFF. The 2026-09-16 Xerox VersaLink C7130 footing `ipp-urf`:
# that engine exposes no PostScript and no port 9100 — only IPP (631) with
# PDF/JPEG/URF/PWG at a fixed 600 dpi, so the raster IS the dot pattern and the
# printer's RIP never sees a page description. Rasters come from ghostscript
# (`-sDEVICE=urfgray -r600`) or straight from page000_gt.npy.
# SAFETY: interactive confirmation required; Claude Code must ask the user first
# (.claude/rules/hardware.md). Refuses without a tty, like print_plane.sh.
set -euo pipefail
FILE="${1:?usage: print_ipp_raster.sh <job.urf|job.pwg|job.pdf> <printer-host> [media] [color-mode]}"
HOST="${2:?usage: print_ipp_raster.sh <job.urf|job.pwg|job.pdf> <printer-host> [media] [color-mode]}"
MEDIA="${3:-na_letter_8.5x11in}"       # or iso_a4_210x297mm (must be loaded)
COLOR="${4:-monochrome}"               # monochrome | color — a cmyk_pdf.py file MUST be sent with `color`
QUALITY="${PRINT_QUALITY:-4}"          # env: 4 normal | 5 high  (IPP print-quality)
OPTIMIZE="${CONTENT_OPTIMIZE:-}"       # env: auto | graphics | text | text-and-graphics (IPP print-content-optimize); empty = not sent
case "$FILE" in *cmyk*|*color*|*probe-page*) [ "$COLOR" = "color" ] || { echo "refusing: $FILE is a colour job; pass 'color' as the 4th argument" >&2; exit 2; } ;; esac
case "$FILE" in
  *.urf) FILETYPE=image/urf ;;
  *.pwg) FILETYPE=image/pwg-raster ;;      # pwg_raster.py (cmyk_8 / sgray_8 / black_1)
  *.pdf) FILETYPE=application/pdf ;;      # ONLY the full-page 1-bit image PDFs of pdf_bilevel.py (K mask) / cmyk_pdf.py (DeviceCMYK)
  *) echo "refusing: $FILE is not a .urf/.pwg raster or a bilevel .pdf" >&2; exit 2 ;;
esac
[ -t 0 ] || { echo "refusing: interactive confirmation requires a terminal" >&2; exit 2; }
URI="ipps://$HOST/ipp/print"
read -r -p "Physically print '$FILE' ($FILETYPE, media $MEDIA, $COLOR, quality $QUALITY${OPTIMIZE:+, optimize $OPTIMIZE}, print-scaling none) via $URI? [yes/NO] " ok
[ "$ok" = "yes" ] || { echo "aborted"; exit 1; }
shasum -a 256 "$FILE"
# the printer's TLS certificate is self-signed: trust it for this call only,
# via a throwaway HOME so the user's ~/.cups/client.conf is never touched
TMPHOME="$(mktemp -d)"; trap 'rm -rf "$TMPHOME"' EXIT
mkdir -p "$TMPHOME/.cups"; printf 'AllowAnyCert Yes\nValidateCerts No\n' > "$TMPHOME/.cups/client.conf"
TEST="$TMPHOME/print-raster.test"
{
cat <<'T'
{
	NAME "Print raster with scaling off"
	OPERATION Print-Job
	GROUP operation-attributes-tag
	ATTR charset attributes-charset utf-8
	ATTR language attributes-natural-language en
	ATTR uri printer-uri $uri
	ATTR name requesting-user-name $user
	ATTR mimeMediaType document-format $filetype
	GROUP job-attributes-tag
	ATTR integer copies 1
	ATTR keyword media $media
	ATTR keyword print-scaling none
	ATTR keyword print-color-mode $color
	ATTR enum print-quality $quality
	ATTR keyword sides one-sided
T
[ -n "$OPTIMIZE" ] && printf '\tATTR keyword print-content-optimize %s\n' "$OPTIMIZE"
cat <<'T'
	FILE $filename
	STATUS successful-ok
	STATUS successful-ok-ignored-or-substituted-attributes
	EXPECT job-id
	EXPECT job-uri
}
T
} > "$TEST"
HOME="$TMPHOME" ipptool -tv -T 60 -f "$FILE" -d "filetype=$FILETYPE" -d "media=$MEDIA" -d "color=$COLOR" -d "quality=$QUALITY" "$URI" "$TEST" || { echo "IPP submission FAILED (see above) — nothing was printed" >&2; exit 1; }
echo "submitted $(wc -c < "$FILE" | tr -d ' ') bytes of $FILETYPE to $URI (media $MEDIA, scaling none)"
