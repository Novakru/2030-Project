import sys

###############
# Base Errors #
###############

class XDLError(Exception):
    """Base XDL error."""
    pass

class XDLGraphError(XDLError):
    """Graph related error."""
    pass

class XDLCompilationError(XDLError):
    """Error occurring during compilation."""
    pass

class XDLExecutionError(XDLError):
    """Error occurring during execution."""
    pass

class XDLValueError(XDLError):
    """Invalid value supplied."""
    pass

class XDLSanityCheckError(XDLError):
    """Step sanity check failed."""
    pass

#######################
# File I/O and Syntax #
#######################

class XDLInvalidFileTypeError(XDLError):
    """Tried to instantiate XDL with invalid file type."""

    def __init__(self, file_ext):
        self.file_ext = file_ext

    def __str__(self):
        return f'{self.file_ext} is an invalid XDL file type. Valid file\
 file types: .xdl, .xdlexe, .json'

class XDLInvalidSaveFormatError(XDLError):
    """Tried to save XDL with invalid file format."""

    def  __init__(self, file_format):
        self.file_format = file_format

    def  __str__(self):
        return f'"{self.file_format}" is an invalid file format for saving\
 XDL. Valid file formats: "xml", "json".'

class XDLVesselNotDeclaredError(XDLError):
    """Vessel used in procedure but not declared in Hardware section."""

    def __init__(self, vessel):
        self.vessel = vessel

    def __str__(self):
        return f'"{self.vessel}" used as vessel in procedure but not declared\
 in <Hardware> section of XDL'

class XDLReagentNotDeclaredError(XDLError):
    """Reagent used in procedure but not declared in Reagents section."""

    def __init__(self, reagent):
        self.reagent = reagent

    def __str__(self):
        return f'"{self.reagent}" used as reagent in procedure but not declared\
 in <Reagents> section of XDL'

class XDLFileNotFoundError(XDLError):
    """File given for loading xdl does not exist."""

    def __init__(self, file_name):
        self.file_name = file_name

    def __str__(self):
        return f'{self.file_name} does not exist.'

class XDLInvalidInputError(XDLError):
    """Object given to instantiate XDL is not a file path, XML XDL string or XDL
    JSON dict.
    """

    def __init__(self, input_str):
        self.input_str = input_str

    def __str__(self):
        return f'Cannot instantiate XDL from this. Invalid syntax.\
     \n\n{self.input_str}'

class XDLInvalidArgsError(XDLError):
    """Invalid combination of args given to XDL __init__."""

    def __str__(self):
        return 'Unable to initialise XDL object, invalid argument combination\
 given. Either xdl arg must be given with the name of a valid XDL\
 file or XDL string, or steps, reagents and hardware arguments must\
 all be given with lists of instantiated objects.'

#########
# Graph #
#########

class XDLGraphInvalidFileTypeError(XDLGraphError):
    """Invalid file type given for loading graph."""

    def __init__(self, graph_file):
        self.graph_file = graph_file

    def __str__(self):
        return f'Graph file "{self.graph_file}" has any invalid file type.\
 Valid file types: .json, .graphml'

class XDLGraphFileNotFoundError(XDLGraphError):
    """File path given for graph does not exist."""

    def __init__(self, graph_file):
        self.graph_file = graph_file

    def __str__(self):
        return f'Graph file "{self.graph_file}" does not exist.'

class XDLGraphTypeError(XDLGraphError):
    """Object with invalid type given to instantiate graph."""

    def __init__(self, graph_file):
        self.graph_file = graph_file

    def __str__(self):
        return f'{type(self.graph_file)} is not a valid type to load a graph\
 Accepted objects: Paths to .json or .graphml graph files. Contents of .json\
 graph as dict. Networkx MultiDiGraph.'

###############
# Compilation #
###############

class XDLDoubleCompilationError(XDLCompilationError):
    """User tries to compile the same XDL object twice."""

    def __str__(self):
        return 'Cannot compile same XDL object twice.'

#############
# Execution #
#############

class XDLInvalidPlatformControllerError(XDLExecutionError):
    """Invalid platform controller supplied."""

    def __init__(self, platform_controller):
        self.platform_controller = platform_controller

    def __str__(self):
        return f'Invalid platform controller supplied. Type:\
 {type(self.platform_controller)} Value: {self.platform_controller}'

class XDLExecutionBeforeCompilationError(XDLExecutionError):
    """User tries to execute xdl before compiling it."""

    def __str__(self):
        return 'Trying to execute procedure that has not been compiled. First\
 call xdl_obj.prepare_for_execution(graph).'

