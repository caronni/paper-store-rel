"""typist: OUR encoder for TYPED-STREAM v0 (not typed by the finder).

  python3 typist.py enc [--region] CODE.py [CODE2.py ...] [--data BIN] > lines.txt
  python3 typist.py dec lines.txt          (verify + print the decoded code)

enc: the code files are concatenated in order (each ends in a newline),
encoded ('\\n' -> '~', each leading 4-space indent unit -> '@', remainder
spaces kept), cut into 64-char payloads, each followed by its 3-char check;
then, if --data is given, the payload line '###' and the data as base-32
(5 bits/char, MSB first, last char zero-padded), 64 chars per line; then
'RUN'.  --region types only the text between the lines '# BEGIN <X>' and
'# END <X>' of each file (the markers themselves are not typed).
Refuses '~', '@', '###', tabs, CR, trailing spaces and any character
outside printable ASCII in code.  Stdlib only, deterministic."""
import sys

ALPHA = '0123456789abcdefghijklmnopqrstuv'
WIDTH = 64


def check(n, payload):
    """The TYPED-STREAM check of payload as stream line n (1-based)."""
    c = (n * 1000003 + sum((i + 1) * ord(ch) for i, ch in enumerate(payload))) % 32768
    return ALPHA[c >> 10] + ALPHA[c >> 5 & 31] + ALPHA[c & 31]


def region(src):
    """Text between '# BEGIN X' and '# END X' marker lines (exclusive)."""
    out, on = [], False
    for ln in src.split('\n'):
        s = ln.strip()
        if s.startswith('# BEGIN '):
            on = True
        elif s.startswith('# END '):
            on = False
        elif on:
            out.append(ln + '\n')
    if not out:
        raise ValueError('no # BEGIN / # END region')
    return ''.join(out)


def encode_code(src):
    """Python source -> typed stream text. Raises ValueError on anything the
    stream cannot carry."""
    if not src.endswith('\n'):
        src += '\n'
    if '###' in src:
        raise ValueError("source contains '###' (the section separator)")
    out = []
    for k, ln in enumerate(src[:-1].split('\n'), 1):
        for bad, why in (('~', "'~'"), ('@', "'@'"), ('\t', 'a tab'), ('\r', 'a CR')):
            if bad in ln:
                raise ValueError(f'source line {k} contains {why}')
        if any(not (32 <= ord(ch) < 127) for ch in ln):
            raise ValueError(f'source line {k} has a non-printable-ASCII char')
        if ln != ln.rstrip(' '):
            raise ValueError(f'source line {k} has trailing spaces')
        ind = len(ln) - len(ln.lstrip(' '))
        out.append('@' * (ind // 4) + ' ' * (ind % 4) + ln[ind:])
    return '~'.join(out) + '~'


def decode_code(text):
    """Inverse of encode_code: exactly what checker.py writes to a.py."""
    return text.replace('~', '\n').replace('@', '    ')


def b32(data):
    bits = ''.join(f'{b:08b}' for b in data)
    bits += '0' * (-len(bits) % 5)
    return ''.join(ALPHA[int(bits[i:i + 5], 2)] for i in range(0, len(bits), 5))


def unb32(chars, nbytes):
    bits = ''.join(f'{ALPHA.index(ch):05b}' for ch in chars)
    return int(bits[:8 * nbytes] or '0', 2).to_bytes(nbytes, 'big')


def cut(text):
    return [text[i:i + WIDTH] for i in range(0, len(text), WIDTH)]


def encode(code_text, data=None):
    """Typed stream text (already encoded) + optional data bytes -> the list
    of lines the finder types, checks appended, ending in 'RUN'."""
    payloads = cut(code_text)
    if data is not None:
        payloads += ['###'] + cut(b32(data))
    return [p + check(n, p) for n, p in enumerate(payloads, 1)] + ['RUN']


def decode_lines(lines):
    """Lines -> (code typed text, data base-32 text or None).  Every line
    must carry its correct check; raises ValueError otherwise."""
    if not lines or lines[-1] != 'RUN':
        raise ValueError("stream must end with 'RUN'")
    ps = []
    for n, ln in enumerate(lines[:-1], 1):
        if len(ln) < 3 or ln[-3:] != check(n, ln[:-3]) or len(ln) > WIDTH + 3:
            raise ValueError(f'line {n} fails its check')
        ps.append(ln[:-3])
    sec = ''.join(ps).split('###')
    return sec[0], (sec[1] if len(sec) > 1 else None)


def main(argv):
    if argv[:1] == ['dec']:
        code, data = decode_lines(open(argv[1]).read().split('\n')[:-1])
        sys.stdout.write(decode_code(code))
        if data is not None:
            sys.stderr.write(f'data section: {len(data)} base-32 chars\n')
        return 0
    if argv[:1] != ['enc']:
        sys.stderr.write(__doc__)
        return 2
    args, data, reg = argv[1:], None, False
    if '--data' in args:
        k = args.index('--data')
        data = open(args[k + 1], 'rb').read()
        args = args[:k] + args[k + 2:]
    if '--region' in args:
        reg = True
        args.remove('--region')
    src = ''
    for f in args:
        s = open(f).read()
        s = region(s) if reg else s
        src += s if s.endswith('\n') else s + '\n'
    lines = encode(encode_code(src), data)
    sys.stdout.write('\n'.join(lines) + '\n')
    sys.stderr.write(f'{len(lines)} lines ({len(lines) - 1} checked + RUN), '
                     f'{sum(len(x) for x in lines)} chars\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
