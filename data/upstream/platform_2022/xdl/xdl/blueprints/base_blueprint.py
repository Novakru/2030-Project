from typing import List, Tuple
from ..steps import Step
from ..reagents import Reagent
from ..hardware import Component
from ..xdl import XDL
from ..utils.xdl_base import XDLBase
from ..platforms import PlaceholderPlatform


class BaseBlueprint(XDLBase):
    """Base blueprint class.
    """

    def __init__(self, props):
        super().__init__(props)

    def build(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Return steps and reagents for this stage of the procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []


class BaseProcedureBlueprint(BaseBlueprint):
    """Template for entire single-reaction-step synthetic procedures.
    """

    def __init__(self, props):
        super().__init__(props)

    def build_prep(self) -> Tuple[List[Step], List[Reagent]]:
        """Compile preparation steps and reagents for the procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build_reaction(self) -> Tuple[List[Step], List[Reagent]]:
        """Compile reaction steps and reagents for the procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build_workup(self) -> Tuple[List[Step], List[Reagent]]:
        """Compile workup steps and reagents for the procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build_purification(self) -> Tuple[List[Step], List[Reagent]]:
        """Compile purification steps and reagents for the procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build(self) -> Tuple[List[Step], List[Reagent]]:
        """Compile all procedure steps and reagents.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        prep_steps, prep_reagents = self.build_prep()
        reaction_steps, reaction_reagents = self.build_reaction()
        workup_steps, workup_reagents = self.build_workup()
        purification_steps, purification_reagents = self.build_purification()
        steps = {
            'prep': prep_steps,
            'reaction': reaction_steps,
            'workup': workup_steps,
            'purification': purification_steps,
            'no_section': [],
        }
        reagents = (
            prep_reagents
            + reaction_reagents
            + workup_reagents
            + purification_reagents
        )
        return steps, reagents

    def build_xdl(self, save: str = None) -> XDL:
        """Build XDL object and save to file if save path given.

        Arguments:
            save (str): File path to save .xdl file to.

        Returns:
            XDL: XDL object of built procedure.
        """
        steps, reagents = self.build()

        x = XDL(steps=steps, reagents=reagents, hardware=[
            Component(id="reactor", component_type="reactor"),
            Component(id="rotavap", component_type="rotavap"),
            Component(id="separator", component_type="separator"),
            Component(id="product", component_type="flask"),
            Component(id="buffer_flask", component_type="flask"),
        ], platform=PlaceholderPlatform)

        if save:
            x.save(save)

        return x


class BasePrepBlueprint(BaseBlueprint):
    """Template for preparation procedures.
    """

    def __init__(self, props):
        super().__init__(props)

    def build_prep(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Build prep stage of procedure. Add reagents.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Return steps and reagents for this stage of the procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        prep_steps, prep_reagents = self.build_prep()

        return prep_steps, prep_reagents


class BaseReactionBlueprint(BaseBlueprint):
    """Template for reaction procedures.
    """

    def __init__(self, props):
        super().__init__(props)

    def build_reaction(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Build reaction stage of procedure. Heat reaction mixture.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build(self) -> Tuple[List[Step], List[Reagent]]:
        """Compile Reagents and Steps for all reaction stages and return
        them to be incorporated into XDL procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        reaction_steps, reaction_reagents = self.build_reaction()

        return reaction_steps, reaction_reagents


class BaseWorkupBlueprint(BaseBlueprint):
    """Template for workup procedures.
    """

    def __init__(self, props):
        super().__init__(props)

    def build_filter(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Build filtration stage of workup.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build_extraction(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Build extraction stage of workup.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build_wash(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Build washing stage of workup.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build_dry(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Build drying stage of workup.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build(self) -> Tuple[List[Step], List[Reagent]]:
        """Compile Reagents and Steps for all workup stages and return
        them to be incorporated into XDL procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        filter_steps, filter_reagents = self.build_filter()
        extraction_steps, extraction_reagents = self.build_extraction()
        wash_steps, wash_reagents = self.build_wash()
        dry_steps, dry_reagents = self.build_dry()

        workup_steps = (
            filter_steps
            + extraction_steps
            + wash_steps
            + dry_steps
        )

        workup_reagents = (
            filter_reagents
            + extraction_reagents
            + wash_reagents
            + dry_reagents
        )

        return workup_steps, workup_reagents


class BasePurificationBlueprint(BaseBlueprint):
    """Template for purification procedures.
    """

    def __init__(self, props):
        super().__init__(props)

    def build_purification(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Build purification stage of procedure. E.g. Run column, distill...

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        return [], []

    def build(self) -> Tuple[List[Step], List[Reagent]]:
        """Abstract method, but not mandatory, can just return empty lists.
        Return steps and reagents for this stage of the procedure.

        Returns:
            Tuple[List[Step], List[Reagent]]: (steps, reagents) tuple.
        """
        purification_steps, purification_reagents = self.build_purification()

        return purification_steps, purification_reagents