class XDLDurationBeforeCompilationError(XDLExecutionError):
    """User tries to calculate duration before compiling procedure."""

    def __str__(self):
        return 'Trying to calculate duration for procedure that has not been\
 compiled. First call xdl_obj.prepare_for_execution(graph).'

class XDLReagentVolumesBeforeCompilationError(XDLExecutionError):
    """User tries to calculate reagents volumes used before compiling
    procedure.
    """

    def __str__(self):
        return 'Trying to calculate reagent volumes for procedure that has not\
 been compiled. First call xdl_obj.prepare_for_execution(graph).'

class XDLExecutionOnDifferentGraphError(XDLExecutionError):
    """User tries to execute XDL using different graph than the one used to
    compile it.
    """

    def __str__(self):
        return 'Trying to execute XDL on different graph than the one it was\
 compiled with.'

########
# Misc #
########

class XDLStepIndexError(XDLError):
    """User supplies a step index out of bounds of step list."""

    def __init__(self, step_index, len_steps):
        self.step_index = step_index
        self.len_steps = len_steps

    def __str__(self):
        return f'{self.step_index} is out of bounds for step list with length\
 {self.len_steps}'

class XDLStepNotInStepsListError(XDLError):
    """When user asks to execute a step object that isn't in ``xdl_obj.steps``.
    """
    def __init__(self, step):
         self.step = step

    def __str__(self):
        return f'Given step not found in steps list.\n\n\
{self.step.name}\n{self.step.properties}'

class XDLInvalidPlatformError(XDLError):
    """User supplies an invalid platform."""

    def __init__(self, platform):
        self.platform = platform

    def __str__(self):
        return f'{self.platform} is an invalid platform. Platform must\
 be "chemputer" or a subclass of AbstractPlatform.'

class XDLLanguageUnavailableError(XDLError):
    """User requests human readable in a language that is unavailable."""

    def __init__(self, language, available_languages=None):
        self.language = language
        self.available_languages = available_languages

    def __str__(self):
        s = f'Language {self.language} not supported.'
        if self.available_languages is not None:
            s += f'Available languages: {", ".join(self.available_languages)}'
        return s

class XDLInvalidStepsTypeError(XDLError):
    def __init__(self, steps_type):
        self.steps_type = steps_type

    def __str__(self):
        return (f'Invalid type for steps: {self.steps_type}\n'
                 'Valid types: List or Dict with steps sections.')

class XDLUnimplementedStepError(XDLCompilationError):
    def __init__(self, step_name: str) -> None:
        self.step_name = step_name

    def __str__(self):
        return f'"{self.step_name}" is an unimplemented step.\
 Unable to compile.'

##################
# Step Templates #
##################

class XDLStepTemplateError(XDLError):
    """Error related to abstract step templates."""
    pass

class XDLStepTemplateMissingPropError(XDLStepTemplateError):
    """Step implementation missing mandatory prop."""

    def __init__(self, name, prop, prop_type):
        self.name = name
        self.prop = prop
        self.prop_type = prop_type

    def __str__(self):
        return f'"{self.name}" step template requires an "{self.prop}"\
 ({self.prop_type}) property, but this has not been found in PROP_TYPES.'

class XDLStepTemplatePropTypeError(XDLStepTemplateError):
    """Step implementation has an invalid prop type."""

    def __init__(self, name, prop, prop_type, invalid_prop_type):
        self.name = name
        self.prop = prop
        self.prop_type = prop_type
        self.invalid_prop_type = invalid_prop_type

    def __str__(self):
        return f'"{self.name}" step template requires that "{self.prop}" has\
 prop type {str(self.prop_type)}. Prop type found is\
 {str(self.invalid_prop_type)}.'

class XDLStepTemplateMissingDefaultPropError(XDLStepTemplateError):
    """Step implementation missing mandatory default prop."""

    def __init__(self, name, prop, default_prop):
        self.name = name
        self.prop = prop
        self.default_prop = default_prop

    def __str__(self):
        return f'"{self.name}" step template requires that "{self.prop}"\
 has a default value of {self.default_prop}, but this has not been found in\
 DEFAULT_PROPS.'

class XDLStepTemplateInvalidDefaultPropError(XDLStepTemplateError):
    """Step implementation has invalid default prop."""

    def __init__(self, name, prop, default_prop, invalid_default_prop):
        self.name = name
        self.prop = prop
        self.default_prop = default_prop
        self.invalid_default_prop = invalid_default_prop

    def __str__(self):
        return f'"{self.name}" step template requires that "{self.prop}" has\
 has a default value of {str(self.default_prop)}. Default value found is\
 {str(self.invalid_default_prop)}.'

