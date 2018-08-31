# coding=utf-8
# Licensed Materials - Property of IBM
# Copyright IBM Corp. 2016,2018
#
# Wrap the operator's iterable in a function
# that when called returns each value from
# the iteration returned by iter(callable).
# It the iteration returns None then that
# value is skipped (i.e. no tuple will be
# generated). When the iteration stops
# the wrapper function returns None.
#
# There are two possibilities:
# a) iterable is a decorated class and is iterable
# b) iterable is a decorated function that returns an iterator
#

from future.builtins import *
import collections
import sys
import streamsx.spl.types
import streamsx._streams._runtime

class _SourceIterable(object):
    def __init__(self, callable_):
        self._callable = callable_
        self._splpy_context = streamsx._streams._runtime._has_context_methods(type(self._callable))
        self._splpy_entered = False

        try:
            self._it = iter(self._callable)
        except TypeError:
            self._it = self._callable()
        except:
            ei = sys.exc_info()
            if streamsx._streams._runtime._call_exit(iterable, ei[0], ei[1], ei[2]):
                self._it = iter([])
            else:
                raise ei[1]

    def __call__(self):
        try:
            while True:
                tuple_ = next(self._it)
                if tuple_ is not None:
                     return tuple_
        except StopIteration:
            self._it = None
            return None

    def __enter__(self):
        self._callable.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        return self._callable.__exit__(exc_type, exc_value, traceback)


# The decorated operators only support converting
# Python tuples or a list of Python tuples to
# an SPL output tuple. To simplify the generated code
# we handle any other type by using a wrapper function
# and converting to a Python tuple or list of Python
# tuples.
#
# A Python tuple returned by the wrapped function
# may be sparse, values not set by the dictionary
# (etc.) are set to None in the Python tuple.

def _splpy_convert_tuple(attributes):
    """Create a function that converts tuples to
    be submitted as dict objects into Python tuples
    with the value by position.
    Return function handles tuple,dict,list[tuple|dict|None],None
    """

    def _to_tuples(tuple_):
        if isinstance(tuple_, tuple):
            return tuple_
        if isinstance(tuple_, dict):
            return tuple(tuple_.get(name, None) for name in attributes)
        if isinstance(tuple_, list):
            lt = list()
            for ev in tuple_:
                if isinstance(ev, dict):
                    ev = tuple(ev.get(name, None) for name in attributes)
                lt.append(ev)
            return lt
        return tuple_
    return _to_tuples

def _splpy_to_tuples(fn, attributes):
   conv_fn = _splpy_convert_tuple(attributes)

   def _to_tuples(*args, **kwargs):
      value = fn(*args, **kwargs)
      return conv_fn(value)

   _add_shutdown_hook(fn, _to_tuples)
   return _to_tuples

def _splpy_release_memoryviews(*args):
    for o in args:
        if isinstance(o, memoryview):
            o.release()
        elif isinstance(o, list):
            for e in o:
                _splpy_release_memoryviews(e)
        elif isinstance(o, dict):
            for e in o.values():
                _splpy_release_memoryviews(e)

def _splpy_primitive_input_fns(obj):
    """Convert the list of class input functions to be
        instance functions against obj.
        Used by @spl.primitive_operator SPL cpp template.
    """
    ofns = list()
    for fn in obj._splpy_input_ports:
        ofns.append(getattr(obj, fn.__name__))
    return ofns
    
def _splpy_all_ports_ready(callable_):
    """Call all_ports_ready for a primitive operator."""
    if hasattr(type(callable_), 'all_ports_ready'):
        try:
            return callable_.all_ports_ready()
        except:
            if streamsx._streams._runtime._call_exit(callable_):
                return None
            raise
    return None

_Timestamp = collections.namedtuple('Timestamp', ['seconds', 'nanoseconds', 'machine_id'])

# Used by Timestamp.__reduce__ to avoid dill
# trying to treat a Timestamp as a namedtuple.
def _stored_ts(s, ns, mid):
    return streamsx.spl.types.Timestamp(s, ns, mid)

