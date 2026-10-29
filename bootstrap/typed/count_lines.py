"""Canonical line counter for a stage-0 decoder. Usage: python3 count_lines.py dec.py
Counts physical lines between '# BEGIN DECODER' and '# END DECODER' that are not blank
and not comment-only. Flags violations of the typed-subset rules."""
import sys, re, ast
src = open(sys.argv[1]).read()
body = src.split("# BEGIN DECODER", 1)[1].split("# END DECODER", 1)[0]
lines = [l for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
viol = []
for i, l in enumerate(lines, 1):
    if len(l) > 80: viol.append(f"line {i}: {len(l)} chars > 80")
    code = l.split("#")[0]
    if ";" in code and "'" not in code and '"' not in code: viol.append(f"line {i}: semicolon")
tree = ast.parse(body)
for n in ast.walk(tree):
    if isinstance(n, (ast.Import, ast.ImportFrom)): viol.append(f"import at line {n.lineno}")
    if isinstance(n, ast.Constant) and isinstance(n.value, float): viol.append(f"float literal at line {n.lineno}")
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div): viol.append(f"true division '/' at line {n.lineno}")
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("hash", "eval", "exec", "open", "__import__", "float", "round"):
        viol.append(f"call to {n.func.id}() at line {n.lineno}")
print(f"lines={len(lines)} chars={sum(len(l) for l in lines)}")
for v in viol: print("VIOLATION:", v)
sys.exit(1 if viol else 0)
