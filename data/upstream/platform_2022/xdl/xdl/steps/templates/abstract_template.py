from typing import Dict, Any
from xdl.utils.xdl_base import XDLBase
from ...errors import (
    XDLStepTemplateNameError,
    XDLStepTemplateMissingPropError,
    XDLStepTemplatePropTypeError,
    XDLStepTemplateMissingDefaultPropError,
    XDLStepTemplateInvalidDefaultPropError,
    XDLStepTemplateMissingPropLimitError,
    XDLStepTemplateInvalidPropLimitError,
)
from ...utils.prop_limits import PropLimit


class AbstractXDLElementTemplate(XDLBase):
    """Base class to create step templates such as ``AbstractAddStep``. Purpose
    of this class is to allow :py:attr:`MANDATORY_PROP_TYPES` to be defined for
    all generic step classes, e.g. ``Add``, ``Filter`` etc. Then platform
    specific implemenations of these steps can inherit this class and have this
    class will validate that  they support the mandatory properties. This should
    ensure interoperability between platforms, if scripts are written according
    to the standard defined by the mandatory properties of the step templates.
    Extra properties will be allowed as before, but will have no guarantee of
    interoperability between platforms.

    Raises:
        XDLStepTemplateMissingPropError: Implementation is missing mandatory
            prop.
        XDLStepTemplatePropTypeError: Implementation has mandatory prop, but
            prop type is wrong.

    Attributes:
        MANDATORY_NAME (str): Name of step, e.g. 'Add', 'Filter'. Should be
            declared in any subclass.
        MANDATORY_PROP_TYPES (Dict[str, type]): Dict of prop types that step
            must have. An inheriting step can have extra props, as long as
            it has all the props declared here.
        MANDATORY_PROP_LIMITS (Dict[str, PropLimit]): Dict of prop limits
            that step must have. Not every prop has to have a prop limit.
        MANDATORY_DEFAULT_PROPS (Dict[str, Any]): Dict of default props. A value
            of ``None`` for a prop means that the prop should have a default
            value, but any default is acceptable.
    """

    # Mandatory class attributes to fill in when creating templates
    MANDATORY_NAME: str = ''
    MANDATORY_PROP_TYPES: Dict[str, type] = {}
    MANDATORY_PROP_LIMITS: Dict[str, PropLimit] = {}
    MANDATORY_DEFAULT_PROPS: Dict[str, Any] = {}

    def __init__(self, param_dict: Dict[str, Any]) -> None:
        """Validate that step implements all mandatory properties correctly and
        call ``super().__init__``.
        """
        self.validate()
        super().__init__(param_dict)

    def validate(self) -> None:
        """Validate step class conforms to standard in step template class."""
        self.validate_name()
        self.validate_prop_types()
        self.validate_default_props()
        self.validate_prop_limits()

    def validate_name(self) -> None:
        """Check step name is correct.

        Raises:
            XDLStepTemplateNameError: If implemented step name is not the same
                as :py:attr:`MANDATORY_NAME`.
        """
        if type(self).__name__ != self.MANDATORY_NAME:
            raise XDLStepTemplateNameError(
                self.MANDATORY_NAME, type(self).__name__)

    def validate_prop_types(self) -> None:
        """Validate that all mandatory props are present in prop types, and that
        they have the correct prop types.

        Raises:
            XDLStepTemplateMissingPropError: Mandatory prop is missing from prop
                types.
            XDLStepTemplatePropTypeError: Mandatory prop has the wrong prop
                type.
        """
        for prop, prop_type in self.MANDATORY_PROP_TYPES.items():

            # Check prop in PROP_TYPES
            if prop not in self.PROP_TYPES:
                raise XDLStepTemplateMissingPropError(
                    self.MANDATORY_NAME, prop, prop_type)

            # Check prop type is correct type
            elif prop_type != self.PROP_TYPES[prop]:
                raise XDLStepTemplatePropTypeError(
                    self.MANDATORY_NAME, prop, prop_type, self.PROP_TYPES[prop])

    def validate_default_props(self) -> None:
        """Validate that all mandatory default props are present and correct.

        Raises:
            XDLStepTemplateMissingDefaultPropError: Mandatory default prop
                from default props.
            XDLStepTemplateInvalidDefaultPropError: Mandatory default prop has
                wrong value in default props.
        """
        for prop, default_value in self.MANDATORY_DEFAULT_PROPS.items():

            # Check prop in DEFAULT_PROPS
            if prop not in self.DEFAULT_PROPS:
                raise XDLStepTemplateMissingDefaultPropError(
                    self.MANDATORY_NAME, prop, default_value)

            # Check default prop is correct. A mandatory default prop value of
            # None means that the implemented value can be anything.
            elif (default_value is not None
                    and self.DEFAULT_PROPS[prop] != default_value):
                raise XDLStepTemplateInvalidDefaultPropError(
                    self.MANDATORY_NAME,
                    prop,
                    default_value,
                    self.DEFAULT_PROPS[prop]
                )

    def validate_prop_limits(self) -> None:
        """Validate that all mandatory prop limits are implemented and have the
        correct values.

        Raises:
            XDLStepTemplateMissingPropLimitError: Mandatory prop limit missing
                from prop limits.
            XDLStepTemplateInvalidPropLimitError: Mandatory prop limit has wrong
                prop limit in prop limits.
        """
        for prop, prop_limit in self.MANDATORY_PROP_LIMITS.items():

            # Check prop in PROP_LIMITS
            if prop not in self.PROP_LIMITS:
                raise XDLStepTemplateMissingPropLimitError(
                    self.MANDATORY_NAME, prop, prop_limit)

            # Check prop limit is correct.
            elif self.PROP_LIMITS[prop] != prop_limit:
                raise XDLStepTemplateInvalidPropLimitError(
                    self.MANDATORY_NAME,
                    prop,
                    prop_limit,
                    self.PROP_LIMITS[prop]
                )
