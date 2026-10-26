import pprint

class VesselSpec(object):
    def __init__(
        self,
        filter: bool = False,
        stir: bool = False,
        evaporate: bool = False,
        separate: bool = False,
        vacuum: bool = False,
        irradiate: bool = False,
        inert_gas: bool = False,
        min_temp: float = None,
        max_temp: float = None,
    ):
        self.filter = filter
        self.stir = stir
        self.evaporate = evaporate
        self.separate = separate
        self.vacuum = vacuum
        self.inert_gas = inert_gas
        self.irradiate = irradiate
        self.min_temp = min_temp
        self.max_temp = max_temp

    def __add__(self, other):
        # Get bool flags
        filter = self.filter or other.filter
        evaporate = self.evaporate or other.evaporate
        separate = self.separate or other.separate
        vacuum = self.vacuum or other.vacuum
        inert_gas = self.inert_gas or other.inert_gas
        irradiate = self.irradiate or other.irradiate
        stir = self.stir or other.stir

        # Get min temperature
        if self.min_temp is None:
            if other.min_temp is None:
                min_temp = None
            else:
                min_temp = other.min_temp
        else:
            if other.min_temp is None:
                min_temp = self.min_temp
            else:
                min_temp = min(self.min_temp, other.min_temp)

        # Get max temperature
        if self.max_temp is None:
            if other.max_temp is None:
                max_temp = None
            else:
                max_temp = other.max_temp
        else:
            if other.max_temp is None:
                max_temp = self.max_temp
            else:
                max_temp = max(self.max_temp, other.max_temp)

        return VesselSpec(
            filter=filter,
            stir=stir,
            separate=separate,
            evaporate=evaporate,
            irradiate=irradiate,
            vacuum=vacuum,
            inert_gas=inert_gas,
            min_temp=min_temp,
            max_temp=max_temp
        )

    def __str__(self):
        pp = pprint.PrettyPrinter()
        return pp.pformat({
            'filter': self.filter,
            'stir': self.stir,
            'separate': self.separate,
            'evaporate': self.evaporate,
            'irradiate': self.irradiate,
            'vacuum': self.vacuum,
            'inert_gas': self.inert_gas,
            'min_temp': self.min_temp,
            'max_temp': self.max_temp
        })
