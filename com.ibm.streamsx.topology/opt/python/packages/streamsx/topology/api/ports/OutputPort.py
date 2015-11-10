
from streamsx.topology.api.ports.PortDeclaration import PortDeclaration
from streamsx.topology.utils.frameRetriever import functionId

class OutputPort(PortDeclaration):

    def getInputPorts(self):
        """
        Returns a list of input ports connected to the output port
        :return: a list of input ports connected to the output port
        """
        raise Exception("Unimplemented interface method: %s" % functionId(self, 0))
