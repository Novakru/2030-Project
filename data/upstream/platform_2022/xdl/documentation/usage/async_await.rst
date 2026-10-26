Async / Await
=============

The ``Async`` and ``Await`` steps allow tasks to be performed in parallel.

Anything within an ``Async`` block, will be run in a background thread, while
the steps after the ``Async`` block continue immediately. If at any point in the
procedure you wish to wait for an ``Async`` block to finish, you can use an
``Await`` step. An example of this is shown below, dissolving a solid and
heating another reactor at the same time, before transferring the solution into
the heated reactor.

WARNING: Using ``Async`` / ``Await`` opens up a lot of synchronisation issues
and race conditions. There are no checks that what you're doing won't
completely mess up, and it is your responsibility to make sure no resource is
accessed at the same time by two threads.

.. code-block:: xml

   <Synthesis>

     <Hardware>
       <Component
         id="reactor1"
         type="reactor"
       />
       <Component
         id="reactor2"
         type="reactor"
       />
     </Hardware>

     <Reagents>
       <Reagent
         id="water"
       />
     </Reagents>

     <Procedure>

       <!-- Start dissolving a solid in reactor1 -->
       <Async
         pid="dissolution"
       >
         <Dissolve
           vessel="reactor1"
           reagent="water"
           volume="20 mL"
         />
       </Async>

       <!-- While it is dissolving, heat the contents of reactor2 to 80°C -->
       <HeatChillToTemp
         vessel="reactor2"
         temp="80°C"
       />

       <!-- Wait for the Dissolve step to finish -->
       <Await
         pid="dissolution"
       />

       <!-- Transfer the dissolved solid from reactor1 to reactor2 -->
       <Transfer
         from_vessel="reactor1"
         to_vessel="reactor2"
         volume="all"
       />
     </Procedure>

   </Synthesis>



