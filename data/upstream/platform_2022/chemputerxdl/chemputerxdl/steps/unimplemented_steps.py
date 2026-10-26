"""
.. module:: steps.unimplemented_steps
    :platforms: Unix, Windows
    :synopsis: Definition of steps yet to be implemented

"""

from xdl.steps.base_steps import UnimplementedStep

class Sonicate(UnimplementedStep):
    """Sonication step for using a sonicator
    """

    def __init__(self, **kwargs):
        super().__init__(locals())

class Distill(UnimplementedStep):
    """Distill step for distillation of products
    """

    def __init__(self, **kwargs):
        super().__init__(locals())

class Sublimate(UnimplementedStep):
    """Sublimate step for sublimation of products
    """

    def __init__(self, **kwargs):
        super().__init__(locals())

class Hydrogenate(UnimplementedStep):
    """Hydrogenate step for hydrogenation reactions
    """

    def __init__(self, **kwargs):
        super().__init__(locals())

class Irradiate(UnimplementedStep):
    """Irradiate step used in the Photoreactor module
    """

    def __init__(self, **kwargs):
        super().__init__(locals())