class XDLStepTemplateMissingPropLimitError(XDLStepTemplateError):
    """Step implementation missing mandatory prop limit."""

    def __init__(self, name, prop, prop_limit):
        self.name = name
        self.prop = prop
        self.prop_limit = prop_limit

    def __str__(self):
        return f'"{self.name}" step template requires that "{self.prop}"\
 has prop_limit {self.prop_limit}, but this has not been found in\
 PROP_LIMITS.'

class XDLStepTemplateInvalidPropLimitError(XDLStepTemplateError):
    """Step implementation has invalid prop limit."""

    def __init__(self, name, prop, prop_limit, invalid_prop_limit):
        self.name = name
        self.prop = prop
        self.prop_limit = prop_limit
        self.invalid_prop_limit = invalid_prop_limit

    def __str__(self):
        return f'"{self.name}" step template requires that "{self.prop}" has\
 has a prop limit {str(self.prop_limit)}. Prop limit found is\
 {str(self.invalid_prop_limit)}.'

class XDLStepTemplateNameError(XDLStepTemplateError):
    """Step implementation has invalid name."""

    def __init__(self, mandatory_name, name):
        self.mandatory_name = mandatory_name
        self.name = name

    def __str__(self):
        return f'{self.mandatory_name} step must have class name\
 {self.mandatory_name}. Name found: {self.name}.'

##############
# Prop Types #
##############

class XDLUndeclaredDefaultPropError(XDLError):
    """Prop included in ``DEFAULT_PROPS`` but not in ``PROP_TYPES``."""

    def __init__(self, step_name, prop):
        self.step_name = step_name
        self.prop = prop

    def __str__(self):
        return f'{self.step_name} step class has {self.prop} in DEFAULT_PROPS\
 but not in PROP_TYPES.'

class XDLUndeclaredPropLimitError(XDLError):
    """Prop included in ``PROP_LIMITS`` but not in ``PROP_TYPES``."""

    def __init__(self, step_name, prop):
        self.step_name = step_name
        self.prop = prop

    def __str__(self):
        return f'{self.step_name} step class has {self.prop} in PROP_LIMITS\
 but not in PROP_TYPES.'

class XDLUndeclaredInternalPropError(XDLError):
    """Prop included in ``INTERNAL_PROPS`` but not in ``PROP_TYPES``."""

    def __init__(self, step_name, prop):
        self.step_name = step_name
        self.prop = prop

    def __str__(self):
        return f'{self.step_name} step class has {self.prop} in INTERNAL_PROPS\
 but not in PROP_TYPES.'

class XDLUndeclaredAlwaysWriteError(XDLError):
    """Prop included in ``ALWAYS_WRITE`` but not in ``PROP_TYPES``."""

    def __init__(self, step_name, prop):
        self.step_name = step_name
        self.prop = prop

    def __str__(self):
        return f'{self.step_name} step class has {self.prop} in ALWAYS_WRITE\
 but not in PROP_TYPES.'

class XDLMissingDefaultPropError(XDLError):
    """``'default'`` given as value for prop but prop not in ``DEFAULT_PROPS``.
    """

    def __init__(self, xdl_element_name, prop):
        self.xdl_element_name = xdl_element_name
        self.prop = prop

    def __str__(self):
        return f'"default" given as value for {self.prop} property, but no\
 default value found in {self.xdl_element_name} DEFAULT_PROPS.'

class XDLMissingPropTypeError(XDLError):
    """Value given for prop but prop not in ``PROP_TYPES``."""

    def __init__(self, xdl_element_name, prop):
        self.xdl_element_name = xdl_element_name
        self.prop = prop

    def __str__(self):
        return f'Missing prop type for {self.prop} in {self.xdl_element_name}\
 class.'

class XDLFailedPropLimitError(XDLValueError):
    """Value given for prop does not match prop limit."""

    def __init__(self, xdl_element_name, prop, value, prop_limit):
        self.xdl_element_name = xdl_element_name
        self.prop = prop
        self.value = value
        self.prop_limit = prop_limit

    def __str__(self):
        return f'{self.xdl_element_name}: Value "{self.value}" does not match\
 "{self.prop}" prop limit. {self.prop_limit.hint}'

class XDLTypeConversionError(XDLValueError):
    """Error occurred converting value to prop type."""

    def __init__(self, xdl_element_name, prop, prop_type, value):
        self.xdl_element_name = xdl_element_name
        self.prop = prop
        self.value = value
        self.prop_type = prop_type

    def __str__(self):
        return f'{self.xdl_element_name}: Unable to convert {self.prop} value\
 {self.value} to {self.prop_type}.'
