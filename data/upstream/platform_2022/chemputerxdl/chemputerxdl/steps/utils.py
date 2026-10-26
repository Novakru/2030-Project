"""
.. module:: steps.utils
    :platforms: Unix, Windows
    :synopsis: General utilities used in XDL steps

"""

from typing import List, Optional
from xdl.steps.base_steps import Step
from .steps_base import CConnect, CValveMoveToPosition

def get_vacuum_valve_reconnect_steps(
    vessel: str,
    inert_gas: str,
    vacuum_valve: str,
    valve_unused_port: str
) -> Optional[List[Step]]:
    """Reconnects the vacuum valve from inert gas to vessel

    Args:
        vessel (str): Target vessel
        inert_gas (str): Inert gas line
        vacuum_valve (str): Valve attached to vacuum
        valve_unused_port (str): Unused port on vacuum valve

    Returns:
        Optional[List[Step]]: Reconnection steps, none if no vacuum source
    """

    # Using inert gas line, connect
    if inert_gas:
        return [
            CConnect(
                from_vessel=inert_gas,
                to_vessel=vessel
            )
        ]

    # Using vacuum valve, move vacuum valve to vacuum
    elif vacuum_valve:
        return [
            CValveMoveToPosition(
                valve_name=vacuum_valve, position=valve_unused_port
            )
        ]

    # Not required
    return []
