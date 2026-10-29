"""The cmy spec vectors' tile literals, shared by test_cmy_vectors (which
derives them from the design text over the frozen reference machinery)
and test_cmy_emission (which finds them on an emitted page).

Typed from docs/CMY-DESIGN.md v0.3 before the build (docs/CMY-GENERATOR-
PLAN.md W0; design §11, G11); moved here from test_cmy_vectors at W2b
(2026-10-12) so no test module imports another.  A mismatch is a defect
in the code or in a premise, never a re-pin.
"""
from __future__ import annotations

STATE_ID = {"W": 0, "C": 1, "M": 2, "Y": 4}         # design §2.1

# §2.5 + R10: word bit 1 -> C; bit 0 -> Y iff the MSB of domain 9 (aux 0,
# major = counter, u = n_dust + site, v = 0) is set, else W.  §2.5 + R3 as
# amended: the dust sites go one at a time to the lowest running total
# from the tile's own word supply, ties M, Y, W, C; domain 9 at u < n_dust
# permutes that fill vector onto the dust sites (raster order).  Strings
# hold one letter per site; spaces are cosmetic.
TILES = {
    ("c2-cmy-r0700@10x10", 12): dict(
        words="CWYCWCYWCC CCWWCYCCCC CYCCYWCCWW WYWYYCYCYY CYYCYCCCWW "
              "WCCCYYWCYC YCWYWCCCYC CYYYCCCCWC YYCCCYCCWC YYCCCWYCYC",
        zero_mask="1010011010 1100010011 0100100100 0101101111 0110110100 "
                  "0111110111 1001001010 1111010101 1100010101 1111001111",
        supply={"C": 51, "W": 19, "Y": 30},
        dust="MMMMMMMMMM MMMMMMMMMM",
        dust_counts={"M": 20},
        words_sha256="7586af0430379b40a79296b53b6702a2"
                     "9bc04d80ed84d5435a12d8574ee21c0b",
    ),
    ("c2-cmy-r0700@10x10", 28): dict(
        words="CCCCYWYCCC CYYWCCCYYC CWCCYYCWCC YCCWCYYYCW YCYCCWCYYY "
              "CCCCCCCYWC CYCCCCCYCY CYCYWWYCWC WYCCCYCCYC CWCCCYWCWC",
        zero_mask="0010101010 1110101111 1011111010 1110111100 1010100111 "
                  "1110100101 0111001101 1111001000 0111010010 1010010100",
        supply={"C": 57, "W": 15, "Y": 28},
        dust="MMWMMMMMMW MMMMMMMMMM",
        dust_counts={"M": 18, "W": 2},
        words_sha256="80c94c90544364bc622f73c1e5321174"
                     "73070d5115bb1bc13f3a2f172009efd8",
    ),
    ("c2-cmy-r0700@10x10", 30): dict(
        words="CWWCCYCCYW WCWWYCYCYC CCCWCYCCWW WCCWWCWCWC CCYCWCWCWW "
              "CYWCWWWYWC WCWCCCWYCC CCCCYWWCWC WWCCCYCCWC CYCYCWYCWC",
        zero_mask="0001010110 0100101111 0000010100 0100010100 0010000100 "
                  "0100000100 0100000111 1001100000 0011011000 0101101101",
        supply={"C": 51, "W": 34, "Y": 15},
        dust="YMMMMMMMMM MMMMMMMMMY",
        dust_counts={"M": 18, "Y": 2},
        words_sha256="a7bb333e3866348c2cf3680aa0791f88"
                     "b53767cd5713c9be03a0ec0b57debc21",
    ),
    ("c2-cmy-r0700-p300@10x10", 0): dict(
        words="CYYCCCWCWC CCCCWCYCCY CCYCCCCCCY CCYCWCYYWC YCWWYCWCYC "
              "YCCWYCWCCC WYYYWCYCCC CCCWCYCWCW CYCCCCWYYC YCWWWYWCYC",
        zero_mask="1111010101 0101001111 0010000011 1011001100 1100100011 "
                  "1010100110 0111011000 0000011010 0111000110 1100010010",
        supply={"C": 55, "W": 20, "Y": 25},
        dust="MYCWYMYWWM WWWMMWMMYY MMYMWYYYYY MMWWCWWMMW CCMYWMWMMW "
             "MWYYCWWYWY CMWWMYMCCW MYYMWMMMWM MWWWCMWYCY YCMYMMMCYY "
             "YMMMMWMMWC MYYYWMMWWM WWYMYCMWYM WWWYMMMWYC WCCMMCMWMW "
             "MMMYMWWCYW YYMMYMMYMM WMMMMYWWWW YMWCYMMWMY YYMYWYMMYY",
        dust_counts={"M": 75, "Y": 50, "W": 55, "C": 20},
        words_sha256="4159ed0f85be5479bf05a2b8642eff0e"
                     "377305258ed33cb5553d1325d5ba6348",
    ),
}


def letters(text: str) -> str:
    return "".join(text.split())


def ids(text: str) -> list[int]:
    return [STATE_ID[s] for s in letters(text)]
