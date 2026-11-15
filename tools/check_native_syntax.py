"""Optional grammar check only, NOT Android SDK type checking or compilation.
Install: pip install tree-sitter tree-sitter-kotlin
"""
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_kotlin

root = Path(__file__).resolve().parents[1]
parser = Parser(Language(tree_sitter_kotlin.language()))
failed = []
for path in (root / "android").rglob("*.kt"):
    tree = parser.parse(path.read_bytes())
    todo, errors = [tree.root_node], []
    while todo:
        node = todo.pop()
        if node.type == "ERROR" or node.is_missing:
            errors.append(str(node.start_point))
        todo.extend(node.children)
    print(str(path.relative_to(root)), "OK" if not errors else errors)
    if errors:
        failed.append(str(path))
if failed:
    raise SystemExit(1)
print("Kotlin grammar passed. A real Gradle build and phone tests are still required.")
