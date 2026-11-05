"""Curated always-generalize rows. Not applied yet — date-shift / review pane next.

Each rule: specific surface forms → coarser wording. The engine (later) will
match any `from_terms` variant and rewrite to `to`.
"""

from __future__ import annotations

# CWO2: listed as "Chief Warrant Officer 3" in the source note; stored as CWO2.
GENERALIZE_RULES: list[dict] = [
    {
        "category": "rank",
        "from_terms": ["CWO3", "Chief Warrant Officer 3"],
        "to": "a senior warrant officer",
    },
    {
        "category": "rank",
        "from_terms": ["CWO2", "Chief Warrant Officer 2"],
        "to": "a chief warrant officer",
    },
    {
        "category": "rank",
        "from_terms": ["WO1", "Warrant Officer 1"],
        "to": "a new warrant officer",
    },
    {
        "category": "rank",
        "from_terms": ["SGT", "Sergeant"],
        "to": "a non-commissioned officer",
    },
    {
        "category": "rank",
        "from_terms": ["CPL", "Corporal"],
        "to": "a non-commissioned officer",
    },
    {
        "category": "branch",
        "from_terms": ["U.S. Marine Corps", "USMC", "United States Marine Corps"],
        "to": "a U.S. military branch",
        "note": "Keep the real service name if the argument is the service itself.",
    },
    {
        "category": "branch",
        "from_terms": ["U.S. Army", "US Army", "United States Army"],
        "to": "a U.S. military branch",
    },
    {
        "category": "platform",
        "from_terms": ["CH-53", "Sea Stallion"],
        "to": "a military helicopter",
    },
    {
        "category": "platform",
        "from_terms": ["AH-64", "Apache"],
        "to": "a military helicopter",
    },
    {
        "category": "platform",
        "from_terms": ["OH-58", "Kiowa"],
        "to": "a military helicopter",
    },
    {
        "category": "platform",
        "from_terms": ["AH-1", "Cobra"],
        "to": "a military helicopter",
    },
    {
        "category": "era",
        "from_terms": ["retired in FY2004", "retired FY2004"],
        "to": "retired in the early 2000s",
    },
    {
        "category": "era",
        "from_terms": ["entered service in 1983"],
        "to": "entered service in the early 1980s",
    },
    {
        "category": "place",
        "from_terms": ["Palo Alto VA", "Palo Alto VA Medical Center"],
        "to": "a West Coast medical center",
    },
    {
        "category": "place",
        "from_terms": ["Maryland VA"],
        "to": "an East Coast medical center",
    },
    {
        "category": "place",
        "from_terms": ["Austin VA Clinic"],
        "to": "a central Texas medical center",
    },
    {
        "category": "place",
        "from_terms": ["Olin E. Teague Veterans' Center", "Olin E. Teague Veterans’ Center"],
        "to": "a central Texas medical center",
    },
    {
        "category": "event",
        "from_terms": ["right ankle sprain during field exercise in 1995"],
        "to": "line of duty injury of right ankle",
    },
]

# These name a *this-case* fact, not a reusable coarsening of all Thanksgivings.
CASE_SPECIFIC_ALIASES: list[dict] = [
    {
        "from_terms": ["Thanksgiving Day 1999", "Thanksgiving 1999"],
        "to": "date of original injury",
    },
    {
        "from_terms": ["November 1999"],
        "to": "date of original injury",
    },
]
