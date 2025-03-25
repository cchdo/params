import cchdo.params as data

# some params to play with
EXPOCODE = data.WHPNames["EXPOCODE"]
CTDPRS = data.WHPNames[("CTDPRS", "DBAR")]
CTDSAL = data.WHPNames[("CTDSAL", "PSS-78")]
SALNTY = data.WHPNames[("SALNTY", "PSS-78")]

CTDTMP_90 = data.WHPNames[("CTDTMP", "ITS-90")]
CTDTMP_68 = data.WHPNames[("CTDTMP", "IPTS-68")]


def test_ordering():
    # These are some historic orderings
    assert EXPOCODE < CTDPRS
    assert CTDPRS > EXPOCODE
    assert CTDSAL < SALNTY


def test_ordering_fallback():
    # If things have the same rank, break tie with lex sort on units
    assert CTDTMP_68 < CTDTMP_90


def test_arr_sort():
    expected = [
        EXPOCODE,
        CTDPRS,
        CTDSAL,
        SALNTY,
    ]

    unordered = [
        SALNTY,
        CTDPRS,
        EXPOCODE,
        CTDSAL,
    ]

    assert expected != unordered
    assert expected == sorted(unordered)
