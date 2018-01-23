# coding=utf-8
# Licensed Materials - Property of IBM
# Copyright IBM Corp. 2018

import copy
import dis
import inspect
import logging

import streamsx.spl.code.opcodes
import streamsx.spl.code.types as types
import streamsx.topology.schema
import streamsx.topology.topology
import streamsx.spl.op

trace = logging.getLogger('streamsx.topology.translator')

class _SPLTupleCtx(object):
    """Code translator for a function passed a structured schema tuple as a single argument.
    """
    def __init__(self, code, in_schema, out_schema=None):
        self.code = code
        self._tuple = types.InTuple(0, code.co_varnames[0])
        self.in_schema = in_schema
        # Attributes by position and name
        attrs = types.attributes(in_schema)
        self.in_attrs_pos = attrs[0]
        self.in_attrs_name = attrs[1]
        self._referenced_attrs = set()

        if out_schema:
            self.out_schema = out_schema
            attrs = types.attributes(out_schema)
            self.out_attrs_pos = attrs[0]
            self.out_attrs_name = attrs[1]

        self._seen_return = False
        self._return = None

        self.jumps = dict()

    def alias(self):
        """Alias the input stream requires once it is translated to SPL operator invocation.

        The SPL expressions reference the input tuple as the returned value.
        """
        return self._tuple.name

    def read_attribute(self, name):
        self._referenced_attrs.add(name)
        return types.ReadAttribute(self._tuple, self.in_attrs_name[name])


    def merge_jumps(self, stack, ins):
        jump_values = self.jumps.get(ins.offset)
        if not jump_values:
            return

        while jump_values:
            jv = jump_values.pop()
            jv_val = jv[0]
            jv_ins = jv[1]
            if jv_ins.opname == 'JUMP_IF_FALSE_OR_POP':
                tos = types.CodeValue('boolean', types.binary(jv_val, '&&', types.as_boolean(stack.pop())))
                stack.append(tos)
            elif jv_ins.opname == 'JUMP_IF_TRUE_OR_POP':
                tos = types.CodeValue('boolean', types.binary(jv_val, '||', types.as_boolean(stack.pop())))
                stack.append(tos)
            else:
                raise types.CannotTranslate(jv_ins)


    def _calculate(self):
        """Calculate the returned expressions based upon byte code.

        Raises:
            AttributeError: Code accesses an attribute of the tuple
                that does not exist.
            CannotTranslate: Code cannot be translated into SPL.
           
        """
        stack = list()
        for ins in dis.get_instructions(self.code):
            if self._seen_return:
                raise types.CannotTranslate(ins, 'Already seen return')
            act = streamsx.spl.code.opcodes.OA.get(ins.opname)
            if act is not None:
                if ins.is_jump_target:
                    self.merge_jumps(stack, ins)
                act(self, stack, self.code, ins)
            else:
                raise types.CannotTranslate(ins, "Not supported")

    def _tuple_spl(ctx, schema, tuple_):
        st = '{'
        attr_names = ['a', 'b', 'c']
        for i in range(len(attr_names)):
             if i:
                 st += ', '
             st += attr_names[i]
             st += '=';
             st += tuple_[i]
        
        st += '}'
        return st

def enabled(topo, fn):

    state = topo.features.get(streamsx.topology.topology.Topology.TRANSLATE_FEATURE, False)
    if isinstance(state, bool):
        if not state:
            return False
    else:
        state = str(state).lower()
        state = state == 'true' or state == 'yes'
        if not state:
            return False

    if hasattr(fn, '_spl_translate'):
        return fn._spl_translate
    return True


def translatable_schema(schema):
    if streamsx.topology.schema.is_common(schema):
        return False
    print("type:schema:" + str(type(schema)))
    if not hasattr(schema, '_types'):
        return False
    return True

def translatable_logic(fn):
    return inspect.isfunction(fn) and hasattr(fn, '__code__')

def translate_filter(stream, fn, name):
    """Translate a Python filter to an SPL Filter if possible."""

    if not enabled(stream.topology, fn):
        return None
    schema = stream.oport.schema
    if not translatable_schema(schema):
        return None

    if translatable_logic(fn):
        ctx = FilterCtx(fn.__code__, schema)
        if ctx.translate():
            return ctx.add_translated(stream, name)
    return None

class FilterCtx(_SPLTupleCtx):
    """Translator for a Python filter against a structured schema.

    Args:
        code: Code atttribute ``__code__`` of Python function.
        in_schema(StreamSchema): Schema of input stream.

    """
    def __init__(self, code, in_schema):
        super(FilterCtx, self).__init__(code, in_schema)

    def translate(self):
        """
        Attempt to translate filter function.

        Return True if translation was successful, else False.
        """
        try:
            self._calculate()

            # Convert any return to boolean type
            # following Python rules.
            self._return = types.as_boolean(self._return)
            return True
        except types.CannotTranslate as e:
            trace.debug(e.ins + " -- " + e.args)
            return False

    def filter_expression(self):
        """Return the translated filter expression.
        Requires the stream is alaised as `alias()`.
        """
        return self._return.expr if self._return else None

    def add_translated(self, stream, name):

        stream = stream.aliased_as(self.alias())

        params = {'filter': streamsx.spl.op.Expression.expression(str(self.filter_expression()))}
        _op = streamsx.spl.op.Map('spl.relational::Filter', stream, params=params, name=name)
        _op.stream._spl_translated = 'FromPython'
        return _op

def translate_map(stream, fn, out_schema, name):
    """Translate a Python map to SPL if possible."""

    trace.debug("Translator: Attempting " + str(name))

    if not enabled(stream.topology, fn):
        trace.debug("Translator: Not enabled")
        return None

    if not translatable_schema(out_schema):
        trace.debug("Translator: Output schema not supported." + str(out_schema))
        return None

    in_schema = stream.oport.schema
    if not translatable_schema(in_schema):
        trace.debug("Translator: Input schema not supported." + str(in_schema))
        return None

    if not translatable_logic(fn):
        trace.debug('Translator: Callable not translatable:' + str(fn))
        return None

    ctx = MapCtx(fn.__code__, in_schema, out_schema)
    if ctx.translate():
        return ctx.add_translated(stream, name)

    trace.debug("Translator: Code not translatable:" + str(fn))
    return None

class MapCtx(_SPLTupleCtx):
    def __init__(self, code, in_schema, out_schema):
        super(MapCtx, self).__init__(code, in_schema, out_schema)


    def translate(self):
        try:
            self._calculate()
        except types.CannotTranslate as e:
            trace.debug(e.ins + " -- " + e.args)
            return False

        if not isinstance(self._return, types.CodeTuple):
            return False

        if len(self._return.values) != len(self.out_attrs_pos):
            return False

        try:
            values = self._return.values
            assignments = []
            for i in range(len(self.out_attrs_pos)):
                attr = self.out_attrs_pos[i]
                assignments.append(types.assignment_cast(values[i], attr.code_type))
            self.assignments = assignments
            return True
        except types.CannotTranslate:
            return False

    def add_translated(self, stream, name):
        stream = stream.aliased_as(self._tuple.name)

        params = {}
        _op = streamsx.spl.op.Map('spl.relational::Functor', stream, schema=self.out_schema, params=params, name=name)
        for i in range(len(self.out_attrs_pos)):
            attr = self.out_attrs_pos[i]
            setattr(_op, attr.name, _op.output(str(self.assignments[i])))
        _op.stream._spl_translated = 'FromPython'
        return _op

