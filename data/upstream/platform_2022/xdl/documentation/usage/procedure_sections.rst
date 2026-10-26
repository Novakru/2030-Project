==================
Procedure Sections
==================

Steps within a XDL file can be grouped into four sections: Prep, Reaction, Workup and Purification.
Doing this can help with readability, and also make it clearer to other people using the file
what the purpose of different steps is. Using these sections is optional, but recommended
if your procedure maps well to them.

XML XDL
*******

To use them in XML XDL, simply add the corresponding section tags around any steps you
want to be in that section. The sections must be in the order listed above, although
not all sections have to be included. Steps without a section must be above all section tags.

Example
^^^^^^^

.. code-block:: xml

    <Procedure>

      <!-- Steps with no section here -->

      <Prep>

        <!-- Prep steps here -->

      </Prep>

      <Reaction>

        <!-- Reaction steps here -->

      </Reaction>

      <Workup>

        <!-- Workup steps here -->

      </Workup>

      <Purification>

        <!-- Purification steps here -->

      </Purification>

    </Procedure>


ChemIDE
^^^^^^^

Procedure sections can also be used in ChemIDE. If you load a XDL file that already uses
them, then they will be visible in ChemIDE and you can just drag steps between sections.

However, if you start with no procedure sections, they will not be displayed so you won'that
be able to drag steps between them. In this case, you can select the step section
in the step options menu.

.. image:: assets/select-step-section.jpg
   :width: 600
