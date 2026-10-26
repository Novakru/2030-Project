# Std
from typing import List, Dict, Any, Tuple
import copy
import uuid

# Other
from networkx import MultiDiGraph

# Relative
from ..utils import FTNDuration
from ...localisation import LOCALISATIONS
from ...utils import XDLBase
from ...utils.localisation import conditional_human_readable
from ...utils.misc import format_property, SanityCheck
from ...utils.vessels import VesselSpec
from ...errors import (
    XDLUndeclaredDefaultPropError,
    XDLUndeclaredAlwaysWriteError,
    XDLUndeclaredInternalPropError,
    XDLUndeclaredPropLimitError
)


class Step(XDLBase):
    """Base class for all step objects.

    Attributes:
        properties (dict): Dictionary of step properties. Should be implemented
            in step ``__init__`` method.
        uuid (str): Step unique universal identifier, generated automatically.
        localisation: Dict[str, str]: Provides localisation for all steps
            specified by the XDL cross platform templates. Can be overridden if
            localisation needed for other steps or steps do not conform to cross
            platform standard.

    Args:
        param_dict (Dict[str, Any]): Step properties dict to initialize step
            with.
    """

    # This provides localisation for all steps specified by the XDL cross
    # platform templates. Can be overridden if localisation needed for other
    # steps or steps do not conform to cross platform standard.
    localisation: Dict[str, str] = LOCALISATIONS

    def __init__(self, param_dict: Dict[str, Any]) -> None:
        super().__init__(param_dict)

        self.uuid = str(uuid.uuid4())

        # Validate prop types
        self._validate_prop_types()
        self._validated_prop_types = True

    def _validate_prop_types(self):
        """Make sure that all props specified in ``DEFAULT_PROPS``, ``INTERNAL_PROPS``,
        ``ALWAYS_WRITE`` and ``PROP_LIMITS`` are specified in ``PROP_TYPES``.

        Raises:
            XDLUndeclaredDefaultPropError: Prop used in ``DEFAULT_PROPS`` that
                is not in ``PROP_TYPES``.
            XDLUndeclaredInternalPropError: Prop used in ``INTERNAL_PROPS`` that
                is not in ``PROP_TYPES``.
            XDLUndeclaredPropLimitError: Prop used in ``PROP_LIMITS`` that is
                not in ``PROP_TYPES``.
            XDLUndeclaredAlwaysWriteError: Prop used in ``ALWAYS_WRITE`` that is
                not used in ``PROP_TYPES``.
        """
        # Default Props
        for default_prop in self.DEFAULT_PROPS:
            if default_prop not in self.PROP_TYPES:
                raise XDLUndeclaredDefaultPropError(self.name, default_prop)

        # Internal Props
        for internal_prop in self.INTERNAL_PROPS:
            if internal_prop not in self.PROP_TYPES:
                raise XDLUndeclaredInternalPropError(self.name, internal_prop)

        # Prop Limits
        for prop_limit in self.PROP_LIMITS:
            if prop_limit not in self.PROP_TYPES:
                raise XDLUndeclaredPropLimitError(self.name, prop_limit)

        # Always Write
        for always_write in self.ALWAYS_WRITE:
            if always_write not in self.PROP_TYPES:
                raise XDLUndeclaredAlwaysWriteError(self.name, always_write)

    def on_prepare_for_execution(self, graph: MultiDiGraph) -> None:
        """Abstract method to be overridden with logic to set internal
        properties during procedure compilation. Doesn't use ``@abstractmethod``
        decorator as it's okay to leave this blank if there are no internal
        properties.

        This method is called during procedure compilation. Sanity checks are
        called after this method, and are there to validate the internal
        properties added during this stage.

        Args:
            graph (MultiDiGraph): networkx MultiDiGraph of graph that procedure
                is compiling to.
        """
        pass

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Abstract methods that should return a list of ``SanityCheck`` objects
        to be checked by final_sanity_check. Not compulsory so not using
        ``@abstractmethod`` decorator.
        """
        return []

    def final_sanity_check(self, graph: MultiDiGraph) -> None:
        """Run all ``SanityCheck`` objects returned by ``sanity_checks``. Can be
        extended if necessary but ``super().final_sanity_check()`` should always
        be called.
        """
        for sanity_check in self.sanity_checks(graph):
            sanity_check.run(self)

    def formatted_properties(self) -> Dict[str, str]:
        """Return properties as dictionary of ``{ prop: formatted_val }``.
        Used when generating human readables.
        """
        # Copy properties dict
        formatted_props = copy.deepcopy(self.properties)

        # Add formatted properties for all properties
        for prop, val in formatted_props.items():

            # Ignore children
            if prop != 'children':
                formatted_props[prop] = format_property(
                    prop,
                    val,
                    self.PROP_TYPES[prop],
                    self.PROP_LIMITS.get(prop, None),
                )

            # Convert None properties to empty string
            if formatted_props[prop] in ['None', None]:
                formatted_props[prop] = ''

        return formatted_props

    def human_readable(self, language: str = 'en') -> str:
        """Return human readable sentence describing step.

        Args:
            language (str): Language code for human readable sentence. Defaults
                to ``'en'``.

        Returns:
            str: Human readable sentence describing actions taken by step.
        """
        # Look for step name in localisation dict
        if self.name in self.localisation:

            # Get human readable template from localisation dict
            step_human_readables = self.localisation[self.name]
            if language in step_human_readables:
                language_human_readable = step_human_readables[language]

                # Traditional human readable template strings
                if type(language_human_readable) == str:

                    # If step has a comment add comment to template.
                    if self.comment:
                        language_human_readable += '. {comment}'

                    return language_human_readable.format(
                        **self.formatted_properties()) + '.'

                # New conditional JSON object human readable format
                else:
                    # If step has a comment add comment to template.
                    if self.comment:
                        language_human_readable['full'] += '. {comment}'

                    return conditional_human_readable(
                        self, language_human_readable)

        # Return step name as a fallback if step not in localisation dict
        return self.name

    def scale(self, scale: float) -> None:
        """Method to override to handle scaling if procedure is scaled.
        Should update step properties accordingly with given scale. Doesn't
        need to do/return anything.

        Args:
            scale (float): Scale factor to scale step by.
        """
        return

    def reagents_consumed(self, graph: MultiDiGraph) -> Dict[str, float]:
        """Method to override if step consumes reagents. Used to recursively
        calculate volume of reagents consumed by procedure.

        Args:
            graph (MultiDiGraph): Graph to use when calculating volume of
                reagents consumed by step.

        Returns:
            Dict[str, float]: Dict of volumes of reagents consumed in format
            ``{ reagent_id: volume_consumed... }``.
        """
        return {}

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Method to override to give approximate duration of step. Used to
        recursively determine duration of procedure.

        Args:
            graph (MultiDiGraph): Graph to use when calculating step duration.

        Returns:
            FTNDuration: Estimated duration of step in seconds as FTN.
        """
        # Default duration for steps that don't override this method. Duration
        # used is an estimate of the duration of steps that are virtually
        # instantaneous, such as starting stirring.
        return FTNDuration(0.5, 1, 2)

    def locks(self, platform_controller: Any) -> Tuple[List]:
        """WIP: Abstract method used by parallelisation.

        Returns locks, ongoing_locks and unlocks. Locks are nodes that are used
        while the step is executing. Ongoing locks are nodes that will be in use
        indefinitely after the step has finished (e.g. a vessel that the
        reaction mixture has been added to). Unlocks are nodes that are no
        longer being used after the step has finished (e.g. a vessel that the
        reaction mixture has been removed from).

        Args:
            platform_controller (Any): Platform controller to use for
                calculating which nodes in graph are used by step.

        Returns:
            Tuple[List]: Tuple of step lock changes in format
            ``(locks, ongoing_locks, unlocks)``.
        """
        return [], [], []

    def acquire_locks(self, platform_controller: Any, pid: str = None):
        return

    def release_locks(self, platform_controller: Any, pid: str = None):
        return

    @property
    def name(self) -> str:
        """Get class name."""
        return type(self).__name__

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        """Return dictionary of required specifications of vessels used by the
        step. ``{ prop_name: vessel_spec... }``

        Returns:
            Dict[str, VesselSpec]: Dict of required specification of vessels
            used by the step. Should be overridden if the step has any special
            requirement on a vessel used.
        """
        return {}

    @property
    def requirements(self) -> Dict:
        """Return dictionary of requirements of vessels used by the step.
        Currently only used bySynthReader. This will soon be deprecated and
        completely replaced by ``vessel_specs``.
        """
        return {}

    def __eq__(self, other: Any) -> bool:
        """Allow ``step == other_step`` comparisons."""

        # Different type, not equal
        if type(other) != type(self):
            return False

        # Different name, not equal
        if other.name != self.name:
            return False

        # Different length of properties, not equal
        if len(self.properties) != len(other.properties):
            return False

        # Compare properties
        for k, v in other.properties.items():

            # Compare children
            if k == 'children':

                # Different length of children, not equal
                if len(v) != len(self.children):
                    return False

                # Compare individual children
                for i, other_child in enumerate(v):

                    # Children are different, not equal
                    if other_child != self.children[i]:
                        return False

            # Property key is not in self.properties, not equal
            elif k not in self.properties:
                return False

            # Different values for property, not equal
            elif v != self.properties[k]:
                return False

        # Passed all equality tests, steps are equal
        return True

    def __ne__(self, other: Any) -> bool:
        """Recommended to include this just to show that non equality has been
        considered and it is simply ``not __eq__(other)``.
        """
        return not self.__eq__(other)

    def __deepcopy__(self, memo):
        """Allow ``copy.deepcopy(step)`` to be called. Default deepcopy works,
        but not on Python 3.6, so that is what this is for. When Python 3.6 is
        not supported this can go.
        """
        # Copy children
        children = []
        if 'children' in self.properties and self.children:
            for child in self.children:
                children.append(child.__deepcopy__(memo))

        # Copy properties
        copy_props = {}
        for k, v in self.properties.items():
            if k != 'children':
                copy_props[k] = v

        if children:
            copy_props['children'] = children

        # Make new self
        copied_self = type(self)(**copy_props)

        return copied_self
