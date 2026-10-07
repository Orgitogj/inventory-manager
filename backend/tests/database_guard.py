from sqlalchemy.engine import URL, make_url

TEST_DATABASE_SUFFIX = "_test"


class UnsafeTestDatabaseError(RuntimeError):
    pass


def require_test_database_name(database_name: str | None) -> str:
    if not database_name or not database_name.endswith(TEST_DATABASE_SUFFIX):
        raise UnsafeTestDatabaseError(
            f"Refusing to run database tests against {database_name!r}: "
            f"the database name must end with {TEST_DATABASE_SUFFIX!r}."
        )

    return database_name


def require_test_database_url(database_url: str) -> URL:
    url = make_url(database_url)
    require_test_database_name(url.database)
    return url
