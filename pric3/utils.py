from fractions import Fraction
from typing import List, Any, BinaryIO
from io import StringIO
from tempfile import NamedTemporaryFile
from z3 import BoolRef, Z3_mk_ge, Z3_mk_eq, Solver, sat, Int, unsat, unknown, Real, And, Z3_mk_le, RealVal
import math
import os
import pickle
import signal
import pathlib

import stormpy


def intersperse(val, sequence):
    """
    Insert val between each element in the sequence.

    .. doctest::

        >>> join_generator(intersperse(", ", ["hello", "world"]))
        'hello, world'
    """
    first = True
    for item in sequence:
        if not first:
            yield val
        yield item
        first = False

def next_or_value(val):
    """
    If `val` is an iterator, call `next`, otherwise just return `val`.

    .. doctest::

        >>> next_or_value([1,2])
        [1, 2]
        >>> next_or_value(iter([1,2]))
        1
    """
    if hasattr(val, '__next__'):
        return next(val)
    else:
        return val

def parse_fraction(val):
    """
    If val is a string, parse it as a Fraction.
    If val is an int, parse it as a Fraction.
    If val is a Fraction, return it.
    If val is something else, throw an error.
    """
    if isinstance(val, Fraction):
        return val
    elif isinstance(val, (int, str)):
        return Fraction(val)
    else:
        raise Exception(
            'Value must be either a string, int, or Fraction. E.g. floats are not allowed to avoid precision loss.'
        )


def join_generator(generator):
    """
    Join all strings returned by the generator into one large string using io.StringIO.
    """
    buf = StringIO()
    for text in generator:
        buf.write(text)
    return buf.getvalue()


def parse_prism_program_string(program_str: str) -> stormpy.PrismProgram:
    """
    Parse a PRISM program from a string.
    Creates a temporary file and reads it using stormpy.parse_prism_program.
    """
    with NamedTemporaryFile(mode="w+") as file:
        file.write(program_str)
        file.flush()
        return stormpy.parse_prism_program(file.name)


def concat_generators(*generators):
    for generator in generators:
        yield from generator


def attach_newtype_declaration_module(typ: type, declaration_module_name: str):
    """
    Add a ``declaration_module_name`` to a newly created type.

    This ugly hack is used in the ``conf.py`` for the sphinx documentation.

    Apparently no one else wanted newtypes with proper documentation links...

    Parameters:
        typ: The type to be annotated.
        declaration_module_name: always ``__name__``.
    """
    typ.declaration_module_name = declaration_module_name  # type: ignore

def ge_no_coerce(left, right):
    # TODO: add assertions for noncoerce
    return BoolRef(Z3_mk_ge(left.ctx_ref(), left.as_ast(), right.as_ast()), left.ctx)

def le_no_coerce(left, right):
    # TODO: add assertions for noncoerce
    return BoolRef(Z3_mk_le(left.ctx_ref(), left.as_ast(), right.as_ast()), left.ctx)

def eq_no_coerce(left,right):
    #TODO add assertion for coercion-free
    return BoolRef(Z3_mk_eq(left.ctx_ref(), left.as_ast(), right.as_ast()), left.ctx)

def state_valuation_to_z3_check_args(state_valuation):
    """
    Converts a state_valuation to a list of state args which is to be passed to a relative inductiveness check.
    :param state_valuation: The state valuation that is to be converted.
    :return: The list of args of the solver.
    """
    return [eq_no_coerce(var.variable, val) for var, val in state_valuation.items()]


compare_solver = Solver()

integer_div_res = Int("Div")
real_div_res = Real("RDiv")
eval_result = Real("result")

def z3_values_check_gt(val_1, val_2):
    return compare_solver.check(val_1 > val_2) == sat

def z3_values_check_lt(val_1, val_2):
    return compare_solver.check(val_1 < val_2) == sat

def z3_values_check_geq(val_1, val_2):
    return compare_solver.check(val_1 >= val_2) == sat

def z3_values_check_leq(val_1, val_2):
    return compare_solver.check(val_1 <= val_2) == sat

def z3_values_check_neq(val_1, val_2):
    return compare_solver.check(val_1 != val_2) == sat

def z3_values_check_eq(val_1, val_2):
    return compare_solver.check(val_1 == val_2) == sat



def z3_integer_division(divisor, dividend):
    res = compare_solver.check(integer_div_res == divisor / dividend)

    if res == unsat or res == unknown:
        raise

    else:
        return compare_solver.model()[integer_div_res]

def z3_real_floored_division(divisor, dividend):
    res = compare_solver.check(real_div_res == divisor / dividend)

    if res == unsat or res == unknown:
        raise

    else:
        return RealVal(math.floor(compare_solver.model()[real_div_res].as_fraction()))


def z3_evaluate_polynomial_at_point(polynomial, variable, value):
    res = compare_solver.check(And(eval_result == polynomial, variable == value))

    if res == unsat or res == unknown:
        raise

    else:
        return compare_solver.model()[eval_result]


def sort_list_of_z3_numbers(to_sort):
    to_sort = [n.as_fraction() for n in to_sort]
    to_sort = sorted(to_sort)


def create_binary_file_with_incremental_name(filename_pattern: str) -> BinaryIO:
    """
    Given a pattern, open (that is, create) a new file with a name
    generated from the given pattern.
    The directory in the pattern must not contain any pattern symbols.
    The directory will be created recursively before the new file is created.
    """
    # create the directory
    pathlib.Path(pathlib.PurePath(filename_pattern).parent).mkdir(exist_ok=True)

    i = 0
    while True:
        filename = filename_pattern % i
        try:
            return open(filename, 'xb')
        except FileExistsError:
            pass
        i += 1

def unpickle_all_in_directory(directory_path: str) -> List[Any]:
    """
    Unpickle all files in a directory.
    """
    objects = []
    files = sorted(pathlib.Path(directory_path).iterdir(), key=os.path.getmtime)
    for path in files:
        try:
            objects.append(pickle.load(open(path, "rb")))
        except EOFError:
            print("EOFError while opening %s" % path)
    return objects

def setup_sigint_handler():
    # When interrupted, Python handles SIGINT with a KeyboardInterruptException.
    # However, this prevents proper detection of terminated processes
    # by shells that invoked this program.
    # A shell script that invokes e.g. this program in a loop would continue
    # with the next command even though a SIGINT to this program should result
    # in termination of the shell script as well.
    #
    # One may consider this as a design flaw in Python.
    #
    # References:
    #   * https://github.com/fish-shell/fish-shell/issues/3104
    #   * https://stackoverflow.com/a/47900396
    def handle_int(signum, frame):
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    signal.signal(signal.SIGINT, handle_int)
