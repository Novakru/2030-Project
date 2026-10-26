from typing import Optional, List, Dict, Type
from networkx import MultiDiGraph
from .abstract_platform import AbstractPlatform
from ..execution.abstract_executor import AbstractXDLExecutor
from ..steps import Step
from ..steps import placeholders, Wait
if False:
    from ..xdl import XDL

class PlaceholderExecutor(AbstractXDLExecutor):
    pass

class PlaceholderPlatform(AbstractPlatform):
    """Placeholder platform providing no compilation but the xdl cross platform
    standard as the step library.
    """

    @property
    def step_library(self) -> Dict[str, Type[Step]]:
        """Collection of steps associated with the platform. Should take the
        form of a mapping between step class names and step classes, e.g.
        ``{ 'Add': Add, 'Stir': Stir... }``

        Returns:
            Dict[str, Type[Step]]: Collections of steps associated with platform
            in form ``{ step_name: step_type... }``
            e.g. ``{ 'Add': Add... }``.
        """
        return {
            'Add': placeholders.Add,
            'AddSolid': placeholders.AddSolid,
            'CleanVessel': placeholders.CleanVessel,
            'Crystallize': placeholders.Crystallize,
            'Dissolve': placeholders.Dissolve,
            'Dry': placeholders.Dry,
            'EvacuateAndRefill': placeholders.EvacuateAndRefill,
            'Evaporate': placeholders.Evaporate,
            'Filter': placeholders.Filter,
            'FilterThrough': placeholders.FilterThrough,
            'HeatChill': placeholders.HeatChill,
            'HeatChillToTemp': placeholders.HeatChillToTemp,
            'Irradiate': placeholders.Irradiate,
            'Precipitate': placeholders.Precipitate,
            'Purge': placeholders.Purge,
            'RunColumn': placeholders.RunColumn,
            'Separate': placeholders.Separate,
            'StartHeatChill': placeholders.StartHeatChill,
            'StartPurge': placeholders.StartPurge,
            'StartStir': placeholders.StartStir,
            'Stir': placeholders.Stir,
            'StopHeatChill': placeholders.StopHeatChill,
            'StopPurge': placeholders.StopPurge,
            'StopStir': placeholders.StopStir,
            'Transfer': placeholders.Transfer,
            'Wait': Wait,
            'WashSolid': placeholders.WashSolid,
        }

    @property
    def executor(self) -> Type[AbstractXDLExecutor]:
        return PlaceholderExecutor

    def graph(
        self,
        xdl_obj: 'XDL',
        template: Optional[str] = None,
        save: Optional[str] = None,
        auto_fix_issues: Optional[bool] = True,
        ignore_errors: Optional[List[int]] = []
    ) -> MultiDiGraph:
        return None
