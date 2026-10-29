"""Line counter and typed-subset audit for the reader (adapted from
typed/count_lines.py).  Usage: python3 count_reader.py reader.py

The typed text is the region between '# BEGIN READER' and '# END READER'
minus every block of lines from '#--- shared with the loader (not typed) ---'
to '#--- end shared ---' (the definitions the loader provides; make_typed.py
drops them the same way).  Counts its non-blank, non-comment physical lines.
Flags: lines > 72 chars, ';', '~', an '@' outside a string literal (the
operator or a decorator; inside a literal it is allowed: the owner's ruling
of 2026-10-23, "yes, b.py may include the literal @" -- the ban on '@'
anywhere was the hand-typed a.py's, the typist era's indent mark), imports,
float or complex literals,
true division, any call to a builtin outside the typed subset (open() and
input() are allowed: the reader's spec needs them), and -- the loader
interface -- any module-level binding of the reserved names d, q, k
(they are the loader's: d = the cm2 v2 decoder, q = the alphabet, k = the
Horner line check).  Reports whether the token N2 and the write of c.py
(the reader's output, ruling 34) are present."""
import ast
import builtins
import io
import sys
import tokenize

SHARED_BEGIN = '#--- shared with the loader (not typed) ---'
SHARED_END = '#--- end shared ---'
RESERVED = {'d', 'q', 'k'}


def typed_text(src):
    if '# BEGIN READER\n' in src:      # as loader/make_typed.py's region()
        src = src.split('# BEGIN READER\n', 1)[1].split('# END READER', 1)[0]
    out, inside = [], False
    for t in src.splitlines(keepends=True):
        bare = t.rstrip('\r\n')
        if bare == SHARED_BEGIN:
            inside = True
        elif bare == SHARED_END:
            inside = False
        elif not inside:
            out.append(t)
    return ''.join(out)


def module_bindings(tree):
    """Names bound at module level (assignments, defs, for targets, ...),
    not inside functions."""
    names = []

    def targets(t):
        if isinstance(t, ast.Name):
            names.append((t.id, t.lineno))
        elif isinstance(t, (ast.Tuple, ast.List)):
            for x in t.elts:
                targets(x)
        elif isinstance(t, ast.Starred):
            targets(t.value)

    def walk(body):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                names.append((n.name, n.lineno))
                continue
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    targets(t)
            elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
                targets(n.target)
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                targets(n.target)
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for it in n.items:
                    if it.optional_vars is not None:
                        targets(it.optional_vars)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    names.append(((a.asname or a.name).split('.')[0], n.lineno))
            for f in ('body', 'orelse', 'finalbody'):
                if hasattr(n, f) and isinstance(getattr(n, f), list):
                    walk(getattr(n, f))
            if isinstance(n, ast.Try):
                for hnd in n.handlers:
                    walk(hnd.body)
        for n in ast.walk(ast.Module(body, [])):
            if isinstance(n, ast.NamedExpr):
                targets(n.target)
    walk(tree.body)
    return names


def main():
    src = open(sys.argv[1]).read()
    body = typed_text(src)
    numbered = [(k, l) for k, l in enumerate(body.splitlines(), 1)
                if l.strip() and not l.strip().startswith("#")]
    lines = [l for k, l in numbered]
    literal = {tokenize.STRING} | {getattr(tokenize, x) for x in ('FSTRING_MIDDLE', 'TSTRING_MIDDLE')
                                   if hasattr(tokenize, x)}
    at = {r for t in tokenize.generate_tokens(io.StringIO(body).readline)
          if '@' in t.string and t.type not in literal for r in range(t.start[0], t.end[0] + 1)}
    OK = {"input", "open", "print", "len", "range", "sum", "min", "max", "abs",
          "enumerate", "sorted", "int", "ord", "chr", "bytes", "bytearray", "str"}
    viol = []
    for i, (k, l) in enumerate(numbered, 1):
        if len(l) > 72:
            viol.append(f"line {i}: {len(l)} chars > 72")
        if "~" in l or k in at:
            viol.append(f"line {i}: '~' or '@' (outside a string literal)")
        if ";" in l.split("#")[0]:
            viol.append(f"line {i}: semicolon")
    tree = ast.parse(body)
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            viol.append(f"import at {n.lineno}")
        if isinstance(n, ast.Constant) and isinstance(n.value, (float, complex)):
            viol.append(f"float/complex literal at {n.lineno}")
        if isinstance(n, (ast.BinOp, ast.AugAssign)) and isinstance(n.op, ast.Div):
            viol.append(f"true division at {n.lineno}")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            f = n.func.id
            if hasattr(builtins, f) and f not in OK:
                viol.append(f"builtin {f}() at {n.lineno}")
    for name, ln in module_bindings(tree):
        if name in RESERVED:
            viol.append(f"reserved name {name!r} bound at module level, line {ln}")
    n2 = sum(1 for t in tokenize.generate_tokens(io.StringIO(body).readline)
             if t.type == tokenize.NAME and t.string == 'N2')
    print(f"lines={len(lines)} chars={sum(len(l) for l in lines)} "
          f"stripped={sum(len(l.strip()) for l in lines)} longest={max(map(len, lines))} "
          f"N2 tokens={n2} writes c.py={'c.py' in body}")
    for v in viol:
        print("VIOLATION:", v)
    sys.exit(1 if viol else 0)


if __name__ == '__main__':
    main()
