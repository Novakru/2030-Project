"""
.. module:: chemputerxdl.platform
    :platforms: Unix, Windows
    :synopsis: Chemputer XDL abstraction of the Chempiler

"""

from xdl import XDL
from typing import Optional, List, Dict
from .steps.collection import STEP_OBJ_DICT
from .executor import ChemputerExecutor
from xdl.platforms import AbstractPlatform
from .graphgen import graph_from_template
from xdl.utils import schema
from .localisation import HUMAN_READABLE_STEPS

class ChemputerPlatform(AbstractPlatform):

    @property
    def step_library(self) -> Dict:
        """Returns the library of steps in the platform.
        Returns:
            Dict: Step library
        """

        return STEP_OBJ_DICT

    @property
    def executor(self) -> ChemputerExecutor:
        """Get the executor of the platform

        Returns:
            ChemputerExecutor: Chemputer Executor
        """

        return ChemputerExecutor

    def graph(
        self,
        xdl_obj: XDL,
        template: Optional[str] = None,
        save: Optional[str] = None,
        auto_fix_issues: Optional[bool] = True,
        ignore_errors: Optional[List[int]] = []
    ) -> Dict:
        """Get the graph associated with this platform

        Args:
            xdl_obj (XDL): XDL object

            template (Optional[str], optional): Graph template.
                                                Defaults to None.

            save (Optional[str], optional): Save a new graph template.
                                            Defaults to None.

            auto_fix_issues (Optional[bool], optional): Automatically fix
                                        any fixable issues. Defaults to True.

            ignore_errors (Optional[List[int]], optional): Ignore any errros
                                                    raised. Defaults to [].

        Returns:
            Dict: Graph created from template
        """

        return graph_from_template(
            xdl_obj,
            template=template,
            save=save,
            auto_fix_issues=auto_fix_issues,
            ignore_errors=ignore_errors
        )

    @property
    def schema(self) -> str:
        """Get the XDL schema

        Returns:
            str: Schema
        """

        return schema.generate_schema(STEP_OBJ_DICT)

    @property
    def localisation(self) -> List[str]:
        """Get the localisation languages for all Chemputer XDL steps

        Returns:
            List[str]: Localisations
        """

        return HUMAN_READABLE_STEPS
