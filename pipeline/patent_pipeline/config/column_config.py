"""
Column and dtype settings for the PatentsView files used in preprocessing.

I keep this in one place so the early column cuts are explicit. If a field is
not listed here, it is dropped when the raw TSV files are read.
"""

# Columns kept from each raw file.
COLUMNS = {
    "patent": [
        "patent_id",
        "patent_date",
        "patent_title",
        "num_claims",
    ],
    "application": [
        "application_id",
        "patent_id",
        "patent_application_type",
        "filing_date",
        "series_code",
        "rule_47_flag",
    ],
    "assignee": [
        "patent_id",
        "assignee_id",
        "disambig_assignee_organization",
    ],
    "cpc": [
        "patent_id",
        "cpc_group",
        "cpc_section",
        "cpc_class",
        "cpc_subclass",
    ],
    "citation": [
        "patent_id",
        "citation_patent_id",
    ],
    "abstract": [
        "patent_id",
        "patent_abstract",
    ],
    "claims": [
        "patent_id",
        "claim_number",
        "claim_text",
        "dependent",
    ],
    "inventor": [
        "patent_id",
        "inventor_id",
        "disambig_inventor_name_first",
        "disambig_inventor_name_last",
    ],
    "pct": [
        "patent_id",
        "pct_doc_number",
        "pct_371_date",
    ],
    "rel_doc": [
        "patent_id",
        "related_doc_number",
        "related_doc_type",
    ],
}


# Import dtypes used in the raw reads.
# IDs stay as strings, date fields are parsed later in preprocessing, and
# nullable integers are used where missing values can occur.
DTYPE_MAPPINGS = {
    "patent": {
        "patent_id": "string",
        "patent_date": "string",
        "patent_title": "string",
        "num_claims": "Int64",
    },
    "application": {
        "application_id": "string",
        "patent_id": "string",
        "patent_application_type": "string",
        "filing_date": "string",
        "series_code": "string",
        "rule_47_flag": "string",
    },
    "assignee": {
        "patent_id": "string",
        "assignee_id": "string",
        "disambig_assignee_organization": "string",
    },
    "cpc": {
        "patent_id": "string",
        "cpc_group": "string",
        "cpc_section": "string",
        "cpc_class": "string",
        "cpc_subclass": "string",
    },
    "citation": {
        "patent_id": "string",
        "citation_patent_id": "string",
    },
    "abstract": {
        "patent_id": "string",
        "patent_abstract": "string",
    },
    "claims": {
        "patent_id": "string",
        "claim_number": "Int64",
        "claim_text": "string",
        "dependent": "string",
    },
    "inventor": {
        "patent_id": "string",
        "inventor_id": "string",
        "disambig_inventor_name_first": "string",
        "disambig_inventor_name_last": "string",
    },
    "pct": {
        "patent_id": "string",
        "pct_doc_number": "string",
        "pct_371_date": "string",
    },
    "rel_doc": {
        "patent_id": "string",
        "related_doc_number": "string",
        "related_doc_type": "string",
    },
}
