Reagents
========

Reagents in the :code:`<Reagents />`  section of the XDL file can take various
properties, listed here.

+---------------------------------+---------------------------------------------------------------------------------------------------+
| Property                        | Description                                                                                       |
+=================================+===================================================================================================+
| **cleaning_solvent**            | If specified, will be used for cleaning backbone after this reagent is encountered.               |
+---------------------------------+---------------------------------------------------------------------------------------------------+
| **use_for_cleaning**            | Normally only common solvents used for cleaning. If True, reagent will also be used for cleaning. |
+---------------------------------+---------------------------------------------------------------------------------------------------+
| **cas**                         | Information only. CAS number.                                                                     |
+---------------------------------+---------------------------------------------------------------------------------------------------+
| **role**                        | Information only. 'catalyst', 'reagent', 'solvent' or 'substrate'.                                |
+---------------------------------+---------------------------------------------------------------------------------------------------+
| **stir**                        | Reagent should be stirred while in its reagent flask.                                             |
+---------------------------------+---------------------------------------------------------------------------------------------------+
| **temp**                        | Reagent should be kept at this temp while in its reagent flask.                                   |
+---------------------------------+---------------------------------------------------------------------------------------------------+
| **last_minute_addition**        | ID of another reagent that should be added to the reagent just before it is used.                 |
+---------------------------------+---------------------------------------------------------------------------------------------------+
| **last_minute_addition_volume** | Volume of last_minute_addition reagent to add.                                                    |
+---------------------------------+---------------------------------------------------------------------------------------------------+
| **preserve**                    | Reagent is valuable. Use minimum amounts (i.e. don't use for cleaning or filter dead volume)      |  
+---------------------------------+---------------------------------------------------------------------------------------------------+

Example
^^^^^^^

.. code-block:: xml

    <Reagents>

      <!-- Store reagent at 30°C with stirring. Clean backbone with DCM after every use. -->
      <Reagent
        id="choroacetylchloride"
        cleaning_solvent="DCM"
        temp="30°C"
        stir="True"
      />

      <Reagent
        id="DCM"
        cas="75092"
      />

      <!-- Don't use HFIP for cleaning. -->
      <Reagent
        id="HFIP"
        preserve="True"
      />

    </Reagents>
