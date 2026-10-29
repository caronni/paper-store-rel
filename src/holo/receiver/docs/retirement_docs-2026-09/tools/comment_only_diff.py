"""Assert that a change to Python files is comment-only.

Usage: env/bin/python src/holo/receiver/docs/retirement_docs-2026-09/tools/comment_only_diff.py <git-base-ref> <file> [<file> ...]

For every file, parses the version at <git-base-ref> and the working-tree
version, strips docstrings (the only prose the AST keeps), and compares the
ASTs. Exit 0 if every file's code is identical, 1 otherwise, naming the file.
Comments never enter the AST, so a comment-only edit compares equal.
"""
import ast, subprocess, sys

def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return tree

def _dump(src: str) -> str:
    return ast.dump(_strip_docstrings(ast.parse(src)), include_attributes=False)

def main(argv: list[str]) -> int:
    base, files = argv[1], argv[2:]
    bad = []
    for path in files:
        before = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True, check=True).stdout
        after = open(path, encoding="utf-8").read()
        if _dump(before) != _dump(after):
            bad.append(path)
    for path in bad:
        print(f"CODE CHANGED (not comment-only): {path}")
    print(f"{len(files) - len(bad)} of {len(files)} files comment-only against {base}")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
