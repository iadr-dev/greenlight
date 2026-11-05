"""The roles of the code stage, by name: shared by the routing (``route``) and the guard, which must stay light."""

WRITERS = ("implementer", "ui-engineer")
REVIEWERS = ("code-reviewer", "security-reviewer", "ui-reviewer")
REVIEWS_DIR = "reviews"               # in a feature folder: reviews/<task>-<reviewer>.md, written by that reviewer only
