from typing import List, Dict

def shift_usage_times(
    usage_times: Dict[str, List[List[int]]],
    shift: int
) -> Dict[str, List[List[int]]]:
    """Shift usage times dict by given amount. Returns a new dict leaving
    `usage_times` unaffected.

    Args:
        usage_times (Dict[str, List[List[int]]]): Usage times dict to shift.
        shift (int): Amount to shift all usage times by.

    Returns:
        Dict[str, List[List[int]]]: New usage times dict with all times shifted.
    """
    shifted_usage_times = {}
    for node, node_usage_times in usage_times.items():
        shifted_usage_times[node] = [
            (item[0] + shift, item[1] + shift) for item in node_usage_times]
    return shifted_usage_times
