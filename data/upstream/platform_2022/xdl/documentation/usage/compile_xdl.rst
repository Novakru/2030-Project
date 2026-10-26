Compile XDL
===========

Python
******

Once you have a XDL procedure and a compatible graph, they can be compiled into
a .xdlexe file.

.. code-block:: python

    from xdl import XDL

    # Example assumes you have previously created files 'procedure.xdl' and
    # 'procedure_graph.json'.

    x = XDL('procedure.xdl')

    # Produces executable file named 'procedure.xdlexe'.
    xdl_obj.prepare_for_execution('procedure_graph.json')

ChemIDE
*******

XDL procedures can also be compiled using ChemIDE. To do this you must load a XDL
procedure, and also generate or load a graph. You can see if a graph is loaded
by switching to Graph Mode in the toolbar.

.. image:: assets/graph-mode-button.png
   :width: 400

To compile go to the actions menu and click "Compile".

.. image:: assets/compile-menu-button.png
   :width: 600

Here you have the option to upload a graph if you have not loaded one already.

.. image:: assets/compile-modal.png
   :width: 600

There are two options for compilation, one stage and two stage.

One stage compilation will give you a xdlexe file straight away and can be used by clicking
the "Compile" button.

Two stage compilation is useful if you want more control over the exact steps that will be executed.
The "Add Process Steps" button will map xdl vessels to graph vessels, add implicit steps such as cleaning steps,
and then take you back to the editor where you can review the procedure and make adjustments.
The "Basic Compile" button can then be used to generate a xdlexe file. The "Compile" button
is just the combination of these two stages without the option to adjust the procedure in between.