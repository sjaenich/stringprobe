from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from z3.z3 import *
from z3.z3 import BoolRef
from compiler_provenance.reverse_engineering.information.information_extractor import InformationExtractor
from .string_parser import StringParser, SourceStringEntry
from tqdm import tqdm
from .superc import SuperC

@dataclass
class MSC:
    presencecondtion: BoolRef
    line: int


@dataclass    
class TreePath:
    data: list[SourceStringEntry]
    presence_conditions: BoolRef


    def __add__(self, other: "TreePath") -> "TreePath":
        if not isinstance(other, TreePath):
            return NotImplemented
        return TreePath(self.data + other.data, And(self.presence_conditions,other.presence_conditions))
    def head(self) -> "TreePath":
        return TreePath([self.data[0]],self.presence_conditions)

    def tail(self) -> "TreePath":
        return TreePath(self.data[1:], self.presence_conditions)
    
    def to_string(self) -> str:
        string =""
        for sse in self.data:
            string += sse.content
        return string

    def to_z3(self) -> BoolRef:
        arguments = []
        for sse in self.data:
            if sse.macro:
                x = String(sse.content)
                arguments.append(x)
            else:
                arguments.append(sse.content)
        return arguments

    def contains_unresolved_macro(self) -> bool:
        for sse in self.data:
            if sse.macro:
                return True
        return False
    
    def __len__(self) -> int:
        return len(self.data)


