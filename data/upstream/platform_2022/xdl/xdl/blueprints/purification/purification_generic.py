from ..base_blueprint import BasePurificationBlueprint

class GenericPurification(BasePurificationBlueprint):

    def __init__(self):
        super().__init__(locals())

    def build_purification(self):
        steps, reagents = [], []
        return steps, reagents
