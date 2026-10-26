========
XDL Base
========

This is an attempt at explaining the inheritance structure that XDL steps use.

In short there are 5 abstract step classes (listed below) which all inherit :code:`Step`,
which itself inherits :code:`XDLBase`.

:code:`AbstractDynamicStep` -> :code:`Step` -> :code:`XDLBase`

:code:`AbstractAsyncStep` -> :code:`Step` -> :code:`XDLBase`

:code:`AbstractBaseStep` -> :code:`Step` -> :code:`XDLBase`

:code:`AbstractStep` -> :code:`Step` -> :code:`XDLBase`

:code:`UnimplementedStep` -> :code:`Step` -> :code:`XDLBase`

:code:`XDLBase` is responsible for parsing all properties passed to :code:`__init__`.
This instantiates a dict :code:`self.properties` that contains all the values in
standard units.

It also gives access to the class name as :code:`self.name`.

So in the :code:`__init__` method of a step when the line :code:`super().__init__(locals())`
executes, all the arguments get added to the properties dictionaries in standard units,
i.e. :code:`'5 mL'` -> :code:`5`, :code:`'5 L'` -> :code:`5000`.

Standard units are mL, seconds, RPM, grams, °C and mbar.

Additionally, :code:`XDLBase` overrides :code:`__setattr__` and :code:`__getattr__` so
after :code:`super().__init__(locals())` is called in the step constructor, all
properties become available as member variables.

The final secret is that when a property is changed (e.g. :code:`self.time = '1 min'`)
the new value is parsed and converted to standard units, or if the new value is
:code:`'default'`, it will be replaced with the corresponding default value from
``DEFAULT_PROPS``.
