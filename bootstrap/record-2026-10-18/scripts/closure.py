import ast, sys, os, collections
ROOT = sys.argv[1]; SRC = os.path.join(ROOT, "src")
def modfile(name):
    p = os.path.join(SRC, *name.split("."))
    if os.path.isfile(p + ".py"): return p + ".py"
    if os.path.isfile(os.path.join(p, "__init__.py")): return os.path.join(p, "__init__.py")
    return None
def modname(path):
    rel = os.path.relpath(path, SRC)[:-3].replace(os.sep, ".")
    return rel[:-9] if rel.endswith(".__init__") else rel
def imports(path):
    tree = ast.parse(open(path).read())
    me = modname(path); pkg = me if path.endswith("__init__.py") else me.rpartition(".")[0]
    out = set(); ext = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names: out.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = pkg
                for _ in range(n.level - 1): base = base.rpartition(".")[0]
                m = base + ("." + n.module if n.module else "")
            else: m = n.module
            out.add(m)
            for a in n.names: out.add(m + "." + a.name)
    return out
seeds = []
for d, _, fs in os.walk(os.path.join(SRC, "holo", "receiver")):
    if "/tests" in d or d.endswith("/tests"): continue
    seeds += [os.path.join(d, f) for f in fs if f.endswith(".py")]
seen = set(); stack = list(seeds); ext = collections.Counter()
while stack:
    f = stack.pop()
    if f in seen: continue
    seen.add(f)
    # parents' __init__ are executed too
    m = modname(f).split(".")
    for i in range(1, len(m)):
        pf = modfile(".".join(m[:i]))
        if pf and pf not in seen: stack.append(pf)
    for name in imports(f):
        mf = modfile(name)
        if mf: stack.append(mf)
        elif not modfile(name.rpartition(".")[0] or "x") : ext[name.split(".")[0]] += 1
for f in sorted(seen): print(os.path.relpath(f, ROOT))
print("EXT", sorted(ext), file=sys.stderr)
