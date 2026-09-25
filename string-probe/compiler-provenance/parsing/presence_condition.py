import re
from ast import literal_eval
from z3.z3 import *
 
 









def split_on_top_level_AND(text: str):
    parts = []
    start = 0
    depth = 0
    in_bar_symbol = False
    i = 0

    while i < len(text):
        ch = text[i]

        if ch == "|":
            in_bar_symbol = not in_bar_symbol
            i += 1
            continue

        if not in_bar_symbol:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif (
                depth == 0
                and text.startswith("AND", i)
                and (i == 0 or text[i - 1].isspace())
                and (i + 3 == len(text) or text[i + 3].isspace())
            ):
                part = text[start:i].strip()
                if part:
                    parts.append(part)

                start = i + 3
                i += 3
                continue

        i += 1

    tail = text[start:].strip()
    if tail:
        parts.append(tail)

    return parts


def parse_AND_connected_smt2(text: str):
    z3_exprs = []

    for part in split_on_top_level_AND(text):
        try:
            smt = parse_smt2_string(part)
        except Exception as e:
            raise ValueError(f"Could not parse SMT-LIB block:\n{part}") from e

        z3_exprs.extend(
            normalize_defined_symbols(e)
            for e in smt
            if isinstance(e, BoolRef)
        )

    if not z3_exprs:
        raise ValueError(f"SMT-LIB produced no Boolean assertions:\n{text}")

    return simplify(And(*z3_exprs))





        


    


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def defined_macro_name(name: str):
    m = re.fullmatch(
        r'\(\s*defined\s+([A-Za-z_][A-Za-z0-9_]*)\s*\)',
        name.strip(),
    )
    return m.group(1) if m else None


def normalize_defined_symbols(expr):
    replacements = []

    def visit(e, seen):
        key = e.hash()
        if key in seen:
            return
        seen.add(key)

        if is_const(e) and e.num_args() == 0:
            macro = defined_macro_name(e.decl().name())
            if macro is not None:
                replacements.append((e, Bool(macro)))

        for child in e.children():
            visit(child, seen)

    visit(expr, set())
    return substitute(expr, *replacements) if replacements else expr



class PresenceCondition():
    def __init__(self):
        self.line = -1
        self.file_path = None
        self.pc = None
        self.string_literal = None
        self.macro = dict()
    

    def parse(self, pc_string: str):
        pc_string = pc_string.replace("'Value': '\"'\"'", "'Value': \"'\"")
        pc_string = literal_eval(pc_string)
        self.line = int(pc_string["Line"])
        self.pc = parse_AND_connected_smt2(pc_string["PC"])
        self.macro = strip_quotes(pc_string["Value"])