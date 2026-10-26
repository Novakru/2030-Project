=======================
Generate Graph from XDL
=======================

Python
******
.. code-block:: python

    from xdl import XDL

    xdl_obj = XDL('procedure.xdl')

    xdl_obj.graph('template_graph.json')

It is also okay just to do ``xdl_obj.graph()`` and the default template graph will
be used.

Generated graphs can be viewed and edited `here <https://croningroup.gitlab.io/chemputer/graphapp>`_.

ChemIDE
*******

Graphs can also be generated using ChemIDE. To do this load / create a XDL procedure,
then go to the Actions menu and click "Generate Graph".

.. image:: assets/graphgen-menu.png
   :width: 900

This will generate a graph,
and if the graph is generated successfully, it will be immediately opened in ChemIDE.
To save it go to the File menu and click "Export Graph".

.. image:: assets/graphgen-save.png
   :width: 900
