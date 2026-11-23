import io, ast
s = io.open("gui.py", encoding="utf-8").read()
ast.parse(s); print("AST OK", len(s))
