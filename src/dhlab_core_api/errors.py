class InvalidQueryError(ValueError):
    """A user-supplied search expression could not be executed (e.g. malformed FTS5 syntax).

    Raised by the repository, translated to a ``400 Bad Request`` by the app.
    """
