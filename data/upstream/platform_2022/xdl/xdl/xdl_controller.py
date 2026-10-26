import re
from .steps import (
    Step,
    AbstractStep,
    AbstractBaseStep,
    AbstractAsyncStep,
    AbstractDynamicStep
)
from .utils.graph import get_graph


def make_xdl_controller(platform):
    """Generates XDLController class. This is a class that has methods
    corresponding to all the XDL steps,
    e.g. xdl_controller.add(reagent='water', vessel='reactor', volume='10 mL')
    """

    class_name = 'XDLController'
    superclasses = ()
    attributes_dict = {
        '__init__': xdl_controller_init,
    }
    step_library = platform().step_library
    for step_name, step_class in step_library.items():
        # Exclude unrelated classes and abstract base step classes.
        if not issubclass(step_class, Step) and step_class not in [
            Step,
            AbstractStep,
            AbstractBaseStep,
            AbstractAsyncStep,
            AbstractDynamicStep
        ]:
            continue
        # Get snake case method name
        method_name = get_method_name(step_name)

        # If method name not already in attributes dict create method and
        # add to attributes dict.
        if method_name not in attributes_dict:
            # Define method. step_class must be defined as keyword argument
            # so that the current value of step_class is used. Not the
            # value of step_class when the method is called.
            def step_method(self, step_class=step_class, **kwargs):
                block = [step_class(**kwargs)]
                self.executor.add_internal_properties(
                    self.graph, steps=block)
                block[0].execute(self.platform_controller)

            # Add Method to attributes
            attributes_dict[method_name] = step_method
    return type(class_name, superclasses, attributes_dict)


def get_method_name(class_name):
    """Pascal case -> snake case"""
    return re.sub(r'(?<!^)([A-Z])', r'_\1', class_name).lower()


def xdl_controller_init(self, platform, platform_controller, graph_file):
    """Initialise XDL controller."""
    self.graph = get_graph(graph_file)
    self.platform = platform()
    self.executor = self.platform.executor()
    self.platform_controller = platform_controller

def XDLController(platform, platform_controller, graph_file):
    return make_xdl_controller(platform)(
        platform, platform_controller, graph_file)
