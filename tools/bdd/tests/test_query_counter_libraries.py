"""The query counter of the python-pytest-bdd adapter against the real SQLAlchemy and Django.

The hooks import the libraries only when used, so the adapter itself needs neither. These tests run when the library is
installed (the adapter CI job installs both from the pinned, hashed requirements) and are skipped otherwise.
"""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
QUERIES = REPO / "adapters" / "python-pytest-bdd" / "templates" / "tests" / "drivers" / "queries.py"
HAVE_SQLALCHEMY = importlib.util.find_spec("sqlalchemy") is not None
HAVE_DJANGO = importlib.util.find_spec("django") is not None


def load_queries():
    spec = importlib.util.spec_from_file_location("adapter_queries", QUERIES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAVE_SQLALCHEMY, "needs SQLAlchemy")
class SqlAlchemyHookTest(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine, text

        self.text = text
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(text("create table orders (id integer primary key)"))
            connection.execute(text("create table lines (id integer primary key, order_id integer)"))
            for i in range(3):
                connection.execute(text("insert into orders (id) values (:i)"), {"i": i})
                connection.execute(text("insert into lines (order_id) values (:i)"), {"i": i})
        self.counter = load_queries().QueryCounter()
        self.counter.hook_sqlalchemy(self.engine)

    def test_a_query_per_record_is_counted_statement_by_statement(self):
        from sqlalchemy.orm import Session

        with Session(self.engine) as session:
            for (order_id,) in session.execute(self.text("select id from orders")).all():
                session.execute(self.text("select * from lines where order_id = :o"), {"o": order_id}).all()
        self.assertEqual(self.counter.count, 4)                       # one for the list, one per order: the N+1 shape

    def test_a_single_joined_statement_is_one_query(self):
        with self.engine.connect() as connection:
            connection.execute(self.text("select * from orders join lines on lines.order_id = orders.id")).all()
        self.assertEqual(self.counter.count, 1)

    def test_savepoints_and_commits_are_not_counted(self):
        from sqlalchemy.orm import Session

        with Session(self.engine) as session:
            session.execute(self.text("select 1")).all()
            with session.begin_nested():
                session.execute(self.text("select 2")).all()
            session.commit()
        self.assertEqual(self.counter.count, 2)


@unittest.skipUnless(HAVE_DJANGO, "needs Django")
class DjangoHookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import django
        from django.conf import settings

        if not settings.configured:
            settings.configure(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
                               INSTALLED_APPS=[])
            django.setup()
        from django.db import connection

        cls.connection = connection
        with connection.cursor() as cursor:
            cursor.execute("create table if not exists items (id integer primary key)")
            cursor.execute("insert into items default values")

    def test_statements_run_inside_the_wrapper_are_counted_and_others_are_not(self):
        counter = load_queries().QueryCounter()
        with self.connection.cursor() as cursor:
            cursor.execute("select * from items")                       # before the wrapper
        with self.connection.execute_wrapper(counter.django_wrapper):
            with self.connection.cursor() as cursor:
                for _ in range(3):
                    cursor.execute("select * from items")
        self.assertEqual(counter.count, 3)

    def test_savepoints_made_by_atomic_are_not_counted(self):
        from django.db import transaction

        counter = load_queries().QueryCounter()
        with self.connection.execute_wrapper(counter.django_wrapper):
            with transaction.atomic():
                with transaction.atomic():
                    with self.connection.cursor() as cursor:
                        cursor.execute("select * from items")
        self.assertEqual(counter.count, 1)


if __name__ == "__main__":
    unittest.main()
