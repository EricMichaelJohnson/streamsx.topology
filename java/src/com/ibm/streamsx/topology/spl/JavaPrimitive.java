/*
# Licensed Materials - Property of IBM
# Copyright IBM Corp. 2015  
 */
package com.ibm.streamsx.topology.spl;

import java.util.Map;

import com.ibm.streams.operator.Operator;
import com.ibm.streams.operator.StreamSchema;
import com.ibm.streams.operator.model.PrimitiveOperator;
import com.ibm.streamsx.topology.TSink;
import com.ibm.streamsx.topology.TopologyElement;
import com.ibm.streamsx.topology.builder.BOperatorInvocation;
import com.ibm.streamsx.topology.internal.core.SourceInfo;
import com.ibm.streamsx.topology.internal.core.TSinkImpl;

/**
 * Integration between Java topologies and SPL Java primitive operators.
 * 
 */
public class JavaPrimitive {

    /**
     * Create an SPLStream from the invocation of an SPL Java primitive
     * operator. The Java class {@code opClass} must be annotated with
     * PrimitiveOperator.
     * 
     * @param opClass
     *            Class of the operator to be invoked.
     * @param input
     *            Stream that will be connected to the only input port of the
     *            operator
     * @param outputSchema
     *            SPL schema of the operator's only output port.
     * @return SPLStream the represents the output of the operator.
     */
    public static SPLStream invokeJavaPrimitive(
            Class<? extends Operator> opClass, SPLInput input,
            StreamSchema outputSchema, Map<String, ? extends Object> params) {

        BOperatorInvocation op = input.builder().addOperator(
                getInvocationName(opClass),
                opClass, params);
        SourceInfo.setSourceInfo(op, JavaPrimitive.class);
        SPL.connectInputToOperator(input, op);

        return new SPLStreamImpl(input, op.addOutput(outputSchema));
    }

    /**
     * Invocation of a Java primitive operator that consumes a Stream.
     * 
     * @param opClass
     *            Class of the operator to be invoked
     * @param input
     *            Stream that will be connected to the only input port of the
     *            operator
     * @param params
     *            Parameters for the operator, ignored if null
     * @return the sink element
     */
    public static TSink invokeJavaPrimitiveSink(
            Class<? extends Operator> opClass, SPLInput input,
            Map<String, ? extends Object> params) {

        BOperatorInvocation sink = input.builder().addOperator(
                getInvocationName(opClass),
                opClass, params);
        SourceInfo.setSourceInfo(sink, JavaPrimitive.class);
        SPL.connectInputToOperator(input, sink);
        return new TSinkImpl(input.topology(), sink);
    }

    /**
     * Invocation of a Java primitive source operator to produce a SPL Stream.
     * 
     * @param te
     *            Reference to Topology the operator will be in.
     * @param opClass
     *            Class of the operator to be invoked.
     * @param params
     *            Parameters for the SPL Java operator.
     * @param schema
     *            Schema of the output port.
     * @return SPLStream the represents the output of the operator.
     */
    public static SPLStream invokeJavaPrimitiveSource(TopologyElement te,
            Class<? extends Operator> opClass,
            Map<String, ? extends Object> params, StreamSchema schema) {

        
        BOperatorInvocation source = te.builder().addOperator(
                getInvocationName(opClass),
                opClass, params);
        SourceInfo.setSourceInfo(source, JavaPrimitive.class);
        return new SPLStreamImpl(te, source.addOutput(schema));
    }
    
    private static String getInvocationName(Class<? extends Operator> opClass) {
        PrimitiveOperator po = opClass.getAnnotation(PrimitiveOperator.class);
        if (po == null)
            throw new IllegalStateException("Missing @PrimitiveOperator for: " + opClass.getName());
        String opName = po.name();
        if (opName.isEmpty()) {
            opName = opClass.getSimpleName();
        }
        return opName;
    }
}
