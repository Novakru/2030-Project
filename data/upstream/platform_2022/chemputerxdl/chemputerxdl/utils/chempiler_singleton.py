"""This is hacky. But it is effective. In the ``CMove`` step it is critical
that the duration is calculated using a ``Chempiler`` object so that it is
accurate. However, the duration step only takes the graph as an argument, and I
don't want to change this as it makes no sense for any of the other steps or
platforms to use the platform controller here, and makes calculating durations
more hassle.

The solution to this is to instantiate the Chempiler object within the duration
method. But this is very inefficient as Chempiler instantiation is not
instantaneous, and the ``CMove`` method can be called many times when
calculating duration for a whole procedure.

Therefore, to make this approach feasible a Chempiler singleton object is
included here that CMove can access from within the duration method. If the
same object is supplied as the last request for the singleton, then the
Chempiler object will be returned. If a different object is supplied from the
last request, then a new Chempiler object will be created and returned.
"""
from networkx import MultiDiGraph
from chempiler import Chempiler
from commanduinolabware import CommanduinoLabware
from ..utils.execution import get_chempiler

CHEMPILER_SINGLETON = None
_CHEMPILER_SINGLETON_GRAPH_ID = None

def get_chempiler_singleton(graph: MultiDiGraph) -> Chempiler:
    """Get ``Chempiler`` object instantiated with ``graph``. Using this function
    is generally more efficient than instantiating a ``Chempiler`` object
    normally in the code. For a full description of why, read the module
    docstring.

    Args:
        graph (MultiDiGraph): Graph to instantiate ``Chempiler`` object with.

    Returns:
        Chempiler: ``Chempiler`` object instantiated with ``graph``.
    """
    global CHEMPILER_SINGLETON, _CHEMPILER_SINGLETON_GRAPH_ID

    graph_id = id(graph)
    # Graph is the same object used to generate the existing singleton, just
    # return it.
    if graph_id == _CHEMPILER_SINGLETON_GRAPH_ID:
        return CHEMPILER_SINGLETON

    # Graph is different to the one used to generate the existing singleton,
    # replace singleton with new `Chempiler` object and return it.
    else:
        try:
            CHEMPILER_SINGLETON = get_chempiler(
                graph, device_modules=[])
            _CHEMPILER_SINGLETON_GRAPH_ID = graph_id

        # This is an EXTREMELY HACKY thing, to avoid introducing
        # AnalyticalLabware as a hard dependency, but to allow the ``duration``
        # method to use it for instantiating Chempiler when necessary.
        except KeyError:
            from AnalyticalLabware.devices import chemputer_devices
            device_modules = [chemputer_devices]
            CHEMPILER_SINGLETON = get_chempiler(
                graph, device_modules=device_modules)
            _CHEMPILER_SINGLETON_GRAPH_ID = graph_id

        # The reason for this is that when Chempiler is instantiated during
        # it does so in simulation mode. Any CommanduinoLabware devices will
        # initialise the CommanduinoLabware singleton in simulation mode. Any
        # attempt thereafter to initialise Chempiler (and therefore the
        # CommanduinoLabware singleton) in non-simulation mode will raise an
        # error saying real and simulated devices cannot be mixed. This resets
        # the singleton so that it can be reinitialised within the same script.
        CommanduinoLabware.reset()
        return CHEMPILER_SINGLETON