class SourceFile:
    def __init__(self, source_file_path :Path, binary_strings: InformationExtractor, library_dir: str, index: int, config_h: Path, name: str, include_dir: str, extra_include=None):
        self.source_file_path = source_file_path
        self.library_dir = library_dir
        self.binary_strings = binary_strings.strings
        self.source_strings: StringParser
        self.str_to_pc: dict[str, BoolRef] = dict()
        self.pc_condition_counts: dict[BoolRef, int] = defaultdict(int)
        self.macro_to_presence_condition: dict[str, BoolRef] = dict()
        self.macro_string_connection: dict[int, BoolRef] = dict()
        self.covered_lines: set[int] = set()
        self.solver: Solver = Solver()
        self.index_set: list = []
        self.source_code_strings: list[str] = []
        self.index: int = index
        self.config_h = config_h
        self.name = name
        self.include_dir = include_dir
        self.extra_include = extra_include

    def get_macro_formulas(self) -> Solver:
        self.solver = Solver()
        self.source_strings = StringParser(self.source_file_path)
        self.source_strings.extract_string_literals()
        self.source_strings.clean_string_literals()
        self.source_strings.add_func_names()
        

        print("Getting the strings --> normal and resolved")
        normal_strings = self.source_strings.strings
        resolved_strings = self.resolve_strings(self.source_strings.strings_with_unresolved_macros) 
        print("Getting the macro string connections --> normal ")


        s = String('s')
        i = Int('i') 
        BinaryStrings = self.binary_strings
        InBinary = Function('InBinary', StringSort(), IntSort(), BoolSort())

        self.add_string_presence_conditions(normal_strings)
          
        print("Getting the macro string connections --> resolved")
        self.add_string_tp_presence_conditions(resolved_strings)

        print("Added to solver")
        return self.solver

                


    def resolve_strings(self, unresolved: list[list[SourceStringEntry]]) -> list[TreePath]:
        resolved_strings = []
        for concat in tqdm(unresolved):
            concat_tp = TreePath(concat, True)
            resolved_strings += self._get_all(concat_tp, [], self.source_file_path, self.library_dir)
        return resolved_strings



    def add_string_presence_conditions(self, strings: list[SourceStringEntry]):
        macros = set()
        resolved_strings = []
        InBinary = Function('InBinary', StringSort(), IntSort(), BoolSort())
        strings_to_presence_condition = dict()
        entries = SuperC().get_pc_and_macro_values(self.source_file_path, self.library_dir, None, None, self.config_h, self.name, self.include_dir, self.extra_include)
        if entries == []:
            print("No Presence Conditions for",  self.source_file_path)
            return None
        for string in strings:
            if string.content.endswith(".h"):
                continue
            entry = entries[0]
            for e in entries:
                if e.line > string.line_number:
                    break
                entry = e
            string_tp = TreePath([string], entry.pc)
            print("String and PC", string, entry.pc)
            resolved_strings.append(string_tp)
        
        for string_tp in resolved_strings:
            self.index = self.index + 1
            string = string_tp.to_string()
            if len(string) <= 3:
                continue
            label = Bool(f"pc_{string}_{self.index}")
            pc = string_tp.presence_conditions
            pc_key = pc.sexpr() 
            if not str(string_tp.presence_conditions) == "True":
                if self.pc_condition_counts[pc_key] < 8:
                    self.solver.add(string_tp.presence_conditions == InBinary(StringVal(string), self.index))
                    print("Added to solver", string_tp.presence_conditions == InBinary(StringVal(string), self.index))
                    self.pc_condition_counts[pc_key] += 1
                else:
                    print("Not added to solver", string_tp.presence_conditions == InBinary(StringVal(string), self.index))
   
            
            
            self.str_to_pc[label] = string_tp.presence_conditions 
            if not str(string_tp.presence_conditions) == "False":
                self.index_set.append((string, self.index))
                self.source_code_strings.append(string)


    def add_string_tp_presence_conditions(self, resolved_strings: list[TreePath]):
        strings_to_presence_condition = dict()
        InBinary = Function('InBinary', StringSort(), IntSort(), BoolSort())
        for string_tp in resolved_strings:
            arguments = []
            self.index = self.index + 1
            if string_tp.contains_unresolved_macro():
                arguments = string_tp.to_z3()
                label = Bool(f"pc{Concat(arguments)}_{self.index}")
                self.source_code_strings.append(Concat(arguments))
                self.str_to_pc[label] = string_tp.presence_conditions
            else:
                string = string_tp.to_string()
                label = Bool(f"pc_{string}_{self.index}")
                pc = string_tp.presence_conditions
                pc_key = pc.sexpr()
                if not str(string_tp.presence_conditions) == "True":
                    if self.pc_condition_counts[pc_key] < 5:
                        self.solver.add(string_tp.presence_conditions == InBinary(StringVal(string), self.index))
                        print("resolved", string_tp.presence_conditions ==  InBinary(StringVal(string), self.index))
                        self.pc_condition_counts[pc_key] += 1
                if not str(string_tp.presence_conditions) == "False":
                    self.index_set.append((string, self.index))
                self.source_code_strings.append(string)
                self.str_to_pc[label] = string_tp.presence_conditions
            
                            
    def _get_variants(self, entry: TreePath, filepath, library) -> list[TreePath]:
        variants = []
        if len(entry.data) >1:
            return ValueError("TreePath should only have length 1")
        if entry.data[0].macro:
            presence_conditions = SuperC().get_pc_and_macro_values(filepath, library, entry.data[0].line_number, entry.data[0].content, self.config_h, self.name, self.include_dir, self.extra_include)
            if presence_conditions is None:
                variants.append(entry)
            else:
                for pc in presence_conditions:
                
                    if pc.macro == "undefined" or pc.macro == "None":
                        entry.presence_conditions = And(entry.presence_conditions, pc.pc)
                        variants.append(entry)
                    else:
                        new_sse = SourceStringEntry(pc.macro, pc.line, False)
                        new_tp = TreePath([new_sse], pc.pc)
                        variants.append(new_tp)
        else:
            variants.append(entry)
        return variants


    def _get_all(self,input: TreePath, outputs: list[TreePath], filepath, library) -> list[TreePath]:
        if len(input) == 0:
            return outputs
        h = input.head()
        
        variants = self._get_variants(h, filepath, library)
        tail = input.tail()
        old_outputs = outputs.copy()
        outputs.clear()
        for variant in variants:
            for output in old_outputs:
                outputs.append(output + variant)
            if outputs == []:
                outputs.append(variant)
        
        return self._get_all(tail, outputs, filepath, library)