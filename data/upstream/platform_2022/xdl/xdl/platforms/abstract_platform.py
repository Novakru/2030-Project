from typing import Optional, Callable, Union, List, Dict, Any, Type
from networkx import MultiDiGraph
import json
import abc
from ..utils.schema import generate_schema
from ..execution.abstract_executor import AbstractXDLExecutor
from ..steps import Step, AbstractBaseStep
from ..reagents import Reagent
from ..hardware import Component
from ..metadata import Metadata
from ..localisation import LOCALISATIONS
if False:
    from ..xdl import XDL

class AbstractPlatform(object):
    """Container class to hold everything necessary for a platform to be used
    with the XDL framework.

    The idea here is that if you want your platform to be able to execute XDL
    files that you can fill in all the blanks defined in this abstract class and
    then do ``xdl_obj = XDL('procedure.xdl', platform=MyPlatform)``.
    """
    def __init__(self):
        pass

    @property
    @abc.abstractmethod
    def executor(self) -> Type[AbstractXDLExecutor]:
        """This should return the executor class for the platform. Details of
        what specifically the executor class should do can be found in the
        :py:class:`AbstractXDLExecutor` documentation.

        Returns:
            Type[AbstractXDLExecutor]: Executor class for the platform.
        """
        return None

    @property
    @abc.abstractmethod
    def step_library(self) -> Dict[str, Type[Step]]:
        """Collection of steps associated with the platform. Should take the
        form of a mapping between step class names and step classes, e.g.
        ``{ 'Add': Add, 'Stir': Stir... }``

        Returns:
            Dict[str, Type[Step]]: Collections of steps associated with platform
            in form ``{ step_name: step_type... }``
            e.g. ``{ 'Add': Add... }``.
        """
        return None

    @abc.abstractmethod
    def graph(
        self,
        xdl_obj: 'XDL',
        template: Optional[str] = None,
        save: Optional[str] = None,
        auto_fix_issues: Optional[bool] = True,
        ignore_errors: Optional[List[int]] = []
    ) -> MultiDiGraph:
        """Method to generate graph for given procedure.

        Args:
            xdl_obj (XDL): XDL object
            template (Optional[str]): Optional template graph to use when
                generating procedure graph.

            save (Optional[str]): Optional path to save generated graph to.

        Returns:
            MultiDiGraph: Graph that can be used to compile ``xdl_obj``.
        """
        return None

    @property
    def schema(self) -> str:
        """Generate platform specific XML schema for XDL files using platform
        steps.

        Returns:
            str: XML schema for platform XDL files.
        """
        return generate_schema(self.step_library)

    @property
    def localisation(self) -> Dict[str, Dict[str, Union[str, Dict]]]:
        """Return human readable sentence templates for step types. Should be in
        the form ``{ step_name: { language_code: template... }... }``,
        e.g. ``{ 'Add': {'en': '{reagent} was added'} }``.

        This implementation provides localisations for all standard XDL steps.
        It is recommended to provide localisations for non-standard platform
        specific steps also. In this case this can be overridden, but the method
        should begin with ``localisations = super().localisation()``.

        Returns:
            Dict[str, Dict[str, Union[str, Dict]]]: Dict of human readable
            sentence templates for steps in different languages in format
            described above.
        """
        return LOCALISATIONS

    @property
    def declaration(self) -> Dict[str, Any]:
        """Return declaration of the XDL namespace provided by this platform.
        This is fundamental to ChemIDE, as it provides a JSON detailing the prop
        specification of every step / XDL element of a given platform. Should
        not need to be overridden.

        Returns:
            Dict[str, Any]: Declaration of platform XDL namespace with full
            details of all props.
        """
        type_str_dict = {
            'reagent': 'reagent',
            'vessel': 'vessel',
            str: 'str',
            int: 'int',
            float: 'float',
            bool: 'bool',
            Callable: 'func',
            Union[str, int]: 'str or int',
            List[str]: 'List[str]',
            Union[bool, str]: 'bool or str',
            Union[Step, List[Step]]: 'List[Step] or Step',
            List[Any]: 'List[Any]',
            Dict[str, Any]: 'Dict[str, Any]',
        }

        def get_type_str(prop_type: type) -> str:
            """Return str corresponding to prop type, e.g. str -> 'str'."""
            if prop_type in type_str_dict:
                return type_str_dict[prop_type]
            else:
                return str(prop_type).replace('.typing', '')

        # Return platform declaration adding global comment property to every
        # XDL element.
        return {
            'steps': [
                {
                    'name': step_name,
                    'is_base_step': issubclass(step, AbstractBaseStep),
                    'PROP_TYPES': dict(
                        {
                            prop: get_type_str(prop_type)
                            for prop, prop_type in step.PROP_TYPES.items()
                        },
                        **{'comment': 'str'}
                    ),
                    'DEFAULT_PROPS': dict(
                        step.DEFAULT_PROPS, **{'comment': ''}),
                    'INTERNAL_PROPS': step.INTERNAL_PROPS,
                    'ALWAYS_WRITE': step.ALWAYS_WRITE,
                    'PROP_LIMITS': {
                        prop: {
                            'regex': prop_limit.regex,
                            'enum': prop_limit.enum,
                            'hint': prop_limit.hint,
                            'default': prop_limit.default,
                        }
                        for prop, prop_limit in step.PROP_LIMITS.items()
                    },
                    'localisation': self.localisation.get(step_name, {})
                }
                for step_name, step in self.step_library.items()
                if (hasattr(step, 'PROP_TYPES')
                    and not step_name.startswith('Abstract')
                    and step_name not in ['Step', 'UnimplementedStep'])
            ],
            'Reagent': {
                'name': 'Reagent',
                'PROP_TYPES': dict(
                    {
                        k: type_str_dict[v]
                        for k, v in Reagent.PROP_TYPES.items()
                    },
                    **{'comment': 'str'},
                ),
                'DEFAULT_PROPS': dict(
                    Reagent.DEFAULT_PROPS, **{'comment': ''}),
                'INTERNAL_PROPS': Reagent.INTERNAL_PROPS,
                'ALWAYS_WRITE': Reagent.ALWAYS_WRITE,
                'PROP_LIMITS': {
                    prop: {
                        'regex': prop_limit.regex,
                        'enum': prop_limit.enum,
                        'hint': prop_limit.hint,
                        'default': prop_limit.default,
                    }
                    for prop, prop_limit in Reagent.PROP_LIMITS.items()
                }
            },
            'Component': {
                'name': 'Component',
                'PROP_TYPES': dict(
                    {
                        k: type_str_dict[v]
                        for k, v in Component.PROP_TYPES.items()
                    },
                    **{'comment': 'str'}
                ),
                'DEFAULT_PROPS': dict(
                    Component.DEFAULT_PROPS, **{'comment': ''}),
                'INTERNAL_PROPS': Component.INTERNAL_PROPS,
                'ALWAYS_WRITE': Component.ALWAYS_WRITE,
                'PROP_LIMITS': {
                    prop: {
                        'regex': prop_limit.regex,
                        'enum': prop_limit.enum,
                        'hint': prop_limit.hint,
                        'default': prop_limit.default,
                    }
                    for prop, prop_limit in Component.PROP_LIMITS.items()
                }
            },
            'Metadata': {
                'name': 'Metadata',
                'PROP_TYPES': dict(
                    {
                        k: type_str_dict[v]
                        for k, v in Metadata.PROP_TYPES.items()
                    },
                    **{'comment': 'str'}
                ),
                'DEFAULT_PROPS': dict(
                    Metadata.DEFAULT_PROPS, **{'comment': ''}),
                'INTERNAL_PROPS': Metadata.INTERNAL_PROPS,
                'ALWAYS_WRITE': Metadata.ALWAYS_WRITE,
                'PROP_LIMITS': {
                    prop: {
                        'regex': prop_limit.regex,
                        'enum': prop_limit.enum,
                        'hint': prop_limit.hint,
                        'default': prop_limit.default,
                    }
                    for prop, prop_limit in Metadata.PROP_LIMITS.items()
                }
            }
        }

    def save_declaration(self, save_path: str) -> None:
        """Save platform declaration to given path.

        Args:
            save_path (str): Path to save platform declaration to.
        """
        with open(save_path, 'w') as fd:
            json.dump(self.declaration, fd, indent=2)
