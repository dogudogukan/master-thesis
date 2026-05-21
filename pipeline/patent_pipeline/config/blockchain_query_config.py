"""
Blockchain query settings based on Clarke et al. (2020),
"Blockchain patent landscaping: An expert based methodology and search query".

This file adapts Table 3 of Clarke et al. (2020) to a local USPTO PatentsView
workflow. The original query was written for the European Patent Office's
Global Patent Index (GPI), so I do not use it here as a literal search
string. Instead, I implement the same core logic over local title, abstract,
CPC, and assignee-linked patent data.

Some terms are also written in a way that fits the local matcher better. In
particular, hyphens and spaces are treated as equivalent, so "BLOCK-CHAIN"
also matches "block chain". I also retain selected wildcard expansions where
patent text regularly uses suffix variants, for example "ledger" and
"ledgers" or "smart contract" and "smart contracts". In a few places I also
keep spelling variants that show up across sources, for example
"COLORED-COIN" and "COLOURED-COIN".
"""

# Q1 terms from Table 3.
# This is the more specific text branch and it is paired with the broad
# G06/H04 classes. The paper lists "COLORED-COIN" twice, but I keep it once.
# Where a term ends with `*`, the local matcher is allowed to catch suffix
# variants that show up in patent titles and abstracts. I also keep a few
# spelling variants, such as "COLORED-COIN" and "COLOURED-COIN".
MAIN_KEYWORDS = [
    "BLOCKCHAIN*",
    "BLOCK-CHAIN*",
    "BITCOIN*",
    "BIT-COIN*",
    "BLOCKSIGN",
    "CODIUS",
    "COLORED-COIN*",
    "COLOURED-COIN*",
    "CRYPTOCURRENC*",
    "CRYPTO-CURRENC*",
    "DISTRIBUTED-LEDGER",
    "DOGECOIN",
    "DOGE-COIN",
    "ETHEREUM",
    "FACTOM",
    "LITECOIN",
    "LITE-COIN",
    "PAY-TO-SCRIPT-HASH",
    "P2SH",
    "PROOF-OF-STAKE",
    "SIDECHAIN*",
    "SMART-CONTRACT*",
    "SMARTCONTRACT*",
    "ZEROCASH",
    "ZCASH"
]

# Q2 terms from Table 3.
# This branch is broader and noisier than Q1, so I only use it with the
# narrower CPC groups listed below. Some terms keep a local wildcard to catch
# common variants such as "ledger" and "ledgers" or "digital currency" and
# "digital currencies".
SECONDARY_KEYWORDS = [
    "CHAINCOD*",
    "COUNTERPARTY",
    "XCP",
    "DIGITALCURRENC*",
    "DIGITAL-CURRENC*",
    "ETHER",
    "FORKING",
    "FORKS",
    "HAWK",
    "LEDGER*",
    "LISK",
    "MERKLE-TREE",
    "MERKLETREE",
    "HASH-TREE",
    "HASHTREE",
    "MERKLE-ROOT",
    "MERKLEROOT",
    "META-COIN*",
    "METACOIN*",
    "NAME-COIN*",
    "NAMECOIN*",
    "NXT",
    "PROOF-OF-WORK",
    "HASH-CASH",
    "HASHCASH",
    "ROOTSTOCK",
    "RSK",
    "RIPPLE",
    "STELLAR",
    "SYMBIONT",
    "TYPE-COIN*",
    "TYPECOIN*",
    "ZEROCOIN",
    "ZERO-COIN",
    "ZEROKNOWLEDGE",
    "ZERO-KNOWLEDGE"
]

# CPC filters used across the three branches.

# Broad classes used in Q1.
BROAD_CLASSES = [
    "G06",
    "H04"
]

# Specific CPC groups used in Q2.
# In PatentsView these sit in `cpc_group` (for example "H04L9/3236").
SPECIFIC_CLASSES = [
    # Cryptographic mechanisms and signatures
    "H04L9/3247",
    "H04L9/3249",
    "H04L9/3252",
    "H04L9/3255",
    "H04L9/3257",
    "H04L9/3236",
    "H04L9/3239",
    "H04L9/3242",
    "H04L9/0637",
    "H04L9/0643",
    
    # Financial cryptography and payment architectures
    "H04L2209/38",
    "H04L2209/56",
    
    # Other security and compression classes
    "H04L2209/30",
    "H04L2209/46",
    "H04L2209/463",
    "H04L2209/466",
    
    # Payment schemes and e-cash
    "G06Q20/065",
    "G06Q20/0652",
    "G06Q20/0655",
    "G06Q20/0658",
    "G06Q20/02",
    "G06Q20/023",
    "G06Q20/027",
    
    # Payment protocols
    "G06Q20/401",
    "G06Q20/4012",
    "G06Q20/4014",
    "G06Q20/40145",
    "G06Q20/4016",
    "G06Q20/4018",
]

# Q3 is the CPC-only branch from the published query.
# Q1 and Q2 combine text terms with CPC filters; Q3 stays as a CPC combination.

# First half of the Q3 CPC condition.
Q3_GROUP_A = [
    "H04L9/3236",  # Using cryptographic hash functions
    "H04L9/3239",  # Non-keyed hash functions
    "H04L9/3242",  # Keyed hash functions
    "H04L2209/38",  # Chaining, for example a hash chain
]

# Second half of the Q3 CPC condition.
Q3_REQUIRED = "H04L2209/56"

# Helpers that rebuild the query in a Table 3-style format.

def build_query_q1():
    """
    Return the Q1 logic as a boolean fragment.

    I leave out the literal `WORD=` and `CLAS=` prefixes because the pipeline
    uses these lists for local matching rather than sending a query back to
    GPI. So this is a Table 3-style reconstruction, not a literal export of
    the original search string.
    """
    keywords_or = " OR ".join([_format_gpi_term(kw) for kw in MAIN_KEYWORDS])
    classes_or = " OR ".join([_format_gpi_term(cls) for cls in BROAD_CLASSES])
    
    return f"({keywords_or}) AND ({classes_or})"

def build_query_q2():
    """
    Return the Q2 logic as a boolean fragment.

    As in Q1, this keeps the Table 3 structure but drops the literal GPI field
    prefixes. The keyword list also reflects the local wildcard choices
    described at the top of this file.
    """
    keywords_or = " OR ".join([_format_gpi_term(kw) for kw in SECONDARY_KEYWORDS])
    classes_or = " OR ".join([_format_gpi_term(cls) for cls in SPECIFIC_CLASSES])
    
    return f"({keywords_or}) AND ({classes_or})"

def build_query_q3():
    """
    Return the Q3 logic as a boolean fragment.

    This stays CPC-only, just like the published Q3 branch. I still omit the
    literal `CLAS=` prefix because the output is mainly for documentation and
    checking, not for direct submission to GPI.
    """
    group_a_or = " OR ".join([_format_gpi_term(code) for code in Q3_GROUP_A])
    
    return f"({group_a_or}) AND {_format_gpi_term(Q3_REQUIRED)}"


def _format_gpi_term(term: str) -> str:
    """
    Format one term so the rebuilt query still looks like Table 3.

    Terms with spaces or hyphens are quoted. Everything else is left as-is.
    """
    if (" " in term) or ("-" in term):
        return f"\"{term}\""
    return term

def get_full_blockchain_query():
    """
    Combine the three branches into one boolean query string.

    This mirrors the structure of the published full query without the literal
    `WORD=` and `CLAS=` prefixes.
    """
    q1 = build_query_q1()
    q2 = build_query_q2()
    q3 = build_query_q3()
    
    return f"({q1}) OR ({q2}) OR ({q3})"
