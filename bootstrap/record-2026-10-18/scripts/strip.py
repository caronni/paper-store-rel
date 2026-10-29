import ast, sys, io, tokenize, os
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
for p in sys.stdin.read().split():
    src = open(p).read()
    if p.endswith(".py"):
        tree = ast.parse(src)
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str):
                n.body[0] = ast.Pass() if len(n.body) == 1 else None
                n.body = [b for b in n.body if b is not None]
        src = ast.unparse(tree) + "\n"   # unparse drops comments too
    d = os.path.join(out, os.path.dirname(p)); os.makedirs(d, exist_ok=True)
    open(os.path.join(out, p), "w").write(src)
