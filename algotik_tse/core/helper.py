import datetime

from persiantools.jdatetime import JalaliDate


def date_fix(start: str=None, end: str=None, start_delta: [None, str]=None) -> (str, str):
    new_start = None
    new_end = None
    if start is not None and not '-' in start:
        start = start[:4] + "-" + start[4:6] + "-" + start[6:]
    if end is not None and not '-' in end:
        end = end[:4] + "-" + end[4:6] + "-" + end[6:]

    if start is not None:
        two_left_char_start = start[:2]
        if two_left_char_start in ["13", "14", "15"]:
            new_start = JalaliDate.to_gregorian(JalaliDate.fromisoformat(start)).isoformat()
        else:
            new_start = start
    if end is not None:
        two_left_char_end = end[:2]
        if two_left_char_end in ["13", "14", "15"]:
            new_end = JalaliDate.to_gregorian(JalaliDate.fromisoformat(end)).isoformat()
        else:
            new_end = end
    else:
        new_end = end
    return new_start, new_end
