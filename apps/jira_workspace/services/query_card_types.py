from dataclasses import dataclass


JIRA_ISSUE_QUERY_CARD_KIND = "jira_issue_query"


@dataclass(frozen=True)
class QueryCardType:
    value: str
    label: str
    supports_issue_results: bool = False


QUERY_CARD_TYPES = (
    QueryCardType(
        value=JIRA_ISSUE_QUERY_CARD_KIND,
        label="Jira Issue Query",
        supports_issue_results=True,
    ),
)

_QUERY_CARD_TYPE_BY_VALUE = {card_type.value: card_type for card_type in QUERY_CARD_TYPES}


def get_query_card_type_choices():
    return [(card_type.value, card_type.label) for card_type in QUERY_CARD_TYPES]


def get_query_card_type(value):
    return _QUERY_CARD_TYPE_BY_VALUE.get(value)


def require_query_card_type(value):
    card_type = get_query_card_type(value)
    if card_type is None:
        raise ValueError(f"Unsupported query card type '{value}'.")
    return card_type
